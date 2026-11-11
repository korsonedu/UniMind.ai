"""
Payment views — 通过 gateway_router 动态选择支付网关。
"""
import logging

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.http import HttpResponse

from payments.models import Order
from payments.serializers import CreateOrderSerializer, OrderSerializer
from payments.services.base import create_ai_addon_order, confirm_order
from payments.services.gateway_router import get_gateway
from payments.services.subscription import activate_subscription

logger = logging.getLogger(__name__)


class CreateCheckoutSessionView(APIView):
    """创建订单 → 返回模拟收银台 URL。"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = CreateOrderSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        gateway = ser.validated_data['gateway']

        from django.conf import settings as django_settings
        if gateway == 'stub' and not getattr(django_settings, 'DEBUG', False):
            return Response({'error': '当前环境不支持该支付方式'}, status=400)

        from users.models import AIAddonProduct
        from users.views_learning import payment_methods
        if gateway not in payment_methods():
            return Response({'error': '该支付方式暂未开通。'}, status=400)
        product = get_object_or_404(AIAddonProduct, pk=ser.validated_data['product'], is_active=True, price_cents__gt=0, ai_calls__gt=0, validity_days__gt=0)
        order = create_ai_addon_order(user=request.user, product=product, gateway=gateway)

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
        if order.gateway != 'stub':
            return Response({'error': '仅模拟订单可使用此操作。'}, status=400)

        import uuid
        txn_id = f'stub_{uuid.uuid4().hex[:12]}'
        confirm_order(order.id, txn_id, {'source': 'simulate'}, order.amount_cents)
        return Response({
            'status': 'paid',
            'order_id': order.id,
            'gateway_txn_id': txn_id,
        })


class RetiredCouponView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def _retired(self, request, *args, **kwargs):
        return Response({'error': '旧版机构套餐优惠码已停止使用。'}, status=410)

    get = post = put = patch = delete = _retired


# ── Referral ──


class MyReferralView(APIView):
    """GET /api/payments/referral/ — 获取或创建用户推荐码。"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from payments.models import ReferralCode
        import secrets
        code_obj, created = ReferralCode.objects.get_or_create(
            user=request.user,
            defaults={'code': secrets.token_hex(4).upper()},
        )
        return Response({
            'code': code_obj.code,
            'clicks': code_obj.clicks,
            'signups': code_obj.signups,
            'purchases': code_obj.purchases,
        })


# ── Webhook (no auth — 真实支付时校验签名) ──

class WebhookView(APIView):
    """支付网关 webhook 接收端。通过 ?gateway=xxx 路由到对应网关。"""
    permission_classes = []
    authentication_classes = []

    def post(self, request):
        import hmac
        from django.conf import settings
        gateway_name = request.query_params.get('gateway')
        if not gateway_name:
            return Response({'error': 'Missing gateway parameter'}, status=400)
        if gateway_name not in {'stub', 'alipay'}:
            return Response({'error': '不支持该支付网关。'}, status=400)
        if gateway_name != 'alipay':
            webhook_secret = getattr(settings, 'PAYMENT_WEBHOOK_SECRET', '')
            if not webhook_secret:
                return Response({"error": "Webhook not configured"}, status=500)
            provided = request.headers.get('X-Webhook-Secret', '')
            if not hmac.compare_digest(str(provided), str(webhook_secret)):
                return Response({'detail': 'Invalid webhook secret'}, status=403)

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
                return HttpResponse('success') if gateway_name == 'alipay' else Response({'status': 'ignored'})

            if result.get('order_id'):
                order = Order.objects.get(pk=result['order_id'], gateway=gateway_name)
                if gateway_name == 'alipay':
                    expected_number = f'unimind-{order.id}-{order.created_at.strftime("%Y%m%d%H%M%S")}'
                    if event.get('out_trade_no') != expected_number or result.get('amount_cents') is None:
                        raise ValueError('Invalid Alipay order notification')

            # Subscription checkout completed → activate the subscription
            if result.get('type') == 'subscription_checkout_completed':
                from payments.models import Subscription as SubscriptionModel
                sub = SubscriptionModel.objects.filter(
                    institution__orders__id=result['order_id'],
                    status='pending',
                ).order_by('-created_at').first()
                if sub:
                    activate_subscription(
                        sub,
                        result.get('gateway_subscription_id', ''),
                        result.get('gateway_customer_id', ''),
                    )
                # Also confirm the order
                confirm_order(result['order_id'], result['gateway_txn_id'], result['raw'], result.get('amount_cents'))
                return Response({'status': 'ok', 'type': 'subscription_checkout_completed'})

            # Subscription renewed → extend current_period_end
            if result.get('type') == 'subscription_renewed':
                from payments.models import Subscription as SubscriptionModel
                from payments.services.subscription import renew_subscription
                sub = SubscriptionModel.objects.filter(
                    gateway_subscription_id=result.get('gateway_subscription_id'),
                    status='active',
                ).first()
                if sub and result.get('new_period_end'):
                    from django.utils.dateparse import parse_datetime
                    new_end = parse_datetime(result['new_period_end']) if isinstance(result['new_period_end'], str) else result['new_period_end']
                    renew_subscription(sub, new_end)
                return Response({'status': 'ok', 'type': 'subscription_renewed'})

            # One-time payment events
            confirm_order(result['order_id'], result['gateway_txn_id'], result['raw'], result.get('amount_cents'))
            return HttpResponse('success') if gateway_name == 'alipay' else Response({'status': 'ok'})
        except Order.DoesNotExist:
            return Response({'status': 'order not found'}, status=404)
        except Exception:
            logger.exception('Webhook error')
            return Response({'error': 'webhook processing failed'}, status=400)
