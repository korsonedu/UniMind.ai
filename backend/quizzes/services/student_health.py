"""
学生健康度评分引擎 — 流失风险预测。

结合活动频率、Memorix 复习逾期、连续签到、学习趋势，
为学生生成 0-100 的综合健康分。
"""

from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Q, F


def compute_student_health(user) -> dict:
    """
    返回 {
        'score': 0-100,
        'level': 'healthy' | 'at_risk' | 'critical',
        'components': { recency, memorix, streak, trend },
        'details': { days_since_active, overdue_rate, current_streak, weekly_trend }
    }
    """
    now = timezone.now()
    components = {}
    details = {}

    # ── 1. 活跃度 (0-40) ──
    if user.last_active:
        days_since = (now - user.last_active).days
    else:
        days_since = (now - user.date_joined).days if user.date_joined else 30
    details['days_since_active'] = days_since

    if days_since <= 3:
        components['recency'] = 40
    elif days_since <= 7:
        components['recency'] = 30
    elif days_since <= 14:
        components['recency'] = 20
    elif days_since <= 30:
        components['recency'] = 10
    else:
        components['recency'] = 0

    # ── 2. Memorix 复习健康 (0-30) ──
    from quizzes.models import UserQuestionStatus
    statuses = UserQuestionStatus.objects.filter(user=user, stability__gt=0)
    total = statuses.count()
    if total > 0:
        overdue = statuses.filter(next_review_at__lt=now).count()
        overdue_rate = overdue / total
    else:
        overdue_rate = 0
    details['overdue_rate'] = round(overdue_rate, 3)

    if overdue_rate <= 0.1:
        components['memorix'] = 30
    elif overdue_rate <= 0.25:
        components['memorix'] = 20
    elif overdue_rate <= 0.5:
        components['memorix'] = 10
    else:
        components['memorix'] = 0

    # ── 3. 连续签到 (0-20) ──
    from users.models import DailyCheckIn
    latest_checkin = DailyCheckIn.objects.filter(user=user).order_by('-date').first()
    streak = latest_checkin.streak if latest_checkin else 0
    details['current_streak'] = streak

    if streak >= 7:
        components['streak'] = 20
    elif streak >= 3:
        components['streak'] = 15
    elif streak >= 1:
        components['streak'] = 10
    else:
        components['streak'] = 0

    # ── 4. 学习趋势 (0-10) ──
    from quizzes.models import ReviewLog
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)
    this_week = ReviewLog.objects.filter(user=user, review_time__gte=week_ago).count()
    last_week = ReviewLog.objects.filter(
        user=user, review_time__gte=two_weeks_ago, review_time__lt=week_ago
    ).count()
    if last_week == 0 and this_week == 0:
        trend = 'flat'
    elif last_week == 0:
        trend = 'up'
    else:
        ratio = this_week / max(last_week, 1)
        if ratio >= 1.2:
            trend = 'up'
        elif ratio >= 0.7:
            trend = 'flat'
        else:
            trend = 'down'
    details['weekly_trend'] = trend
    details['this_week_reviews'] = this_week
    details['last_week_reviews'] = last_week

    if trend == 'up':
        components['trend'] = 10
    elif trend == 'flat':
        components['trend'] = 5
    else:
        components['trend'] = 0

    score = sum(components.values())

    if score >= 70:
        level = 'healthy'
    elif score >= 40:
        level = 'at_risk'
    else:
        level = 'critical'

    return {
        'score': score,
        'level': level,
        'components': components,
        'details': details,
    }


def compute_institution_student_health(institution) -> list[dict]:
    """为机构内所有学员计算健康度，返回按风险排序的列表。"""
    students = institution.students.filter(institution_role='student').select_related('institution')
    results = []
    for s in students:
        health = compute_student_health(s)
        results.append({
            'student_id': s.id,
            'name': s.nickname or s.username,
            'email': s.email,
            'avatar_url': getattr(s, 'avatar_url', None),
            'date_joined': s.date_joined.isoformat() if s.date_joined else None,
            'last_active': s.last_active.isoformat() if s.last_active else None,
            **health,
        })
    results.sort(key=lambda x: x['score'])
    return results
