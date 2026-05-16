from django.utils import timezone
from django.db.models import F

FREE_AI_QUOTA_LIMIT = 20  # Free 版每月 20 次 AI 出题


def get_current_period_start():
    """当月第一天"""
    now = timezone.now()
    return now.replace(day=1).date()


def check_ai_quota(institution) -> bool:
    """
    检查机构是否还有 AI 出题配额。
    Free 版每月 20 次，Solo/Plus/Pro 无限制。
    无 institution 的独立用户也视为无配额。
    """
    from users.models_commercial import InstitutionUsageLog
    if institution is None:
        return False
    if institution.plan != 'free':
        return True
    usage, _ = InstitutionUsageLog.objects.get_or_create(
        institution=institution,
        period_start=get_current_period_start(),
    )
    return usage.ai_generation_count < FREE_AI_QUOTA_LIMIT


def increment_ai_quota(institution):
    """AI 出题成功后，递增当月计数。原子操作，超过配额时不会递增。"""
    from users.models_commercial import InstitutionUsageLog
    if institution is None or institution.plan != 'free':
        return
    from django.db import transaction
    with transaction.atomic():
        usage = InstitutionUsageLog.objects.select_for_update().get_or_create(
            institution=institution,
            period_start=get_current_period_start(),
        )[0]
        if usage.ai_generation_count < FREE_AI_QUOTA_LIMIT:
            usage.ai_generation_count = F('ai_generation_count') + 1
            usage.save(update_fields=['ai_generation_count'])


def get_ai_quota_info(institution):
    """
    返回 AI 配额信息 {used, limit}。
    limit=None 表示无限制。
    """
    from users.models_commercial import InstitutionUsageLog
    if institution is None:
        return {'used': 0, 'limit': 0}
    if institution.plan != 'free':
        return {'used': 0, 'limit': None}
    usage, _ = InstitutionUsageLog.objects.get_or_create(
        institution=institution,
        period_start=get_current_period_start(),
    )
    return {
        'used': usage.ai_generation_count,
        'limit': FREE_AI_QUOTA_LIMIT,
    }
