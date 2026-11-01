from types import SimpleNamespace
from unittest.mock import patch

from ai_assistant.services.tool_executor import PlannerToolExecutor


def _executor():
    executor = object.__new__(PlannerToolExecutor)
    executor.user = SimpleNamespace(pk=1)
    executor.institution = None
    executor.pending_visuals = []
    return executor


def test_empty_practice_result_requires_original_question():
    empty = {
        "total_found": 0,
        "questions": [],
        "practice_url": "/quiz/practice",
        "message": "已从题库抽取 0 道题目",
    }
    with patch(
        "ai_assistant.services.memory_system.MemorySystem.query_practice_questions",
        return_value=dict(empty),
    ) as query:
        result = _executor()._handle_get_practice_questions({
            "subject": "高中物理",
            "limit": 1,
            "subjective_type": "calculate",
        })

    assert result["no_bank_match"] is True
    assert result["fallback"]["action"] == "generate_question"
    assert "直接" in result["fallback"]["instruction"]
    assert "不要说明" in result["fallback"]["instruction"]
    assert "grade_student_answer" in result["fallback"]["instruction"]
    assert "practice_url" not in result
    assert "visual" not in result
    assert query.call_args.kwargs["q_type"] == "subjective"
    assert query.call_args.kwargs["subjective_type"] == "calculate"


def test_bank_hit_keeps_practice_card_without_fallback():
    hit = {
        "total_found": 1,
        "questions": [{
            "id": 7,
            "text": "题干",
            "q_type": "objective",
            "subjective_type": "",
            "options": ["A", "B"],
            "difficulty_level": "normal",
            "kp_name": "合成知识点",
            "kp_code": "KP-1",
            "is_review": False,
        }],
        "practice_url": "/quiz/practice",
        "message": "已从题库抽取 1 道题目",
    }
    with patch(
        "ai_assistant.services.memory_system.MemorySystem.query_practice_questions",
        return_value=dict(hit),
    ) as query:
        result = _executor()._handle_get_practice_questions({"kp_name": "合成知识点"})

    assert "no_bank_match" not in result
    assert result["visual"]["type"] == "practice_quiz"
    assert result["visual"]["payload"]["practice_id"]
    assert result["questions"][0]["q_type"] == "objective"
    assert query.call_args.kwargs["q_type"] == ""
