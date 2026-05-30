"""平台数据分析工具函数。

所有业务事件记录和分析逻辑集中在此模块。
仅超管可访问分析数据，严格隔离。
"""

from django.utils import timezone
from .models import AnalyticsEvent, NPSSurvey


def record_event(event_type, user=None, institution=None, properties=None):
    """记录业务事件，同步写入。

    轻量操作，单条 INSERT，不影响主流程性能。
    """
    if user and not institution:
        institution = getattr(user, 'institution', None)
    AnalyticsEvent.objects.create(
        event_type=event_type,
        user=user,
        institution=institution,
        properties=properties or {},
    )


def should_show_nps(user):
    """判断是否向用户展示 NPS 问卷。

    规则：
    1. 距上次填写超过 30 天
    2. 用户注册超过 7 天
    3. 本周至少有 3 天活跃（从 AnalyticsEvent 判断）
    """
    now = timezone.now()

    # 规则 1：30 天冷却
    last = NPSSurvey.objects.filter(user=user).order_by('-created_at').first()
    if last and (now - last.created_at).days < 30:
        return False

    # 规则 2：注册满 7 天
    if (now - user.date_joined).days < 7:
        return False

    # 规则 3：本周 3 天活跃
    week_ago = now - timezone.timedelta(days=7)
    active_days = (
        AnalyticsEvent.objects
        .filter(user=user, event_type='user_login', created_at__gte=week_ago)
        .dates('created_at', 'day')
        .count()
    )
    return active_days >= 3
