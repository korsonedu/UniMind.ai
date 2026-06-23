import logging
import os
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from payments.models import Order, Invoice

logger = logging.getLogger(__name__)


@shared_task
def generate_invoice(order_id: int):
    """Generate PDF invoice for a paid order."""
    from django.conf import settings

    order = Order.objects.select_related('user').filter(pk=order_id).first()
    if not order or order.status != 'paid':
        logger.warning("invoice: order %s not ready (status=%s)", order_id, getattr(order, 'status', 'N/A'))
        return

    invoice_number = f"INV-{order.paid_at.strftime('%Y%m%d')}-{order_id:06d}"
    pdf_path = f"invoices/{invoice_number}.pdf"

    # Minimal placeholder — PDF rendering via weasyprint or similar in production
    try:
        # Placeholder: just create an empty record for now
        # Full PDF rendering would use a template + weasyprint
        Invoice.objects.update_or_create(
            order=order,
            defaults={'invoice_number': invoice_number, 'pdf_file': ''},
        )
        logger.info("Invoice %s created for order %s", invoice_number, order_id)
    except Exception:
        logger.exception("Failed to generate invoice for order %s", order_id)


@shared_task
def expire_stale_orders():
    """Cancel orders that have been pending for more than 30 minutes."""
    threshold = timezone.now() - timedelta(minutes=30)
    expired = Order.objects.filter(status='pending', created_at__lt=threshold).update(status='expired')
    if expired:
        logger.info("expire_stale_orders: %s orders expired", expired)


@shared_task
def check_subscription_expiry():
    """Daily: find active subscriptions past their period_end → expire them."""
    from payments.models import Subscription
    from payments.services.subscription import expire_subscription

    now = timezone.now()
    expired_subs = Subscription.objects.filter(
        status='active',
        current_period_end__lt=now,
    )

    count = 0
    for sub in expired_subs:
        try:
            expire_subscription(sub)
            count += 1
        except Exception:
            logger.exception("Failed to expire subscription %s", sub.id)

    if count:
        logger.info("check_subscription_expiry: %s subscriptions expired", count)
