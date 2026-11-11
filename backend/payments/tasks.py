import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from payments.models import Order

logger = logging.getLogger(__name__)


@shared_task(soft_time_limit=60, time_limit=120)
def expire_stale_orders():
    """Cancel orders that have been pending for more than 30 minutes."""
    threshold = timezone.now() - timedelta(minutes=30)
    expired = Order.objects.filter(status='pending', created_at__lt=threshold).update(status='expired')
    if expired:
        logger.info("expire_stale_orders: %s orders expired", expired)


@shared_task(soft_time_limit=120, time_limit=180)
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
