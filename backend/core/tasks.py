"""平台数据聚合任务。

每日凌晨运行，从各业务表聚合统计数据写入 DailyPlatformStats。
"""

from celery import shared_task
from django.db.models import Count, F, Q, Sum
from django.utils import timezone
from datetime import timedelta, date


@shared_task
def aggregate_daily_platform_stats():
    """聚合昨日平台数据，写入 DailyPlatformStats。"""
    from core.models import DailyPlatformStats, AnalyticsEvent
    from users.models import User, Institution
    from quizzes.models import QuizExam, ExamQuestionResult
    from courses.models import VideoProgress
    from users.models_commercial import InstitutionUsageLog

    today = timezone.now().date()
    yesterday = today - timedelta(days=1)

    # ── 用户 ──
    total_users = User.objects.count()
    new_users = User.objects.filter(date_joined__date=yesterday).count()

    # DAU / WAU / MAU: 一次查询用条件聚合
    stats = (
        AnalyticsEvent.objects
        .filter(
            event_type='user_login',
            created_at__date__gte=yesterday - timedelta(days=29),
        )
        .aggregate(
            dau=Count('user', distinct=True, filter=Q(created_at__date=yesterday)),
            wau=Count('user', distinct=True, filter=Q(created_at__date__gte=yesterday - timedelta(days=6))),
            mau=Count('user', distinct=True),
        )
    )
    dau = stats['dau']
    wau = stats['wau']
    mau = stats['mau']

    # ── 机构 ──
    total_institutions = Institution.objects.count()
    new_institutions = Institution.objects.filter(created_at__date=yesterday).count()
    active_institutions = (
        AnalyticsEvent.objects
        .filter(created_at__date=yesterday, institution__isnull=False)
        .values('institution')
        .distinct()
        .count()
    )

    # ── 学习 ──
    quiz_attempts = QuizExam.objects.filter(created_at__date=yesterday).count()

    # 正确率：从 ExamQuestionResult 聚合
    day_results = ExamQuestionResult.objects.filter(exam__created_at__date=yesterday)
    total_q = day_results.count()
    if total_q > 0:
        correct_q = day_results.filter(score__gte=F('max_score') * 0.6).count()
        quiz_correct_rate = correct_q / total_q
    else:
        quiz_correct_rate = 0

    diagnostic_completions = (
        AnalyticsEvent.objects
        .filter(event_type='diagnostic_complete', created_at__date=yesterday)
        .count()
    )

    # ── AI ──
    ai_chat_sessions = (
        AnalyticsEvent.objects
        .filter(event_type='ai_chat_start', created_at__date=yesterday)
        .count()
    )
    # 从 InstitutionUsageLog 聚合当月 AI 调用总量
    month_start = yesterday.replace(day=1)
    usage_agg = InstitutionUsageLog.objects.filter(
        period_start=month_start
    ).aggregate(total_ai=Sum('ai_call_total_count'))
    ai_calls_total = usage_agg.get('total_ai') or 0

    # ── 课程 ──
    course_views = (
        AnalyticsEvent.objects
        .filter(event_type='course_view', created_at__date=yesterday)
        .count()
    )
    course_completions = (
        AnalyticsEvent.objects
        .filter(event_type='course_complete', created_at__date=yesterday)
        .count()
    )
    pdf_exports = (
        AnalyticsEvent.objects
        .filter(event_type='pdf_export', created_at__date=yesterday)
        .count()
    )

    # ── 留存率 ──
    # 次日留存：前天登录的用户中，昨天也登录的比例
    day1_retention = _calc_retention(yesterday, days_back=1)
    day7_retention = _calc_retention(yesterday, days_back=7)
    day30_retention = _calc_retention(yesterday, days_back=30)

    # ── 写入 ──
    DailyPlatformStats.objects.update_or_create(
        date=yesterday,
        defaults={
            'total_users': total_users,
            'new_users': new_users,
            'dau': dau,
            'wau': wau,
            'mau': mau,
            'total_institutions': total_institutions,
            'new_institutions': new_institutions,
            'active_institutions': active_institutions,
            'quiz_attempts': quiz_attempts,
            'quiz_correct_rate': round(quiz_correct_rate, 4),
            'diagnostic_completions': diagnostic_completions,
            'ai_chat_sessions': ai_chat_sessions,
            'ai_calls_total': ai_calls_total,
            'course_views': course_views,
            'course_completions': course_completions,
            'pdf_exports': pdf_exports,
            'day1_retention': round(day1_retention, 4),
            'day7_retention': round(day7_retention, 4),
            'day30_retention': round(day30_retention, 4),
        },
    )
    return f"Aggregated stats for {yesterday}"


def _calc_retention(target_date, days_back):
    """计算留存率：days_back 天前登录的用户中，target_date 也登录的比例。"""
    from core.models import AnalyticsEvent

    cohort_date = target_date - timedelta(days=days_back)
    cohort_users = set(
        AnalyticsEvent.objects
        .filter(event_type='user_login', created_at__date=cohort_date)
        .values_list('user', flat=True)
    )
    if not cohort_users:
        return 0
    retained = (
        AnalyticsEvent.objects
        .filter(event_type='user_login', created_at__date=target_date, user__in=cohort_users)
        .values('user')
        .distinct()
        .count()
    )
    return retained / len(cohort_users)
