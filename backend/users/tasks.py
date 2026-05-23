import logging
from datetime import timedelta

from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone

logger = logging.getLogger(__name__)

User = get_user_model()


@shared_task
def check_membership_expiry():
    """每日检查会员和试用到期，自动降级。"""
    now = timezone.now()

    # 试用到期
    trial_expired = User.objects.filter(
        is_member=True,
        membership_tier='free',
        trial_ends_at__lt=now,
        membership_expires_at__isnull=True,
    )
    count_trial = trial_expired.update(
        is_member=False,
        membership_tier='free',
        trial_ends_at=None,
    )

    # 付费会员到期
    paid_expired = User.objects.filter(
        is_member=True,
        membership_expires_at__lt=now,
    )
    count_paid = paid_expired.update(
        is_member=False,
        membership_tier='free',
        membership_expires_at=None,
        trial_ends_at=None,
    )

    total = count_trial + count_paid
    if total > 0:
        logger.info("check_membership_expiry: %s users downgraded (trial=%s paid=%s)", total, count_trial, count_paid)


@shared_task
def notify_trial_expiring():
    """提前 3 天提醒试用即将到期，提前 1 天再次提醒。"""
    from notifications.models import Notification

    now = timezone.now()
    for days_left in (3, 1):
        target_date = now + timedelta(days=days_left)
        users = User.objects.filter(
            is_member=True,
            membership_tier='free',
            trial_ends_at__date=target_date.date(),
            membership_expires_at__isnull=True,
        )
        for user in users:
            Notification.objects.create(
                recipient=user,
                ntype='system',
                title='试用即将到期' if days_left == 3 else '试用明天到期',
                content=f'您的 {days_left} 天免费试用即将结束，到期后将降级为 Free 方案。升级方案即可保留全部功能。',
                link='/settings/billing',
            )
        if users:
            logger.info("notify_trial_expiring: %s users notified for %s days left", users.count(), days_left)
