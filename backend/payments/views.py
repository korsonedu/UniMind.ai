"""
Payment views — 通过 gateway_router 动态选择支付网关。
"""
import logging

from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404

from payments.models import Order, Invoice, Subscription, Coupon
from payments.serializers import (
    CreateOrderSerializer, OrderSerializer, InvoiceSerializer,
    CouponSerializer, CouponValidateSerializer,
)
from payments.services.base import create_order, confirm_order, get_plan_price
from payments.services.coupon import validate_coupon
from payments.services.gateway_router import get_gateway, gateway_supports_subscriptions
from payments.services.subscription import (
    create_subscription, activate_subscription, cancel_subscription as cancel_sub_biz,
    get_active_subscription,
)
from users.permissions import IsInstitutionOwner, is_institution_owner

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
            coupon_code=ser.validated_data.get('coupon_code', ''),
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


# ── Subscription ──


class CreateSubscriptionView(APIView):
    """POST /api/payments/subscriptions/ — 创建订阅结账会话（网关无关）。"""
    permission_classes = [IsAuthenticated, IsInstitutionOwner]

    def post(self, request):
        user = request.user
        inst = user.institution

        plan = request.data.get('plan', 'starter')
        billing_cycle = request.data.get('billing_cycle', 'monthly')
        gateway = request.data.get('gateway', 'stub')

        if plan not in dict(Subscription.PLAN_CHOICES):
            return Response({'error': f'无效方案: {plan}'}, status=400)
        if billing_cycle not in dict(Subscription.BILLING_CHOICES):
            return Response({'error': f'无效周期: {billing_cycle}'}, status=400)

        if not gateway_supports_subscriptions(gateway):
            return Response({'error': f'该支付方式暂不支持订阅'}, status=400)

        # 1. Create a one-time order for the subscription checkout
        try:
            from payments.services.base import create_order as create_payment_order
            order = create_payment_order(
                user=user,
                plan=plan,
                billing_cycle=billing_cycle,
                gateway=gateway,
                institution=inst,
            )
        except Exception:
            logger.exception('Order creation failed for subscription')
            return Response({'error': '创建订单失败'}, status=500)

        # 2. Create pending subscription record
        try:
            sub = create_subscription(
                institution=inst,
                plan=plan,
                billing_cycle=billing_cycle,
                gateway=gateway,
            )
        except Exception:
            logger.exception('Subscription record creation failed')
            return Response({'error': '创建订阅记录失败'}, status=500)

        # 3. Get checkout URL from gateway
        try:
            gw = get_gateway(gateway)
            data = gw.create_subscription_checkout(order)
        except Exception:
            logger.exception('Subscription checkout failed for order %s (gateway=%s)', order.id, gateway)
            order.status = 'cancelled'
            order.save(update_fields=['status'])
            return Response({'error': '创建订阅会话失败'}, status=500)

        return Response({
            'subscription_id': sub.id,
            'order_id': order.id,
            'checkout_url': data.get('checkout_url'),
        }, status=status.HTTP_201_CREATED)


class SubscriptionStatusView(APIView):
    """GET/POST /api/payments/subscriptions/me/ — 查看/取消机构订阅（网关无关）。"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        inst = getattr(request.user, 'institution', None)
        if not inst:
            return Response({'error': '无机构归属'}, status=403)

        sub = get_active_subscription(inst)
        if not sub:
            return Response({'subscription': None})

        return Response({
            'subscription': {
                'id': sub.id,
                'plan': sub.plan,
                'billing_cycle': sub.billing_cycle,
                'status': sub.status,
                'gateway': sub.gateway,
                'current_period_start': sub.current_period_start.isoformat() if sub.current_period_start else None,
                'current_period_end': sub.current_period_end.isoformat() if sub.current_period_end else None,
                'canceled_at': sub.canceled_at.isoformat() if sub.canceled_at else None,
                'created_at': sub.created_at.isoformat(),
            }
        })

    def post(self, request):
        """取消订阅。"""
        if not is_institution_owner(request.user):
            return Response({'error': '仅机构所有者可操作'}, status=403)

        inst = request.user.institution
        sub = get_active_subscription(inst)
        if not sub:
            return Response({'error': '无活跃订阅'}, status=404)

        # Cancel on gateway side
        try:
            if gateway_supports_subscriptions(sub.gateway):
                gw = get_gateway(sub.gateway)
                gw.cancel_subscription(sub)
        except Exception:
            logger.exception('Gateway cancel failed for subscription %s', sub.id)

        # Always cancel locally
        cancel_sub_biz(sub)
        return Response({'success': True, 'status': 'canceled'})


# ── Coupons ──


class CouponValidateView(APIView):
    """POST /api/payments/coupons/validate/ — 验证优惠码并预览折扣。"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = CouponValidateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        code = ser.validated_data['code']
        plan = ser.validated_data['plan']
        billing_cycle = ser.validated_data['billing_cycle']

        try:
            amount = get_plan_price(plan, billing_cycle)
        except (KeyError, ValueError):
            return Response({'error': '无效的方案或计费周期'}, status=400)

        result = validate_coupon(code, request.user, plan, amount)
        if result['valid']:
            return Response({
                'valid': True,
                'discount_cents': result['discount_cents'],
                'final_amount_cents': result['final_amount_cents'],
                'original_amount_cents': amount,
                'code': code,
            })
        return Response({'valid': False, 'error': result['error']}, status=400)


class CouponListCreateView(APIView):
    """GET/POST /api/payments/coupons/ — 列表+创建优惠券。"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        inst = getattr(request.user, 'institution', None)
        if request.user.is_superuser and not inst:
            qs = Coupon.objects.filter(institution__isnull=True)
        elif inst:
            qs = Coupon.objects.filter(institution=inst) | Coupon.objects.filter(institution__isnull=True)
        else:
            qs = Coupon.objects.none()
        ser = CouponSerializer(qs, many=True)
        return Response(ser.data)

    def post(self, request):
        inst = getattr(request.user, 'institution', None)
        if not inst and not request.user.is_superuser:
            return Response({'error': '无权创建优惠券'}, status=403)

        ser = CouponSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ser.save(institution=inst, created_by=request.user)
        return Response(ser.data, status=201)


class CouponDetailView(APIView):
    """PUT/DELETE /api/payments/coupons/<int:pk>/ — 更新/删除优惠券。"""
    permission_classes = [IsAuthenticated]

    def _get_coupon(self, pk, user):
        inst = getattr(user, 'institution', None)
        coupon = get_object_or_404(Coupon, pk=pk)
        if coupon.institution and coupon.institution != inst:
            raise PermissionDenied('无权操作此优惠券')
        if not coupon.institution and not user.is_superuser:
            raise PermissionDenied('无权操作平台通用优惠券')
        return coupon

    def put(self, request, pk):
        coupon = self._get_coupon(pk, request.user)
        ser = CouponSerializer(coupon, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)

    def delete(self, request, pk):
        coupon = self._get_coupon(pk, request.user)
        coupon.delete()
        return Response(status=204)


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
            return Response({'status': 'ok'})
        except Order.DoesNotExist:
            return Response({'status': 'order not found'}, status=404)
        except Exception:
            logger.exception('Webhook error')
            return Response({'error': 'webhook processing failed'}, status=400)
