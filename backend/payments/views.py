"""
Payment views — 通过 gateway_router 动态选择支付网关。
"""
import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from payments.models import Order, Invoice
from payments.serializers import CreateOrderSerializer, OrderSerializer, InvoiceSerializer
from payments.services.base import create_order, confirm_order
from payments.services.gateway_router import get_gateway

logger = logging.getLogger(__name__)


class CreateCheckoutSessionView(APIView):
    """创建订单 → 返回模拟收银台 URL。"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = CreateOrderSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        plan = ser.validated_data['plan']
        billing_cycle = ser.validated_data['billing_cycle']
        gateway = ser.validated_data['gateway']

        from django.conf import settings as django_settings
        if gateway == 'stub' and not getattr(django_settings, 'DEBUG', False):
            return Response({'error': '当前环境不支持该支付方式'}, status=400)

        order = create_order(
            user=request.user,
            plan=plan,
            billing_cycle=billing_cycle,
            gateway=gateway,
            institution=request.user.institution,
        )

        try:
            gw = get_gateway(gateway)
            data = gw.create_checkout_session(order)
        except Exception:
            logger.exception('Session create failed for order %s (gateway=%s)', order.id, gateway)
            order.status = 'cancelled'
            order.save(update_fields=['status'])
            return Response({'error': '创建支付会话失败'}, status=500)

        return Response({
            'order_id': order.id,
            'checkout_url': data['checkout_url'],
        }, status=status.HTTP_201_CREATED)


class OrderStatusView(APIView):
    """查询订单支付状态。"""
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id, user=request.user)
        except Order.DoesNotExist:
            return Response({'error': '订单不存在'}, status=404)
        return Response(OrderSerializer(order).data)


class OrderHistoryView(APIView):
    """用户历史订单列表。"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Order.objects.filter(user=request.user).order_by('-created_at')
        try:
            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', 20))
        except (ValueError, TypeError):
            page, page_size = 1, 20
        start = (page - 1) * page_size
        end = start + page_size
        qs = qs[start:end]
        return Response(OrderSerializer(qs, many=True).data)


class InvoiceListView(APIView):
    """用户发票列表。"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        orders = Order.objects.filter(user=request.user, status='paid')
        invoices = Invoice.objects.filter(order__in=orders)
        return Response(InvoiceSerializer(invoices, many=True).data)


class SimulatePaymentView(APIView):
    """
    [开发专用] 模拟支付成功 — 直接确认订单，跳过真实支付。
    生产环境应移除此端点。
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        from django.conf import settings
        if not getattr(settings, 'DEBUG', False):
            return Response({'detail': 'Not available in production'}, status=404)

        try:
            order = Order.objects.get(id=order_id, user=request.user)
        except Order.DoesNotExist:
            return Response({'error': '订单不存在'}, status=404)

        if order.status == 'paid':
            return Response({'status': 'already_paid', 'message': '该订单已支付'})

        import uuid
        txn_id = f'stub_{uuid.uuid4().hex[:12]}'
        confirm_order(order.id, txn_id, {'source': 'simulate'}, order.amount_cents)
        return Response({
            'status': 'paid',
            'order_id': order.id,
            'gateway_txn_id': txn_id,
        })


# ── Webhook (no auth — 真实支付时校验签名) ──

class WebhookView(APIView):
    """支付网关 webhook 接收端。通过 ?gateway=xxx 路由到对应网关。"""
    permission_classes = []

    def post(self, request):
        import hmac
        from django.conf import settings
        webhook_secret = getattr(settings, 'PAYMENT_WEBHOOK_SECRET', '')
        if not webhook_secret:
            return Response({"error": "Webhook not configured"}, status=500)
        else:
            provided = request.headers.get('X-Webhook-Secret', '')
            if not hmac.compare_digest(str(provided), str(webhook_secret)):
                return Response({'detail': 'Invalid webhook secret'}, status=403)

        gateway_name = request.query_params.get('gateway')
        if not gateway_name:
            return Response({'error': 'Missing gateway parameter'}, status=400)

        from django.conf import settings as django_settings
        if gateway_name == 'stub' and not getattr(django_settings, 'DEBUG', False):
            return Response({'error': 'Stub gateway not available in production'}, status=400)

        try:
            gw = get_gateway(gateway_name)
        except ValueError:
            return Response({'error': f'Unknown gateway: {gateway_name}'}, status=400)

        try:
            event = gw.verify_webhook(request.headers, request.body)
            result = gw.process_webhook_event(event)
            if not result:
                return Response({'status': 'ignored'})
            confirm_order(result['order_id'], result['gateway_txn_id'], result['raw'], result.get('amount_cents'))
            return Response({'status': 'ok'})
        except Order.DoesNotExist:
            return Response({'status': 'order not found'}, status=404)
        except Exception:
            logger.exception('Webhook error')
            return Response({'error': 'webhook processing failed'}, status=400)
