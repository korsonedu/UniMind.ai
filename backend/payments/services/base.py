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
    amount = get_plan_price(plan, billing_cycle)
    now = timezone.now()

    discount_cents = 0
    applied_coupon_code = ''

    if coupon_code:
        from .coupon import validate_coupon
        result = validate_coupon(coupon_code, user, plan, amount)
        if result['valid']:
            discount_cents = result['discount_cents']
            amount = result['final_amount_cents']
            applied_coupon_code = coupon_code
            # 注意：apply_coupon 在 confirm_order 时调用，避免未支付就扣减次数

    return Order.objects.create(
        user=user,
        institution=institution,
        plan=plan,
        billing_cycle=billing_cycle,
        amount_cents=amount,
        gateway=gateway,
        coupon_code=applied_coupon_code,
        discount_cents=discount_cents,
        expires_at=now + timedelta(minutes=ORDER_TIMEOUT_MINUTES),
    )


def confirm_order(order_id: int, gateway_txn_id: str, raw_callback: dict, amount_cents: int | None = None):
    """Called when a payment gateway confirms payment.

    Uses select_for_update() to prevent race conditions from concurrent
    webhook deliveries — only one thread can process a given order.
    """
    with transaction.atomic():
        order = Order.objects.select_for_update().get(id=order_id)

        if order.status == 'paid':
            logger.warning("Order %s already paid, ignoring duplicate callback", order.id)
            return

        # 校验回调金额与订单金额一致，防止金额篡改
        if amount_cents is not None and amount_cents != order.amount_cents:
            logger.error("Order %s amount mismatch: expected %s, got %s", order.id, order.amount_cents, amount_cents)
            raise ValueError(f"Payment amount mismatch: expected {order.amount_cents}, got {amount_cents}")

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
        duration = PLAN_DURATION_DAYS.get(order.billing_cycle, 30)
        activate_membership(order.user, order.plan, duration, source=order.gateway)

    # Generate invoice asynchronously
    from payments.tasks import generate_invoice
    generate_invoice.delay(order.id)

    logger.info("Order %s confirmed via %s, txn=%s", order.id, order.gateway, gateway_txn_id)
