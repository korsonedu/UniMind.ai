"""
GradingEngine — 统一判分接口。

封装 QuizAITaskService.grade_question，对外暴露单一的 grade() 静态方法。
商业化分层：免费用户仅返回 score + feedback，付费用户返回完整的 error_analysis。
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
        user=None,
    ) -> Dict[str, Any]:
        """
        统一判分接口。

        内部直接调用 QuizAITaskService.grade_question，返回判分结果。
        rubric 参数固定为 None（由 grade_question 内部通过 grading_points 自行处理）。

        user 参数用于商业化分层：免费用户仅返回 score/feedback/is_correct，
        付费用户追加 error_analysis 和 memorix_rating。

        返回 dict 包含：
            - score: float              得分
            - feedback: str             评语
            - is_correct: bool          是否正确
            - analysis: str             (付费) 深度解析 / error_analysis
            - memorix_rating: int       (付费) Memorix 自进化评分 (1-4)
        """
        full_result = QuizAITaskService.grade_question(
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

        is_correct = (full_result.get('score', 0) / max_score) >= 0.6 if max_score > 0 else False

        # 商业化分层：免费用户降级返回
        from ai_assistant.services.memory_system import MemorySystem
        if not MemorySystem._has_feature(user, 'error_analysis'):
            return {
                'score': full_result.get('score', 0),
                'max_score': max_score,
                'feedback': full_result.get('feedback', ''),
                'is_correct': is_correct,
            }

        # 付费用户完整返回
        full_result['is_correct'] = is_correct
        return full_result
