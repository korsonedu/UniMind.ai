import datetime
from typing import Dict, List

from django.utils import timezone

from quizzes.models import KnowledgePoint, ReviewLog, UserKnowledgeState
from study_room.models import StudyPlan, WeeklyTask


def _clamp_0_1(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _normalize_elo(elo_score: int) -> float:
    # 以 800-1800 为主工作区间做线性归一化。
    try:
        val = float(elo_score)
    except Exception:
        return 0.0
    return _clamp_0_1((val - 800.0) / 1000.0)


def build_macro_progress(user, plan: StudyPlan | None) -> Dict:
    today = timezone.localdate()
    kp_qs = KnowledgePoint.objects.filter(level="kp")
    total_kp = kp_qs.count()

    state_qs = UserKnowledgeState.objects.filter(user=user).select_related("knowledge_point")
    mastered_states = state_qs.filter(mastery_score__gte=0.6)
    weak_states = state_qs.filter(mastery_score__lt=0.6).order_by("mastery_score", "updated_at")[:5]

    w_total = float(total_kp)
    w_done = float(mastered_states.count())
    w_remain = max(0.0, w_total - w_done)

    # 近 7 日真实学习速率：按复习日志触达过的考点数量估算。
    week_ago = timezone.now() - datetime.timedelta(days=7)
    recent_kp_count = (
        ReviewLog.objects.filter(user=user, review_time__gte=week_ago)
        .values("knowledge_point_id")
        .distinct()
        .count()
    )
    actual_rate = float(recent_kp_count) / 7.0 if recent_kp_count > 0 else 0.0

    days_to_exam = None
    ideal_rate = 0.0
    status_light = "未设定"
    lag_days = 0.0
    if plan:
        days_to_exam = (plan.target_date - today).days
        if days_to_exam > 0:
            ideal_rate = w_remain / float(days_to_exam)
            status_light = "green" if actual_rate >= ideal_rate else "red"
            if actual_rate > 0:
                lag_days = max(0.0, (ideal_rate - actual_rate) * 7.0 / actual_rate)
        else:
            status_light = "red"

    # 阻塞节点回溯：薄弱节点且其父节点也薄弱时视作阻塞链路。
    state_map = {s.knowledge_point_id: float(s.mastery_score or 0.0) for s in state_qs}
    bottlenecks: List[Dict] = []
    for item in weak_states:
        kp = item.knowledge_point
        if not kp or not kp.parent_id:
            continue
        parent_score = float(state_map.get(kp.parent_id, 1.0))
        if parent_score >= 0.6:
            continue
        bottlenecks.append(
            {
                "knowledge_point_id": kp.id,
                "knowledge_point_name": kp.name,
                "knowledge_point_score": round(float(item.mastery_score or 0.0), 4),
                "parent_id": kp.parent_id,
                "parent_name": kp.parent.name if kp.parent else "",
                "parent_score": round(parent_score, 4),
            }
        )

    weak_nodes = [
        {
            "knowledge_point_id": row.knowledge_point_id,
            "knowledge_point_name": row.knowledge_point.name if row.knowledge_point else "",
            "mastery_score": round(float(row.mastery_score or 0.0), 4),
        }
        for row in weak_states
    ]

    return {
        "plan": {
            "target_date": getattr(plan, "target_date", None),
            "target_score": getattr(plan, "target_score", None),
            "daily_hours": getattr(plan, "daily_hours", None),
            "weekly_summary": getattr(plan, "weekly_summary", None),
        },
        "metrics": {
            "days_to_exam": days_to_exam,
            "w_total": round(w_total, 2),
            "w_done": round(w_done, 2),
            "w_remain": round(w_remain, 2),
            "ideal_rate": round(ideal_rate, 4),
            "actual_rate": round(actual_rate, 4),
            "status_light": status_light,
            "lag_days": round(lag_days, 2),
            "elo_normalized": round(_normalize_elo(getattr(user, "elo_score", 1000)), 4),
        },
        "weak_nodes": weak_nodes,
        "bottlenecks": bottlenecks[:5],
    }


def build_weekly_tasks_payload(user, plan: StudyPlan | None) -> Dict:
    base = build_macro_progress(user=user, plan=plan)
    tasks = WeeklyTask.objects.filter(user=user).order_by("-created_at")[:100]
    items = [
        {
            "id": row.id,
            "title": row.title,
            "description": row.description,
            "status": row.status,
            "knowledge_point_id": row.knowledge_point_id,
            "knowledge_point_name": row.knowledge_point.name if row.knowledge_point else "",
            "week_start": row.week_start,
            "week_end": row.week_end,
            "created_at": row.created_at,
        }
        for row in tasks
    ]
    return {
        **base,
        "tasks": items,
        "task_summary": {
            "pending": sum(1 for t in items if t["status"] == "pending"),
            "in_progress": sum(1 for t in items if t["status"] == "in_progress"),
            "completed": sum(1 for t in items if t["status"] == "completed"),
            "total": len(items),
        },
    }
