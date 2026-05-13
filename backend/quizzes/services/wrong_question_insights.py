from collections import defaultdict
from typing import Dict, List

from quizzes.models import ExamQuestionResult, UserQuestionStatus
from quizzes.services.review_insights import CAUSE_LABELS, infer_primary_cause


DEFAULT_CAUSE = "expression"


def _pick_latest_wrong_cause_by_question(user, question_ids: List[int]) -> Dict[int, str]:
    latest_results = (
        ExamQuestionResult.objects.filter(
            exam__user=user,
            is_correct=False,
            question_id__in=question_ids,
        )
        .select_related("exam")
        .order_by("question_id", "-exam__created_at", "-id")
    )

    cause_by_question: Dict[int, str] = {}
    for row in latest_results:
        if row.question_id in cause_by_question:
            continue
        cause_by_question[row.question_id] = infer_primary_cause(row.feedback, row.analysis)
    return cause_by_question


def build_wrong_question_insights(user, top_k: int = 3) -> Dict[str, object]:
    statuses = list(
        UserQuestionStatus.objects.filter(user=user, wrong_count__gt=0)
        .select_related("question__knowledge_point")
        .order_by("-wrong_count", "question_id")
    )
    if not statuses:
        return {
            "overview": {
                "wrong_questions": 0,
                "wrong_attempts": 0,
            },
            "cause_breakdown": [],
            "knowledge_point_breakdown": [],
            "recommended_drills": [],
        }

    question_ids = [status.question_id for status in statuses]
    cause_by_question = _pick_latest_wrong_cause_by_question(user=user, question_ids=question_ids)

    cause_bucket = defaultdict(lambda: {"question_ids": [], "wrong_attempts": 0, "question_count": 0})
    kp_bucket = defaultdict(
        lambda: {"knowledge_point_id": None, "knowledge_point_name": "未归类考点", "question_ids": [], "wrong_attempts": 0}
    )

    total_wrong_attempts = 0
    for status in statuses:
        total_wrong_attempts += int(status.wrong_count or 0)
        qid = status.question_id
        cause_key = cause_by_question.get(qid, DEFAULT_CAUSE)
        cause_item = cause_bucket[cause_key]
        cause_item["question_ids"].append(qid)
        cause_item["wrong_attempts"] += int(status.wrong_count or 0)
        cause_item["question_count"] += 1

        kp = status.question.knowledge_point
        kp_key = kp.id if kp else "unknown"
        kp_item = kp_bucket[kp_key]
        kp_item["knowledge_point_id"] = kp.id if kp else None
        kp_item["knowledge_point_name"] = kp.name if kp else "未归类考点"
        kp_item["question_ids"].append(qid)
        kp_item["wrong_attempts"] += int(status.wrong_count or 0)

    total_wrong_questions = len(statuses)
    cause_breakdown = []
    for cause_key, item in cause_bucket.items():
        cause_breakdown.append(
            {
                "cause_key": cause_key,
                "cause_label": CAUSE_LABELS.get(cause_key, cause_key),
                "question_count": item["question_count"],
                "wrong_attempts": item["wrong_attempts"],
                "ratio": round(item["question_count"] / total_wrong_questions, 4) if total_wrong_questions else 0,
                "question_ids": item["question_ids"],
            }
        )
    cause_breakdown.sort(key=lambda x: (-x["question_count"], -x["wrong_attempts"]))

    knowledge_point_breakdown = []
    for _, item in kp_bucket.items():
        question_count = len(item["question_ids"])
        knowledge_point_breakdown.append(
            {
                "knowledge_point_id": item["knowledge_point_id"],
                "knowledge_point_name": item["knowledge_point_name"],
                "question_count": question_count,
                "wrong_attempts": item["wrong_attempts"],
                "avg_wrong_count": round(item["wrong_attempts"] / question_count, 2) if question_count else 0,
                "question_ids": item["question_ids"],
            }
        )
    knowledge_point_breakdown.sort(key=lambda x: (-x["question_count"], -x["wrong_attempts"]))

    recommended_drills = []
    for cause_item in cause_breakdown[:top_k]:
        question_ids_for_drill = cause_item["question_ids"][:10]
        recommended_drills.append(
            {
                "drill_type": "cause",
                "drill_key": cause_item["cause_key"],
                "drill_label": f"{cause_item['cause_label']}专项",
                "question_count": len(question_ids_for_drill),
                "question_ids": question_ids_for_drill,
                "recommended_questions": min(10, max(3, len(question_ids_for_drill))),
            }
        )

    for kp_item in knowledge_point_breakdown[:top_k]:
        question_ids_for_drill = kp_item["question_ids"][:10]
        recommended_drills.append(
            {
                "drill_type": "knowledge_point",
                "drill_key": str(kp_item["knowledge_point_id"] or "unknown"),
                "drill_label": f"{kp_item['knowledge_point_name']}专项",
                "question_count": len(question_ids_for_drill),
                "question_ids": question_ids_for_drill,
                "recommended_questions": min(10, max(3, len(question_ids_for_drill))),
            }
        )

    return {
        "overview": {
            "wrong_questions": total_wrong_questions,
            "wrong_attempts": total_wrong_attempts,
        },
        "cause_breakdown": cause_breakdown,
        "knowledge_point_breakdown": knowledge_point_breakdown,
        "recommended_drills": recommended_drills,
    }
