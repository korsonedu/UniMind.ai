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
    """Daily: find active subscriptions past their period_end → expire them (batch optimized)."""
    from payments.models import Subscription
    from django.contrib.auth import get_user_model
    from users.models import Institution

    User = get_user_model()
    now = timezone.now()
    expired_subs = list(Subscription.objects.filter(
        status='active',
        current_period_end__lt=now,
    ).select_related('institution'))
    if not expired_subs:
        return

    sub_ids = [s.id for s in expired_subs]
    inst_ids = list({s.institution_id for s in expired_subs if s.institution_id})

    # 1) Bulk update subscription statuses
    Subscription.objects.filter(id__in=sub_ids).update(status='expired')

    # 2) Bulk update institution plans
    if inst_ids:
        Institution.objects.filter(id__in=inst_ids).update(
            plan='free',
            plan_expires_at=None,
        )

    # 3) Bulk downgrade institution owners' personal membership
    if inst_ids:
        owner_user_ids = list(User.objects.filter(
            institution_id__in=inst_ids,
            institution_role='owner',
            is_member=True,
        ).values_list('id', flat=True))
        if owner_user_ids:
            User.objects.filter(id__in=owner_user_ids).update(
                is_member=False,
                membership_tier='free',
                membership_expires_at=None,
                membership_source=None,
            )

    logger.info("check_subscription_expiry: %s subscriptions expired, %s institutions downgraded",
                len(sub_ids), len(inst_ids))
