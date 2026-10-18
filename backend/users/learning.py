from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from .models import (LearningGrant, CourseStudentStatus, WeeklyAIQuotaConfig,
                     AIAddonGrant, WeeklyAIUsage, AIUsageReservation)


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


def is_course_student(user):
    status = CourseStudentStatus.objects.filter(user=user).values_list('is_course_student', flat=True).first()
    if status is not None:
        return status
    # Historical grants remain evidence of existing access until an administrator decides.
    return has_legacy_membership(user) or active_grants(user).exists()


@transaction.atomic
def set_course_student_status(user, is_student, *, actor=None):
    get_user_model().objects.select_for_update().get(pk=user.pk)
    status, _ = CourseStudentStatus.objects.update_or_create(
        user=user, defaults={'is_course_student': bool(is_student), 'updated_by': actor})
    return status


def get_weekly_quota_config():
    return WeeklyAIQuotaConfig.objects.get_or_create(pk=1)[0]


def set_weekly_quota_config(*, experience_calls, course_calls, actor=None):
    from django.core.exceptions import ValidationError
    if (experience_calls is None) != (course_calls is None):
        raise ValidationError('请同时配置两类周额度，或同时留空。')
    if experience_calls is not None and (type(experience_calls) is not int or type(course_calls) is not int
                                        or experience_calls < 0 or course_calls <= experience_calls):
        raise ValidationError('课程学员周额度必须高于非课程学员，且均为非负整数。')
    config = get_weekly_quota_config()
    config.experience_calls, config.course_calls, config.updated_by = experience_calls, course_calls, actor
    config.save()
    return config


def ai_limit(user):
    from .permissions import is_platform_admin
    if is_platform_admin(user):
        return None
    config = get_weekly_quota_config()
    return config.course_calls if is_course_student(user) else config.experience_calls


def week_bounds(now=None):
    from zoneinfo import ZoneInfo
    now = timezone.localtime(now or timezone.now(), ZoneInfo('Asia/Shanghai'))
    start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return start.date(), start + timedelta(days=7)


def active_addons(user):
    now = timezone.now()
    return AIAddonGrant.objects.filter(user=user, starts_at__lte=now, expires_at__gt=now)


def _release_stale_reservations(user):
    # A killed process cannot execute its finally block. Keep abandoned requests
    # from consuming base or purchased capacity indefinitely.
    cutoff = timezone.now() - timedelta(hours=1)
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=user.pk)
        AIUsageReservation.objects.filter(user=user, status='pending', updated_at__lt=cutoff).update(
            status='released', response={}, updated_at=timezone.now())


def usage_info(user):
    from .permissions import is_platform_admin
    _release_stale_reservations(user)
    week, resets_at = week_bounds()
    used = WeeklyAIUsage.objects.filter(user=user, week=week).values_list('ai_calls', flat=True).first() or 0
    limit = ai_limit(user)
    unlimited = is_platform_admin(user)
    configured = unlimited or limit is not None
    pending = AIUsageReservation.objects.filter(user=user, week=week, status='pending', addon__isnull=True, unlimited=False).count()
    base_remaining = None if unlimited else max(0, (limit or 0) - used - pending)
    addon_remaining = sum(max(0, grant.ai_calls - grant.used_calls - grant.reservations.filter(status='pending').count())
                          for grant in active_addons(user))
    remaining = None if unlimited else base_remaining + addon_remaining
    return {'used': used, 'limit': limit, 'remaining': remaining, 'base_remaining': base_remaining,
            'addon_remaining': addon_remaining, 'resets_at': resets_at.isoformat(), 'configured': configured,
            'unlimited': unlimited, 'pct': min(100, round(used / limit * 100)) if limit else 0,
            'status': 'unconfigured' if not configured else 'exhausted' if remaining == 0 else 'normal'}


