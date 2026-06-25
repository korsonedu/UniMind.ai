"""
学生健康度评分引擎 — 流失风险预测。

结合活动频率、Memorix 复习逾期、连续签到、学习趋势，
为学生生成 0-100 的综合健康分。
"""

from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db.models import Count, Q, F, Subquery, OuterRef
from quizzes.models import UserQuestionStatus, ReviewLog
from users.models import DailyCheckIn


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
    """为机构内所有学员计算健康度，返回按风险排序的列表。

    使用批量聚合查询替代逐学生循环，避免 N+1 问题。
    原来 500 学生 ≈ 3500 次查询 → 现在固定 4 次查询。
    """
    User = get_user_model()
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    students = list(institution.students.filter(
        institution_role='student'
    ).select_related('institution'))

    if not students:
        return []

    student_ids = [s.id for s in students]

    # ── Batch 1: UserQuestionStatus 聚合（Memorix 复习逾期率）──
    status_agg = UserQuestionStatus.objects.filter(
        user_id__in=student_ids,
        stability__gt=0,
    ).values('user_id').annotate(
        total_stable=Count('id'),
        overdue=Count('id', filter=Q(next_review_at__lt=now)),
    )
    status_map = {item['user_id']: item for item in status_agg}

    # ── Batch 2: ReviewLog 聚合（本周/上周趋势）──
    reviews_agg = ReviewLog.objects.filter(
        user_id__in=student_ids,
        review_time__gte=two_weeks_ago,
    ).values('user_id').annotate(
        this_week=Count('id', filter=Q(review_time__gte=week_ago)),
        last_week=Count('id', filter=Q(review_time__gte=two_weeks_ago, review_time__lt=week_ago)),
    )
    reviews_map = {item['user_id']: item for item in reviews_agg}

    # ── Batch 3: DailyCheckIn 最新连续签到 ──
    latest_streak_subq = DailyCheckIn.objects.filter(
        user=OuterRef('pk'),
    ).order_by('-date').values('streak')[:1]

    streaks = User.objects.filter(id__in=student_ids).annotate(
        current_streak=Subquery(latest_streak_subq)
    ).values('id', 'current_streak')
    streak_map = {item['id']: item['current_streak'] for item in streaks}

    # ── 计算评分 ──
    results = []
    for s in students:
        # 活跃度
        if s.last_active:
            days_since = (now - s.last_active).days
        else:
            days_since = (now - s.date_joined).days if s.date_joined else 30

        if days_since <= 3:
            recency = 40
        elif days_since <= 7:
            recency = 30
        elif days_since <= 14:
            recency = 20
        elif days_since <= 30:
            recency = 10
        else:
            recency = 0

        # Memorix 复习逾期率
        st = status_map.get(s.id)
        if st and st['total_stable'] > 0:
            overdue_rate = st['overdue'] / st['total_stable']
        else:
            overdue_rate = 0

        if overdue_rate <= 0.1:
            memorix = 30
        elif overdue_rate <= 0.25:
            memorix = 20
        elif overdue_rate <= 0.5:
            memorix = 10
        else:
            memorix = 0

        # 连续签到
        current_streak = streak_map.get(s.id) or 0
        if current_streak >= 7:
            streak_score = 20
        elif current_streak >= 3:
            streak_score = 15
        elif current_streak >= 1:
            streak_score = 10
        else:
            streak_score = 0

        # 学习趋势
        rw = reviews_map.get(s.id)
        this_week_count = rw['this_week'] if rw else 0
        last_week_count = rw['last_week'] if rw else 0

        if last_week_count == 0 and this_week_count == 0:
            trend = 'flat'
        elif last_week_count == 0:
            trend = 'up'
        else:
            ratio = this_week_count / max(last_week_count, 1)
            if ratio >= 1.2:
                trend = 'up'
            elif ratio >= 0.7:
                trend = 'flat'
            else:
                trend = 'down'

        if trend == 'up':
            trend_score = 10
        elif trend == 'flat':
            trend_score = 5
        else:
            trend_score = 0

        score = recency + memorix + streak_score + trend_score

        if score >= 70:
            level = 'healthy'
        elif score >= 40:
            level = 'at_risk'
        else:
            level = 'critical'

        results.append({
            'student_id': s.id,
            'name': s.nickname or s.username,
            'email': s.email,
            'avatar_url': getattr(s, 'avatar_url', None),
            'date_joined': s.date_joined.isoformat() if s.date_joined else None,
            'last_active': s.last_active.isoformat() if s.last_active else None,
            'score': score,
            'level': level,
            'components': {
                'recency': recency,
                'memorix': memorix,
                'streak': streak_score,
                'trend': trend_score,
            },
            'details': {
                'days_since_active': days_since,
                'overdue_rate': round(overdue_rate, 3),
                'current_streak': current_streak,
                'weekly_trend': trend,
                'this_week_reviews': this_week_count,
                'last_week_reviews': last_week_count,
            },
        })

    results.sort(key=lambda x: x['score'])
    return results
