import json
import logging
from typing import Any, Dict, List, Optional

from ai_engine.tools import (
    GRADING_RESULT_SCHEMA,
    OBJECTIVE_ANALYSIS_SCHEMA,
    QUESTION_LIST_SCHEMA,
)
from quizzes.models import KnowledgePoint, Question

logger = logging.getLogger(__name__)


class QuizAITaskService:
    """AI 判分与题目解析服务。

    Agent 化后，主路径走 structured_output(tool_choice="required")，
    失败时记录 warning 并返回兜底结果，不再走 extract_json + repair 的旧链路。
    """

    @classmethod
    def generate_ai_answer(cls, ai, question: Question) -> str:
        """为题目生成 AI 参考答案（纯文本，不需要结构化输出）。"""
        template = ai.get_template('quizzes', 'ai_answer_prompt.txt') or ''
        prompt = ai.format_template(
            template,
            q_type_display=question.get_subjective_type_display() if question.q_type == 'subjective' else '客观题',
            question_text=question.text,
            grading_points=question.grading_points or '无',
            correct_answer=question.correct_answer or '',
        )
        return ai.simple_chat_text(
            user_prompt=prompt,
            temperature=0.35,
            max_tokens=2800,
            operation='quizzes.generate_ai_answer',
        ) or ''

    @staticmethod
    def _resolve_grading_points(ai, grading_points, rubric, normalized_subjective_type):
        if rubric and isinstance(rubric, list) and len(rubric) > 0:
            lines = []
            for i, item in enumerate(rubric, 1):
                if isinstance(item, dict):
                    point = item.get('point', item.get('criteria', str(item)))
                    score = item.get('score', item.get('max_score', ''))
                    if score:
                        lines.append(f"{i}. {point}（{score}分）")
                    else:
                        lines.append(f"{i}. {point}")
                else:
                    lines.append(f"{i}. {item}")
            return '\n'.join(lines) if lines else (grading_points or ai.default_grading_points(normalized_subjective_type))
        return grading_points or ai.default_grading_points(normalized_subjective_type)

    @classmethod
    def _analyze_objective(cls, ai, question_text, options, correct_answer, user_answer, is_correct):
        """客观题 AI 深度解析：为什么对、为什么错、易错点。"""
        options_text = cls._format_options(options)
        template = ai.get_template('quizzes', 'objective_analysis_prompt.txt') or ''
        if not template:
            return cls._fallback_objective_feedback(ai, correct_answer, is_correct)

        prompt = ai.format_template(
            template,
            question_text=question_text,
            options_text=options_text,
            correct_answer=str(correct_answer),
            user_answer=str(user_answer or '未作答'),
            is_correct='正确' if is_correct else '错误',
        )

        parsed = ai.structured_output(
            system_prompt="",
            user_prompt=prompt,
            schema=OBJECTIVE_ANALYSIS_SCHEMA,
            tool_name="submit_objective_analysis",
            tool_description="提交客观题解析结果",
            temperature=0.4,
            max_tokens=2000,
            operation='quizzes.objective_analysis',
        )

        if not isinstance(parsed, dict):
            logger.warning("Objective analysis structured_output failed, using fallback")
            return cls._fallback_objective_feedback(ai, correct_answer, is_correct)

        why_correct = parsed.get('why_correct', '')
        why_wrong = parsed.get('why_wrong', '')
        pitfalls = parsed.get('pitfalls', '')

        feedback_parts = []
        if is_correct:
            feedback_parts.append('作答与标准答案一致，本题满分。')
        else:
            user_choice = ai.normalize_objective_answer(user_answer)
            correct_choice = ai.normalize_objective_answer(correct_answer)
            feedback_parts.append(
                f'你的作答为 {user_choice or "未作答"}，标准答案为 {correct_choice or "未设置"}，两者不一致，本题不得分。'
            )
        if why_wrong:
            feedback_parts.append(why_wrong)
        if pitfalls:
            feedback_parts.append(f'易错提醒：{pitfalls}')

        analysis_parts = [f'标准答案：{correct_answer}']
        if why_correct:
            analysis_parts.append(why_correct)

        return '\n\n'.join(feedback_parts), '\n\n'.join(analysis_parts)

    @staticmethod
    def _format_options(options):
        if not options:
            return '（无选项信息）'
        if isinstance(options, list):
            lines = []
            for item in options:
                if isinstance(item, dict):
                    key = item.get('key', item.get('label', item.get('value', '')))
                    text = item.get('text', item.get('label', item.get('value', '')))
                    lines.append(f"{key}. {text}")
                else:
                    lines.append(str(item))
            return '\n'.join(lines) if lines else '（无选项信息）'
        return str(options)

    @staticmethod
    def _fallback_objective_feedback(ai, correct_answer, is_correct):
        correct_choice = ai.normalize_objective_answer(correct_answer)
        if is_correct:
            feedback = '作答与标准答案一致，本题满分。'
            analysis = f'标准答案：选择 {correct_choice or "（题库未设置）"}。该选项满足题干条件并与题目设定一致。'
        else:
            feedback = f'作答与标准答案不一致，本题不得分。标准答案为 {correct_choice or "未设置"}。'
            analysis = f'标准答案：选择 {correct_choice or "（题库未设置）"}。请管理员补全解析后再进行训练。'
        return feedback, analysis

    @classmethod
    def grade_question(
        cls,
        ai,
        question_text: str,
        user_answer: Any,
        correct_answer: Any,
        q_type: str,
        max_score: float,
        grading_points: Optional[str] = None,
        rubric: Optional[Any] = None,
        options: Optional[Any] = None,
        subjective_type: str = '主观题',
    ) -> Dict[str, Any]:
        max_score = float(max_score or 0)

        if q_type == 'objective':
            user_choice = ai.normalize_objective_answer(user_answer)
            correct_choice = ai.normalize_objective_answer(correct_answer)
            is_correct = bool(user_choice and user_choice == correct_choice)

            ai_feedback, ai_analysis = cls._analyze_objective(
                ai,
                question_text=question_text,
                options=options,
                correct_answer=correct_answer,
                user_answer=user_answer,
                is_correct=is_correct,
            )

            return {
                'score': max_score if is_correct else 0.0,
                'feedback': ai_feedback,
                'analysis': ai_analysis,
                'memorix_rating': 4 if is_correct else 1,
            }

        template = ai.get_template('quizzes', 'grading_prompt.txt') or ''
        _, normalized_subjective_type = ai.normalize_question_type('subjective', subjective_type)
        prompt = ai.format_template(
            template,
            question_text=question_text,
            subjective_type=subjective_type,
            max_score=max_score,
            grading_points=cls._resolve_grading_points(ai, grading_points, rubric, normalized_subjective_type),
            correct_answer=correct_answer or '无',
            user_answer=user_answer or '（空白）',
        )

        parsed = ai.structured_output(
            system_prompt="",
            user_prompt=prompt,
            schema=GRADING_RESULT_SCHEMA,
            tool_name="submit_grading_result",
            tool_description="提交判分结果",
            temperature=0.2,
            max_tokens=2500,
            operation='quizzes.grade_question',
        )

        if not isinstance(parsed, dict):
            logger.warning("Grading structured_output returned None for operation=quizzes.grade_question")
            return {
                'score': 0.0,
                'feedback': '判分依据和深度解析：未能完成 AI 判分，已返回兜底结果。',
                'analysis': f'标准答案：{str(correct_answer or "")}',
                'memorix_rating': 1,
            }

        try:
            score = float(parsed.get('score', 0))
        except Exception:
            score = 0.0
        score = max(0.0, min(max_score, score))

        try:
            memorix_rating = int(parsed.get('memorix_rating', 2))
        except Exception:
            memorix_rating = 2
        memorix_rating = min(4, max(1, memorix_rating))

        return {
            'score': score,
            'feedback': str(parsed.get('feedback', '已评阅')).strip(),
            'analysis': str(parsed.get('analysis', '')).strip() or str(correct_answer or ''),
            'memorix_rating': memorix_rating,
            'error_analysis': parsed.get('error_analysis'),
        }

    @classmethod
    def generate_questions_from_text(
        cls,
        ai,
        text: str,
        num_obj: int = 3,
        num_short: int = 1,
        num_essay: int = 1,
        num_calc: int = 0,
        kp_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        kp = KnowledgePoint.objects.filter(id=kp_id).first() if kp_id else None
        kps_data = []
        if kp:
            kps_data = [
                {
                    'id': kp.id,
                    'code': kp.code,
                    'name': kp.name,
                    'description': kp.description,
                }
            ]

        kp_payload = (
            json.dumps(kps_data[0], ensure_ascii=False)
            if kp
            else '未指定（模型需尽量从文本语义推断）'
        )

        template = ai.get_template('quizzes', 'generate_from_text_prompt.txt') or ''
        prompt = ai.format_template(
            template,
            source_text=text,
            num_obj=max(0, int(num_obj or 0)),
            num_short=max(0, int(num_short or 0)),
            num_essay=max(0, int(num_essay or 0)),
            num_calc=max(0, int(num_calc or 0)),
            target_kp_json=kp_payload,
        )

        data = ai.structured_output(
            system_prompt="",
            user_prompt=prompt,
            schema=QUESTION_LIST_SCHEMA,
            tool_name="submit_questions",
            tool_description="提交生成的题目列表",
            temperature=0.35,
            max_tokens=7000,
            operation='quizzes.generate_from_text',
        )

        if not isinstance(data, list):
            logger.warning("generate_questions_from_text structured_output failed")
            return []

        kp_by_code = {kp.code: kp} if kp and kp.code else {}
        kp_by_id = {kp.id: kp} if kp else {}

        normalized = []
        for item in data:
            clean = ai._normalize_generated_question(item, kp_by_code, kp_by_id, kp, include_explanation=False)
            if clean:
                normalized.append(clean)
        return normalized

    @classmethod
    def parse_questions_from_text(cls, ai, raw_text: str) -> List[Dict[str, Any]]:
        template = ai.get_template('quizzes', 'preview_parse_prompt.txt') or ''
        prompt = ai.format_template(template, raw_text=raw_text)

        data = ai.structured_output(
            system_prompt="",
            user_prompt=prompt,
            schema=QUESTION_LIST_SCHEMA,
            tool_name="submit_questions",
            tool_description="提交生成的题目列表",
            temperature=0.2,
            max_tokens=3200,
            operation='quizzes.preview_parse',
        )

        if not isinstance(data, list):
            logger.warning("parse_questions_from_text structured_output failed")
            return []

        normalized = []
        for item in data:
            clean = ai._normalize_generated_question(item, {}, {}, None, include_explanation=True)
            if not clean:
                continue
            normalized.append(
                {
                    'text': clean['question'],
                    'q_type': clean['q_type'],
                    'subjective_type': clean['subjective_type'] or None,
                    'options': clean['options'] if clean['q_type'] == 'objective' else {},
                    'correct_answer': clean['answer'],
                    'grading_points': clean['grading_points'],
                    'analysis': clean.get('explanation', ''),
                    'difficulty_level': clean['difficulty_level'],
                }
            )
        return normalized
