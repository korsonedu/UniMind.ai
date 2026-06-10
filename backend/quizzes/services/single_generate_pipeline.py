import json
import re
from typing import Any, Dict, Iterable, List, Optional

from django.conf import settings
from django.db.models import Q

from ai_engine.service import AICallError
from ai_engine.tools import BATCH_REVIEW_SCHEMA
from ai_service import AIService
from quizzes.models import KnowledgePoint
from quizzes.services.ai_schema_guard import validate_question_list_payload
from quizzes.utils import safe_int


def _normalize_kp_ids(kp_ids: Iterable[Any]) -> List[int]:
    normalized: List[int] = []
    for raw in kp_ids or []:
        try:
            kp_id = int(raw)
        except Exception:
            continue
        if kp_id not in normalized:
            normalized.append(kp_id)
    return normalized


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _dedupe_questions(questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    result: List[Dict[str, Any]] = []
    for item in questions:
        text = _normalize_text(item.get("question") or item.get("text"))
        if not text:
            continue
        key = re.sub(r"\s+", " ", text.lower())
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _check_latex_integrity(text: str) -> List[str]:
    issues: List[str] = []
    if not text:
        return issues

    if text.count("$") % 2 != 0:
        issues.append("latex_unbalanced_dollar")
    if text.count(r"\(") != text.count(r"\)"):
        issues.append("latex_unbalanced_inline_paren")
    if text.count(r"\[") != text.count(r"\]"):
        issues.append("latex_unbalanced_block_bracket")

    begins = re.findall(r"\\begin\{([^}]+)\}", text)
    ends = re.findall(r"\\end\{([^}]+)\}", text)
    for env in sorted(set(begins + ends)):
        if begins.count(env) != ends.count(env):
            issues.append(f"latex_unbalanced_env:{env}")
    return issues


def _check_objective_integrity(question: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    q_type = _normalize_text(question.get("q_type")).lower()
    if q_type != "objective":
        return issues

    options = question.get("options")
    answer = _normalize_text(question.get("answer") or question.get("correct_answer")).upper()
    if not isinstance(options, dict):
        issues.append("objective_options_not_dict")
        return issues

    normalized_options = {str(k).strip().upper(): _normalize_text(v) for k, v in options.items()}
    valid_letters = {"A", "B", "C", "D"}
    if not valid_letters.issubset(set(normalized_options.keys())):
        issues.append("objective_options_missing_abcd")
    if answer and answer in valid_letters and not normalized_options.get(answer):
        issues.append("objective_answer_option_empty")
    if answer and answer not in valid_letters and answer not in normalized_options.values():
        issues.append("objective_answer_not_matched")
    if not answer:
        issues.append("objective_answer_missing")
    return issues


def _review_by_model(candidates: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    if not candidates:
        return {}

    from core.prompt_manager import PromptManager
    prompt_config = PromptManager.get_prompt_config(
        "AI_QUESTION_REVIEWER_BATCH",
        "你是学科命题审核专家。请对每道题做对抗性审查，检查逻辑错误、LaTeX语法风险、偏离学科大纲风险。只返回 JSON 数组，每项字段：index(int, 从1开始), pass(bool), issues(list[str]), severity('low|medium|high')。"
    )

    payload = []
    for idx, item in enumerate(candidates, start=1):
        payload.append(
            {
                "index": idx,
                "question": item.get("question") or item.get("text"),
                "q_type": item.get("q_type"),
                "subjective_type": item.get("subjective_type"),
                "answer": item.get("answer"),
                "options": item.get("options"),
                "kp_name": item.get("kp_name"),
                "related_knowledge_id": item.get("related_knowledge_id"),
            }
        )

    data = AIService.structured_output(
        system_prompt=prompt_config.content,
        user_prompt=json.dumps(payload, ensure_ascii=False),
        schema=BATCH_REVIEW_SCHEMA,
        tool_name="submit_batch_review",
        tool_description="提交批量题目审核结果",
        temperature=prompt_config.temperature if prompt_config.temperature is not None else 0.05,
        max_tokens=2200,
        operation="quizzes.single_pipeline.reviewer",
    )

    if not isinstance(data, list):
        # fallback to old extract_json path
        raw = AIService.simple_chat_text(
            system_prompt=prompt_config.content,
            user_prompt=json.dumps(payload, ensure_ascii=False),
            temperature=prompt_config.temperature if prompt_config.temperature is not None else 0.05,
            max_tokens=2200,
            operation="quizzes.single_pipeline.reviewer",
        )
        data = AIService.extract_json(raw)

    if not isinstance(data, list):
        return {}

    result: Dict[int, Dict[str, Any]] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        idx = safe_int(item.get("index"), 0)
        if idx <= 0:
            continue
        result[idx] = {
            "pass": bool(item.get("pass", True)),
            "issues": [str(x) for x in (item.get("issues") or []) if str(x).strip()],
            "severity": str(item.get("severity") or "low"),
        }
    return result


def _classify_questions(candidates: List[Dict[str, Any]], kps: List[KnowledgePoint]) -> List[Dict[str, Any]]:
    by_code = {kp.code: kp.id for kp in kps if kp.code}
    fallback_id = kps[0].id if kps else None
    classified: List[Dict[str, Any]] = []

    for item in candidates:
        record = dict(item)
        if not record.get("kp_id"):
            raw_code = _normalize_text(record.get("related_knowledge_id"))
            record["kp_id"] = by_code.get(raw_code, fallback_id)
        if not record.get("difficulty_level"):
            record["difficulty_level"] = "normal"
        classified.append(record)
    return classified


def run_single_generate_pipeline(
    *,
    kp_ids: Iterable[Any],
    count_per_kp: int = 1,
    target_types: Optional[List[str]] = None,
    target_difficulty: Any = "normal",
    target_type_ratio: Optional[Dict[str, Any]] = None,
    skip_review: bool = False,
    institution=None,
    on_progress=None,
) -> Dict[str, Any]:
    normalized_kp_ids = _normalize_kp_ids(kp_ids)
    if not normalized_kp_ids:
        raise AICallError("未提供有效知识点 ID。", status_code=400, retryable=False, error_category="bad_request")

    kp_qs = KnowledgePoint.objects.filter(id__in=normalized_kp_ids, level="kp")
    if institution:
        kp_qs = kp_qs.filter(Q(institution=institution) | Q(institution__isnull=True))
    kps = list(kp_qs.order_by("id"))
    if not kps:
        raise AICallError("未匹配到有效考点。", status_code=400, retryable=False, error_category="bad_request")

    windows = max(1, safe_int(getattr(settings, "AI_SINGLE_PIPELINE_AUTHOR_WINDOWS", 2), 2))
    max_windows = min(windows, 4)
    candidates: List[Dict[str, Any]] = []

    for author_window in range(max_windows):
        generated = AIService.preview_generate_questions(
            kp_ids=normalized_kp_ids,
            count_per_kp=max(1, safe_int(count_per_kp, 1)),
            target_types=target_types,
            target_difficulty=target_difficulty,
            target_type_ratio=target_type_ratio,
            institution=institution,
            on_progress=on_progress,
        )
        for item in generated or []:
            row = dict(item)
            row["author_window"] = author_window + 1
            candidates.append(row)

    candidates = _dedupe_questions(candidates)
    if not candidates:
        raise AICallError("Author 阶段未生成可用题目。", status_code=502, retryable=True, error_category="empty_generation")

    schema_ok, schema_errors = validate_question_list_payload(candidates, allow_empty=False)
    model_review = {} if skip_review else _review_by_model(candidates)

    review_report: List[Dict[str, Any]] = []
    passed_questions: List[Dict[str, Any]] = []
    rejected_count = 0

    for idx, item in enumerate(candidates, start=1):
        text_blob = "\n".join(
            [
                _normalize_text(item.get("question")),
                _normalize_text(item.get("answer")),
                _normalize_text(item.get("grading_points")),
            ]
        )
        local_issues: List[str] = []
        local_issues.extend(_check_latex_integrity(text_blob))
        local_issues.extend(_check_objective_integrity(item))

        if not item.get("kp_id") and not _normalize_text(item.get("related_knowledge_id")):
            local_issues.append("syllabus_unmapped_kp")

        model_info = model_review.get(idx) or {}
        model_issues = [str(x) for x in (model_info.get("issues") or []) if str(x).strip()]
        model_pass = bool(model_info.get("pass", True))
        critical = any(issue.startswith("latex_unbalanced") for issue in local_issues)
        critical = critical or "objective_answer_missing" in local_issues
        critical = critical or "objective_answer_not_matched" in local_issues
        critical = critical or "syllabus_unmapped_kp" in local_issues
        if not model_pass and str(model_info.get("severity", "low")) in {"medium", "high"}:
            critical = True

        passed = not critical
        if passed:
            passed_questions.append(item)
        else:
            rejected_count += 1

        review_report.append(
            {
                "index": idx,
                "pass": passed,
                "local_issues": local_issues,
                "model_issues": model_issues,
                "model_severity": model_info.get("severity", "low"),
            }
        )

    if not schema_ok:
        review_report.append(
            {
                "index": 0,
                "pass": False,
                "local_issues": list(schema_errors),
                "model_issues": [],
                "model_severity": "high",
            }
        )

    if not passed_questions:
        raise AICallError(
            "Reviewer 阶段未通过，所有候选题目被拒绝。",
            status_code=422,
            retryable=True,
            error_category="review_rejected",
        )

    classified = _classify_questions(passed_questions, kps)
    return {
        "pipeline": {
            "name": "single_generate_v1",
            "stages": ["author", "reviewer", "classifier"],
            "author_windows": max_windows,
            "author_candidates": len(candidates),
            "review_passed": len(classified),
            "review_rejected": rejected_count,
            "schema_ok": schema_ok,
        },
        "questions": classified,
        "review_report": review_report,
    }
