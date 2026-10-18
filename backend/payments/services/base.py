"""
Payment gateway base — shared utilities for creating orders and processing callbacks.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from payments.models import Order, PaymentTransaction
from users.services.membership import activate_membership

logger = logging.getLogger(__name__)

# Order timeout in minutes
ORDER_TIMEOUT_MINUTES = 30

# Plan → amount in cents
PLAN_PRICES_MONTHLY = {
    'starter': 49900,
    'growth': 129900,
    'enterprise': 399900,
}
PLAN_PRICES_ANNUAL = {
    'starter': 499200,     # ¥416/月 × 12 = ¥4,992/年
    'growth': 1299600,     # ¥1,083/月 × 12 = ¥12,996/年
    'enterprise': 3999600, # ¥3,333/月 × 12 = ¥39,996/年
}
PLAN_DURATION_DAYS = {
    'monthly': 30,
    'annual': 365,
}


def get_plan_price(plan: str, billing_cycle: str) -> int:
    prices = PLAN_PRICES_ANNUAL if billing_cycle == 'annual' else PLAN_PRICES_MONTHLY
    return prices.get(plan, 0)


def create_order(*, user, plan: str, billing_cycle: str, gateway: str, institution=None, coupon_code: str = '') -> Order:
    raise ValueError('机构套餐已停止销售。')


def create_learning_order(*, user, product, gateway):
    raise ValueError('课程服务已停止在线销售。')


def create_ai_addon_order(*, user, product, gateway):
    if not product.is_active or not product.configured:
        raise ValueError('AI 加量商品尚未完整配置或未上架。')
    return Order.objects.create(user=user, ai_addon_product=product, plan='ai_addon', billing_cycle='fixed',
                                amount_cents=product.price_cents, entitlement_snapshot=product.snapshot(), gateway=gateway,
                                expires_at=timezone.now() + timedelta(minutes=ORDER_TIMEOUT_MINUTES))


def confirm_order(order_id: int, gateway_txn_id: str, raw_callback: dict, amount_cents: int | None = None):
    """Called when a payment gateway confirms payment.

    Uses select_for_update() to prevent race conditions from concurrent
    webhook deliveries — only one thread can process a given order.
    """
    with transaction.atomic():
        order = Order.objects.select_for_update().get(id=order_id)

        # 校验回调金额与订单金额一致，防止金额篡改
        if amount_cents is not None and amount_cents != order.amount_cents:
            logger.error("Order %s amount mismatch: expected %s, got %s", order.id, order.amount_cents, amount_cents)
            raise ValueError(f"Payment amount mismatch: expected {order.amount_cents}, got {amount_cents}")

        if order.status == 'paid':
            if order.gateway_order_id != gateway_txn_id:
                raise ValueError('Payment transaction mismatch')
            logger.warning("Order %s already paid, ignoring duplicate callback", order.id)
            return

        # 如果使用了优惠券，在标记支付成功前扣减使用次数
        # （失败则抛出异常回滚整个事务，避免已付款但未扣减的情况）
        if order.coupon_code:
            from .coupon import apply_coupon
            from payments.models import Coupon
            coupon = Coupon.objects.get(code=order.coupon_code, is_active=True)
            apply_coupon(coupon, order.user, order)

        PaymentTransaction.objects.create(
            order=order,
            gateway=order.gateway,
            gateway_txn_id=gateway_txn_id,
            raw_callback=raw_callback,
            amount_cents=amount_cents,
            status='success',
        )

        order.status = 'paid'
        order.paid_at = timezone.now()
        order.gateway_order_id = gateway_txn_id
        order.save(update_fields=['status', 'paid_at', 'gateway_order_id'])

        # 会员激活移入 atomic 块内，确保崩溃窗口中不会出现已付款未激活
        if order.plan == 'ai_addon':
            from users.learning import grant_ai_addon
            grant_ai_addon(order)
        elif order.product_id:
            from users.learning import grant_product
            grant_product(order.user, order.product, source='payment', order=order, snapshot=order.entitlement_snapshot)
        else:
            duration = PLAN_DURATION_DAYS.get(order.billing_cycle, 30)
            activate_membership(order.user, order.plan, duration, source='payment')

    # Generate invoice asynchronously
    from payments.tasks import generate_invoice
    transaction.on_commit(lambda: generate_invoice.delay(order.id))

    logger.info("Order %s confirmed via %s, txn=%s", order.id, order.gateway, gateway_txn_id)
