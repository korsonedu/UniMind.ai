"""平台数据分析工具函数。

所有业务事件记录和分析逻辑集中在此模块。
仅超管可访问分析数据，严格隔离。
"""

from .models import AnalyticsEvent


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
