"""
GradingEngine — 统一判分接口。

封装 QuizAITaskService.grade_question，对外暴露单一的 grade() 静态方法。
Phase 2：ErrorClassifier 暂为占位，直接透传 grade_question 返回的 error_analysis
（Phase 1 已在 grade_question 内部通过 LLM 生成）。
"""

from typing import Any, Dict, Optional

from quizzes.services.ai_task_service import QuizAITaskService


class GradingEngine:
    """判分引擎 — 统一入口。"""

    @staticmethod
    def grade(
        ai,
        question_text: str,
        user_answer: Any,
        correct_answer: Any,
        q_type: str,
        max_score: float,
        grading_points: Optional[str] = None,
        options: Optional[Any] = None,
        subjective_type: str = '主观题',
    ) -> Dict[str, Any]:
        """
        统一判分接口。

        内部直接调用 QuizAITaskService.grade_question，返回完整判分结果。
        rubric 参数固定为 None（由 grade_question 内部通过 grading_points 自行处理）。

        返回 dict 包含：
            - score: float              得分
            - feedback: str             评语
            - analysis: str             深度解析 / error_analysis（Phase 1 LLM 产出）
            - memorix_rating: int       Memorix 自进化评分 (1-4)
        """
        return QuizAITaskService.grade_question(
            ai=ai,
            question_text=question_text,
            user_answer=user_answer,
            correct_answer=correct_answer,
            q_type=q_type,
            max_score=max_score,
            grading_points=grading_points,
            rubric=None,
            options=options,
            subjective_type=subjective_type,
        )
