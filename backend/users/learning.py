from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from .models import LearningGrant, LearningUsage


LEARNING_FEATURES = [
    'quiz.manual', 'quiz.exam', 'wrong.review', 'basic.stats', 'full.report',
    'memorix.review', 'ai.assistant', 'course.video',
    'video.outline', 'faq.system', 'study.room', 'pdf.mock',
]


def active_grants(user):
    now = timezone.now()
    return LearningGrant.objects.filter(user=user, revoked=False, starts_at__lte=now, expires_at__gt=now)


def has_legacy_membership(user):
    return user.is_member and (user.membership_expires_at is None or user.membership_expires_at > timezone.now())


def ai_limit(user):
    limit = settings.LEARNING_FREE_AI_CALLS_PER_MONTH
    for grant in active_grants(user):
        limit = max(limit, grant.snapshot.get('monthly_ai_calls', 0))
    if has_legacy_membership(user):
        from .quota import PLAN_QUOTA_LIMITS
        plan = user.personal_plan if user.personal_plan != 'free' else user.membership_tier
        legacy_limits = PLAN_QUOTA_LIMITS.get(plan, {})
        legacy_limit = legacy_limits.get('ai_call_total')
        if 'ai_call_total' in legacy_limits and legacy_limit is None:
            return None
        if legacy_limit is not None:
            limit = max(limit, legacy_limit)
    return limit


def usage_info(user):
    month = timezone.localdate().replace(day=1)
    used = LearningUsage.objects.filter(user=user, month=month).values_list('ai_calls', flat=True).first() or 0
    limit = ai_limit(user)
    return {'used': used, 'limit': limit, 'pct': min(100, round(used / limit * 100)) if limit else 0,
            'status': 'exhausted' if limit is not None and used >= limit else 'normal'}


def reserve_ai_call(user):
    limit = ai_limit(user)
    with transaction.atomic():
        # Lock the user as well, including the first request of a new month.
        get_user_model().objects.select_for_update().get(pk=user.pk)
        usage, _ = LearningUsage.objects.get_or_create(user=user, month=timezone.localdate().replace(day=1))
        if limit is not None and usage.ai_calls >= limit:
            raise PermissionDenied('本月 AI 额度已用完，可在学习服务中查看可用权益。')
        LearningUsage.objects.filter(pk=usage.pk).update(ai_calls=F('ai_calls') + 1)


@transaction.atomic
def grant_product(user, product, *, source, order=None, snapshot=None):
    details = snapshot if snapshot is not None else product.snapshot()
    now = timezone.now()
    get_user_model().objects.select_for_update().get(pk=user.pk)
    if order:
        existing = LearningGrant.objects.filter(order=order).first()
        if existing:
            return existing
    previous_expiry = active_grants(user).filter(product=product).order_by('-expires_at').values_list('expires_at', flat=True).first()
    expires_at = max(now, previous_expiry or now) + timedelta(days=details['duration_days'])
    if order:
        grant, _ = LearningGrant.objects.get_or_create(order=order, defaults={
            'user': user, 'product': product, 'snapshot': details, 'source': source,
            'starts_at': now, 'expires_at': expires_at,
        })
        return grant
    return LearningGrant.objects.create(user=user, product=product, snapshot=details, source=source,
                                        starts_at=now, expires_at=expires_at)