@transaction.atomic
def reserve_ai_call(user, request_id=None, *, fingerprint=''):
    from uuid import UUID, uuid4
    from rest_framework.exceptions import ValidationError
    from .permissions import is_platform_admin
    try:
        request_id = UUID(str(request_id)) if request_id else uuid4()
    except (ValueError, TypeError, AttributeError):
        raise ValidationError({'request_id': '请求标识必须为 UUID。'})
    get_user_model().objects.select_for_update().get(pk=user.pk)
    _release_stale_reservations(user)
    existing = AIUsageReservation.objects.filter(user=user, request_id=request_id).first()
    if existing and existing.fingerprint != fingerprint:
        raise ValidationError({'request_id': '该请求标识已用于另一条提问。'})
    if existing and existing.status != 'released':
        existing.acquired = False
        return existing
    week, _ = week_bounds()
    limit = ai_limit(user)
    unlimited = is_platform_admin(user)
    usage, _ = WeeklyAIUsage.objects.get_or_create(user=user, week=week)
    pending = AIUsageReservation.objects.filter(user=user, week=week, status='pending', addon__isnull=True, unlimited=False).count()
    addon = None
    if not unlimited and (limit is None or usage.ai_calls + pending >= limit):
        for candidate in active_addons(user).order_by('expires_at', 'id'):
            if candidate.used_calls + candidate.reservations.filter(status='pending').count() < candidate.ai_calls:
                addon = candidate
                break
        if addon is None:
            message = 'AI 周额度尚未配置，请联系我们。' if limit is None else '本周 AI 问答额度已用完，请等待下周恢复或联系我们，也可在我的服务查看 AI 加量。'
            raise PermissionDenied(message)
    values = {'attempt_id': uuid4(), 'week': week, 'status': 'pending', 'addon': addon,
              'unlimited': unlimited, 'response': {}, 'fingerprint': fingerprint}
    if existing:
        for key, value in values.items():
            setattr(existing, key, value)
        existing.save()
        reservation = existing
    else:
        reservation = AIUsageReservation.objects.create(user=user, request_id=request_id, **values)
    reservation.acquired = True
    return reservation


@transaction.atomic
def finish_ai_call(reservation, *, success, response=None):
    get_user_model().objects.select_for_update().get(pk=reservation.user_id)
    _release_stale_reservations(reservation.user)
    current = AIUsageReservation.objects.get(pk=reservation.pk)
    if current.attempt_id != reservation.attempt_id or current.status != 'pending':
        return current
    if success:
        if current.addon_id:
            AIAddonGrant.objects.filter(pk=current.addon_id).update(used_calls=F('used_calls') + 1)
        else:
            WeeklyAIUsage.objects.filter(user_id=current.user_id, week=current.week).update(ai_calls=F('ai_calls') + 1)
    current.status = 'succeeded' if success else 'released'
    current.response = response or {}
    current.save(update_fields=['status', 'response', 'updated_at'])
    return current


def confirm_ai_call(reservation, response=None):
    return finish_ai_call(reservation, success=True, response=response)


def release_ai_call(reservation):
    return finish_ai_call(reservation, success=False)


@transaction.atomic
def grant_ai_addon(order):
    details = order.entitlement_snapshot
    if details.get('kind') != 'ai_addon' or not order.ai_addon_product_id:
        raise ValueError('订单不包含 AI 加量快照。')
    calls, days = details.get('ai_calls'), details.get('validity_days')
    if type(calls) is not int or calls < 1 or type(days) is not int or days < 1:
        raise ValueError('订单的 AI 加量交付参数不完整。')
    get_user_model().objects.select_for_update().get(pk=order.user_id)
    now = timezone.now()
    return AIAddonGrant.objects.get_or_create(order=order, defaults={
        'user': order.user, 'product_id': order.ai_addon_product_id, 'snapshot': details,
        'ai_calls': calls, 'starts_at': now, 'expires_at': now + timedelta(days=days),
    })[0]


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
