"""统一学习统计口径。

已练题只统计 reps > 0 的 UserQuestionStatus，排除仅收藏、考试预建、
诊断预建等零作答行。最近正确率按每题最后一次作答计算；累计正确率
按复习次数与错误次数估算，仅作近似参考。
"""

from datetime import timedelta
from typing import Optional

from django.db.models import Avg, Q, Sum
from django.utils import timezone


def _scoped_status_qs(user, *, institution=None, date_from=None, date_to=None):
    from quizzes.models import UserQuestionStatus

    qs = UserQuestionStatus.objects.filter(user=user, reps__gt=0)
    if institution is not None:
        qs = qs.filter(question__institution=institution)
    if date_from and date_to:
        qs = qs.filter(last_review__range=(date_from, date_to))
    return qs


def _study_streak_days(user, anchor_date, date_from=None) -> int:
    from quizzes.models import ReviewLog

    lookback = anchor_date - timedelta(days=30)
    if date_from:
        lookback = max(lookback, date_from.date())
    review_days = (
        ReviewLog.objects.filter(
            user=user,
            review_time__date__gte=lookback,
            review_time__date__lte=anchor_date,
        )
        .values_list('review_time__date', flat=True)
        .distinct()
    )
    streak = 0
    check_date = anchor_date
    for day in sorted(set(review_days), reverse=True):
        if day == check_date:
            streak += 1
            check_date -= timedelta(days=1)
        elif day < check_date:
            break
    return streak


def build_mastery_summary(user, *, institution=None) -> dict:
    """诊断掌握度汇总。mastery_score 范围为 0-100。"""
    from quizzes.models import UserKnowledgeState

    qs = UserKnowledgeState.objects.filter(user=user)
    if institution is not None:
        qs = qs.filter(
            Q(knowledge_point__institution=institution)
            | Q(knowledge_point__institution__isnull=True)
        )
    agg = qs.aggregate(avg=Avg('mastery_score'))
    latest = qs.order_by('-updated_at').values_list('updated_at', flat=True).first()
    return {
        'source': 'diagnostic',
        'kp_count': qs.count(),
        'mastered_kp_count': qs.filter(mastery_score__gte=80).count(),
        'avg_mastery': round(agg['avg'], 1) if agg['avg'] is not None else None,
        'updated_at': latest.isoformat() if latest else None,
    }


def build_learning_stats(
    user,
    *,
    institution=None,
    date_from=None,
    date_to=None,
) -> dict:
    """返回学习统计。无已练题时正确率为 None，由调用方决定如何展示。"""
    qs = _scoped_status_qs(
        user, institution=institution, date_from=date_from, date_to=date_to,
    )
    agg = qs.aggregate(
        total_attempts=Sum('reps'),
        wrong_attempts=Sum('wrong_count'),
    )
    attempted_questions = qs.count()
    total_attempts = agg['total_attempts'] or 0
    wrong_attempts = agg['wrong_attempts'] or 0
    last_correct_count = qs.filter(last_correct=True).count()

    subjects = list(
        qs.filter(question__knowledge_point__isnull=False)
        .exclude(question__knowledge_point__subject__isnull=True)
        .exclude(question__knowledge_point__subject='')
        .values_list('question__knowledge_point__subject', flat=True)
        .distinct()
        .order_by('question__knowledge_point__subject')
    )
    unclassified_questions = qs.filter(
        Q(question__knowledge_point__isnull=True)
        | Q(question__knowledge_point__subject__isnull=True)
        | Q(question__knowledge_point__subject='')
    ).count()

    last_accuracy = (
        round(last_correct_count / attempted_questions * 100, 1)
        if attempted_questions else None
    )
    lifetime_accuracy = (
        round(max(total_attempts - wrong_attempts, 0) / total_attempts * 100, 1)
        if total_attempts else None
    )
    anchor_date = date_to.date() if date_to else timezone.localdate()

    return {
        'attempted_questions': attempted_questions,
        'total_attempts': total_attempts,
        'last_correct_count': last_correct_count,
        'last_accuracy': last_accuracy,
        'lifetime_correct_count': max(total_attempts - wrong_attempts, 0),
        'lifetime_accuracy': lifetime_accuracy,
        'wrong_question_count': qs.filter(wrong_count__gt=0).count(),
        'wrong_attempts': wrong_attempts,
        'mastered_question_count': qs.filter(is_mastered=True).count(),
        'subjects': subjects,
        'subject_count': len(subjects),
        'unclassified_questions': unclassified_questions,
        'study_streak_days': _study_streak_days(user, anchor_date, date_from),
        'mastery': build_mastery_summary(user, institution=institution),
        'has_attempts': attempted_questions > 0,
        'is_new_user': attempted_questions == 0,
        'accuracy_basis': 'last_attempt',
        'date_filter': (
            {
                'from': date_from.isoformat() if hasattr(date_from, 'isoformat') else str(date_from),
                'to': date_to.isoformat() if hasattr(date_to, 'isoformat') else str(date_to),
                'basis': 'last_review',
            }
            if date_from and date_to else None
        ),
        # 兼容旧消费方的字段名
        'total_questions_attempted': attempted_questions,
        'correct_count': last_correct_count,
        'accuracy': last_accuracy or 0,
        'wrong_count': qs.filter(wrong_count__gt=0).count(),
        'subjects_with_progress': len(subjects),
        'suggested_action': 'diagnostic_test' if attempted_questions == 0 else None,
        'diagnostic_url': '/diagnostic' if attempted_questions == 0 else None,
    }
