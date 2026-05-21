import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from payments.models import Order, Invoice
from payments.serializers import CreateOrderSerializer, OrderSerializer, InvoiceSerializer
from payments.services.base import create_order, confirm_order
from payments.services.stripe_gateway import create_payment_intent, verify_webhook, process_webhook_event
from payments.services.wechat_gateway import create_native_order, verify_notify as wechat_verify, process_notify as wechat_process
from payments.services.alipay_gateway import create_page_pay, verify_notify as alipay_verify, process_notify as alipay_process

logger = logging.getLogger(__name__)


class CreateOrderView(APIView):
    """Create a payment order and return gateway-specific payment params."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = CreateOrderSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        plan = ser.validated_data['plan']
        billing_cycle = ser.validated_data['billing_cycle']
        gateway = ser.validated_data['gateway']

        user = request.user
        inst = user.institution

        order = create_order(user=user, plan=plan, billing_cycle=billing_cycle, gateway=gateway, institution=inst)

        try:
            if gateway == 'stripe':
                payment_data = create_payment_intent(order)
            elif gateway == 'wechat':
                payment_data = create_native_order(order)
            elif gateway == 'alipay':
                payment_data = create_page_pay(order)
            else:
                return Response({'error': '不支持的支付方式'}, status=400)
        except Exception as e:
            logger.exception("Failed to create %s order %s", gateway, order.id)
            order.status = 'cancelled'
            order.save(update_fields=['status'])
            return Response({'error': f'创建支付订单失败: {str(e)}'}, status=500)

        return Response({
            'order_id': order.id,
            'gateway': gateway,
            'amount_cents': order.amount_cents,
            'plan': order.plan,
            'billing_cycle': order.billing_cycle,
            **payment_data,
        }, status=status.HTTP_201_CREATED)


class OrderStatusView(APIView):
    """Query order payment status."""
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id, user=request.user)
        except Order.DoesNotExist:
            return Response({'error': '订单不存在'}, status=404)
        return Response(OrderSerializer(order).data)


class OrderHistoryView(APIView):
    """List user's past payment orders."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Order.objects.filter(user=request.user).order_by('-created_at')
        return Response(OrderSerializer(qs, many=True).data)


class InvoiceListView(APIView):
    """List user's invoices."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        orders = Order.objects.filter(user=request.user, status='paid')
        invoices = Invoice.objects.filter(order__in=orders)
        return Response(InvoiceSerializer(invoices, many=True).data)


# ── Webhook handlers (no auth — signature verified internally) ──


class StripeWebhookView(APIView):
    permission_classes = []

    def post(self, request):
        sig = request.headers.get('stripe-signature', '')
        try:
            event = verify_webhook(request.body, sig)
            result = process_webhook_event(event)
            if not result:
                return Response({'status': 'ignored'})
            order = Order.objects.get(id=result['order_id'])
            confirm_order(order, result['gateway_txn_id'], result['raw'], result.get('amount_cents'))
            return Response({'status': 'ok'})
        except Exception as e:
            logger.exception("Stripe webhook error")
            return Response({'error': str(e)}, status=400)


class WechatNotifyView(APIView):
    permission_classes = []

    def post(self, request):
        try:
            data = wechat_verify(request.headers, request.body)
            result = wechat_process(data)
            if not result:
                return Response({'code': 'FAIL', 'message': 'ignored'})
            order = Order.objects.get(id=result['order_id'])
            confirm_order(order, result['gateway_txn_id'], result['raw'], result.get('amount_cents'))
            return Response({'code': 'SUCCESS'})
        except Order.DoesNotExist:
            return Response({'code': 'FAIL', 'message': 'order not found'})
        except Exception as e:
            logger.exception("WeChat notify error")
            return Response({'code': 'FAIL', 'message': str(e)})


class AlipayNotifyView(APIView):
    permission_classes = []

    def post(self, request):
        try:
            data = dict(request.data)
            signature = data.pop('sign', '')
            if not alipay_verify(data, signature):
                return Response('fail')
            result = alipay_process(data)
            if not result:
                return Response('success')  # ack non-terminal states
            order = Order.objects.get(id=result['order_id'])
            confirm_order(order, result['gateway_txn_id'], result['raw'], result.get('amount_cents'))
            return Response('success')
        except Order.DoesNotExist:
            return Response('fail')
        except Exception as e:
            logger.exception("Alipay notify error")
            return Response('fail')


class AlipayReturnView(APIView):
    """Alipay redirects user here after payment. Frontend handles the actual UX."""
    permission_classes = []

    def get(self, request):
        return Response({'status': 'redirect', 'message': '请在前端确认支付结果'})
