import logging
from datetime import timedelta

from celery import shared_task
from django.contrib.auth import get_user_model
from django.db.models import F
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
def elo_decay_daily():
    """每日 ELO 衰减：超过 30 天未登录的活跃用户每天衰减 2 分。"""
    now = timezone.now()
    threshold = now - timedelta(days=30)

    decayed = User.objects.filter(
        is_active=True,
        is_member=False,  # 付费会员不衰减 ELO
        last_login__lt=threshold,
        elo_score__gt=800,
    ).update(
        elo_score=F('elo_score') - 2,
    )

    if decayed > 0:
        logger.info("elo_decay_daily: %s users decayed", decayed)


@shared_task
def elo_decay_weekly():
    """每周 ELO 重置衰减：超过 60 天未登录的用户额外衰减 10 分。"""
    now = timezone.now()
    threshold = now - timedelta(days=60)

    decayed = User.objects.filter(
        is_active=True,
        is_member=False,  # 付费会员不衰减 ELO
        last_login__lt=threshold,
        elo_score__gt=800,
    ).update(
        elo_score=F('elo_score') - 10,
    )

    if decayed > 0:
        logger.info("elo_decay_weekly: %s users deep-decayed", decayed)
