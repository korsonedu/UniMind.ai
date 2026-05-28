import datetime
import random
from typing import Dict, List, Optional

from django.conf import settings
from django.db.models import Q, Sum
from django.utils import timezone

from quizzes.models import Question, UserQuestionStatus
from quizzes.utils import safe_int as _safe_int


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(value, upper))


def _bucket_targets(limit: int, preference: str = "balanced") -> Dict[str, int]:
    if preference == "new_first":
        due_ratio, risk_ratio, new_ratio = 0.20, 0.20, 0.60
    elif preference == "review_first":
        due_ratio, risk_ratio, new_ratio = 0.55, 0.35, 0.10
    else:  # balanced
        due_ratio, risk_ratio, new_ratio = 0.50, 0.30, 0.20

    due_target = max(1, round(limit * due_ratio))
    risk_target = max(1, round(limit * risk_ratio)) if limit > 1 else 0
    new_target = max(0, limit - due_target - risk_target)

    if due_target + risk_target + new_target > limit:
        overflow = due_target + risk_target + new_target - limit
        new_target = max(0, new_target - overflow)

    return {
        "due": due_target,
        "risk": risk_target,
        "new": new_target,
    }


def _select_ids(candidate_ids: List[int], target_count: int, selected_set: set, selected: List[int]) -> int:
    picked = 0
    for qid in candidate_ids:
        if picked >= target_count:
            break
        if qid in selected_set:
            continue
        selected.append(qid)
        selected_set.add(qid)
        picked += 1
    return picked


def build_adaptive_question_ids(
    user,
    limit: int = 10,
    base_queryset=None,
    preference: str = "balanced",
    now=None,
) -> Dict[str, object]:
    """
    preference: "balanced" | "new_first" | "review_first"
    """
    now = now or timezone.now()
    limit = _clamp(_safe_int(limit, 10), 1, 50)

    if base_queryset is None:
        base_queryset = Question.objects.all()

    candidate_subquery = base_queryset.values("id")

    status_qs = UserQuestionStatus.objects.filter(user=user, question_id__in=candidate_subquery)
    active_status_qs = status_qs.filter(is_mastered=False)

    mastered_ids_qs = status_qs.filter(is_mastered=True).values_list("question_id", flat=True)

    due_ids = list(
        active_status_qs.filter(next_review_at__lte=now)
        .order_by("next_review_at", "stability", "-wrong_count")
        .values_list("question_id", flat=True)
    )

    at_risk_window = now + datetime.timedelta(days=3)
    at_risk_ids = list(
        active_status_qs.filter(next_review_at__lte=at_risk_window)
        .exclude(question_id__in=due_ids)
        .filter(Q(wrong_count__gte=1) | Q(stability__lt=7) | Q(last_correct=False))
        .order_by("-wrong_count", "stability", "next_review_at")
        .values_list("question_id", flat=True)
    )

    reinforce_ids = list(
        active_status_qs.filter(wrong_count__gt=0)
        .exclude(question_id__in=due_ids)
        .exclude(question_id__in=at_risk_ids)
        .order_by("-wrong_count", "next_review_at")
        .values_list("question_id", flat=True)
    )

    attempted_ids_qs = status_qs.values_list("question_id", flat=True)

    new_pool_ids = list(
        base_queryset.exclude(id__in=attempted_ids_qs)
        .exclude(id__in=mastered_ids_qs)
        .values_list("id", flat=True)[: max(limit * 4, 40)]
    )
    random.shuffle(new_pool_ids)

    targets = _bucket_targets(limit, preference)

    selected: List[int] = []
    selected_set = set()

    picked_due = _select_ids(due_ids, targets["due"], selected_set, selected)
    picked_risk = _select_ids(at_risk_ids, targets["risk"], selected_set, selected)
    picked_new = _select_ids(new_pool_ids, targets["new"], selected_set, selected)

    picked_reinforce = 0
    if len(selected) < limit:
        picked_reinforce = _select_ids(reinforce_ids, limit - len(selected), selected_set, selected)

    if len(selected) < limit:
        future_ids = set(
            active_status_qs.filter(next_review_at__gt=now)
            .values_list("question_id", flat=True)
        )
        fallback_ids = list(
            base_queryset.exclude(id__in=mastered_ids_qs)
            .exclude(id__in=selected)
            .exclude(id__in=future_ids)
            .order_by("?")
            .values_list("id", flat=True)[: limit * 2]
        )
        _select_ids(fallback_ids, limit - len(selected), selected_set, selected)

    if len(selected) < limit:
        last_resort = list(
            base_queryset.exclude(id__in=mastered_ids_qs)
            .exclude(id__in=selected)
            .order_by("?")
            .values_list("id", flat=True)[: limit * 2]
        )
        _select_ids(last_resort, limit - len(selected), selected_set, selected)

    return {
        "question_ids": selected,
        "meta": {
            "requested_limit": limit,
            "actual_count": len(selected),
            "preference": preference,
            "targets": targets,
            "picked": {
                "due": picked_due,
                "risk": picked_risk,
                "new": picked_new,
                "reinforce": picked_reinforce,
            },
            "pool": {
                "due": len(due_ids),
                "risk": len(at_risk_ids),
                "new": len(new_pool_ids),
                "reinforce": len(reinforce_ids),
            },
        },
    }


def get_memorix_session_plan(user, minutes: int = 25, preferred_limit: Optional[int] = None) -> Dict[str, object]:
    now = timezone.now()
    minutes = _clamp(_safe_int(minutes, 25), 10, 120)

    status_qs = UserQuestionStatus.objects.filter(user=user)
    active_qs = status_qs.filter(is_mastered=False)

    due_count = active_qs.filter(next_review_at__lte=now).count()
    at_risk_count = active_qs.filter(
        stability__lt=7,
        next_review_at__lte=now + datetime.timedelta(days=3),
    ).count()
    weak_focus_count = active_qs.filter(Q(wrong_count__gte=2) | Q(last_correct=False)).count()

    attempted_ids = status_qs.values_list("question_id", flat=True)
    new_qs = Question.objects.exclude(id__in=attempted_ids)
    inst = getattr(user, 'institution', None)
    if inst:
        from django.db.models import Q
        new_qs = new_qs.filter(Q(institution=inst) | Q(institution__isnull=True))
    new_questions_count = new_qs.count()

    if preferred_limit is not None:
        recommended_questions = _clamp(_safe_int(preferred_limit, 10), 1, 50)
    else:
        minutes_per_q = getattr(settings, 'STUDY_MINUTES_PER_QUESTION', 2.8)
        base = _clamp(round(minutes / float(minutes_per_q)), 5, 40)
        recommended_questions = min(50, max(base, min(30, due_count)))

    targets = _bucket_targets(recommended_questions)

    top_weak_kps = list(
        active_qs.filter(wrong_count__gt=0, question__knowledge_point__isnull=False)
        .values("question__knowledge_point_id", "question__knowledge_point__name")
        .annotate(total_wrong=Sum("wrong_count"))
        .order_by("-total_wrong")[:3]
    )

    return {
        "minutes": minutes,
        "recommended_questions": recommended_questions,
        "estimated_minutes": int(round(recommended_questions * 2.8)),
        "review_goal": due_count,
        "at_risk_count": at_risk_count,
        "weak_focus_count": weak_focus_count,
        "new_questions": new_questions_count,
        "targets": targets,
        "top_weak_knowledge_points": [
            {
                "id": row["question__knowledge_point_id"],
                "name": row["question__knowledge_point__name"],
                "wrong_count": int(row["total_wrong"] or 0),
            }
            for row in top_weak_kps
        ],
    }
