"""
Payment gateway base — shared utilities for creating orders and processing callbacks.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from payments.models import Order, PaymentTransaction
from users.services.membership import activate_membership

logger = logging.getLogger(__name__)

# Order timeout in minutes
ORDER_TIMEOUT_MINUTES = 30

# Plan → amount in cents
PLAN_PRICES_MONTHLY = {
    'solo': 29900,
    'plus': 129900,
    'pro': 399900,
}
PLAN_PRICES_ANNUAL = {
    'solo': 19900,   # ~67% of monthly
    'plus': 99900,
    'pro': 299900,
}
PLAN_DURATION_DAYS = {
    'monthly': 30,
    'annual': 365,
}


def get_plan_price(plan: str, billing_cycle: str) -> int:
    prices = PLAN_PRICES_ANNUAL if billing_cycle == 'annual' else PLAN_PRICES_MONTHLY
    return prices.get(plan, 0)


def create_order(*, user, plan: str, billing_cycle: str, gateway: str, institution=None) -> Order:
    amount = get_plan_price(plan, billing_cycle)
    now = timezone.now()
    return Order.objects.create(
        user=user,
        institution=institution,
        plan=plan,
        billing_cycle=billing_cycle,
        amount_cents=amount,
        gateway=gateway,
        expires_at=now + timedelta(minutes=ORDER_TIMEOUT_MINUTES),
    )


def confirm_order(order: Order, gateway_txn_id: str, raw_callback: dict, amount_cents: int | None = None):
    """Called when a payment gateway confirms payment."""
    if order.status == 'paid':
        logger.warning("Order %s already paid, ignoring duplicate callback", order.id)
        return

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

    # Activate membership for the paying user
    duration = PLAN_DURATION_DAYS.get(order.billing_cycle, 30)
    activate_membership(order.user, order.plan, duration, source=order.gateway)

    # Generate invoice asynchronously
    from payments.tasks import generate_invoice
    generate_invoice.delay(order.id)

    logger.info("Order %s confirmed via %s, txn=%s", order.id, order.gateway, gateway_txn_id)
