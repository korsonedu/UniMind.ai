import json
from typing import Any, Dict, List, Optional

from django.conf import settings

from ai_engine.observability import record_schema_event
from quizzes.models import KnowledgePoint, Question
from quizzes import prompt_resources as quizzes_prompt_resources
from quizzes.services.ai_schema_guard import (
    validate_grading_payload,
    validate_question_list_payload,
)


class QuizAITaskService:
    _JSON_REPAIR_SYSTEM_PROMPT = (
        '你是严格的 JSON 修复器。'
        '你的唯一任务是把输入修复为符合要求的 JSON。'
        '禁止输出任何解释、Markdown、前后缀。'
    )

    _SCHEMA_HINTS = {
        'question_list': (
            '输出必须是 JSON 数组，每个对象至少包含: '
            'q_type, subjective_type, question, options, answer, grading_points, difficulty_level, related_knowledge_id。'
        ),
        'grading_result': (
            '输出必须是单个 JSON 对象，且仅包含: '
            'score(number), feedback(string), analysis(string), fsrs_rating(integer 1-4)。'
            '其中 feedback=判分依据和深度解析，analysis=标准答案（满分示范作答）。'
        ),
    }

    @classmethod
    def _repair_json_payload(
        cls,
        ai,
        raw_content: str,
        operation: str,
        schema_key: str,
    ) -> Optional[Any]:
        text = str(raw_content or '').strip()
        if not text:
            return None

        max_retries = max(0, int(getattr(settings, 'AI_SCHEMA_REPAIR_MAX_RETRIES', 1) or 1))
        schema_hint = cls._SCHEMA_HINTS.get(schema_key, '输出合法 JSON。')
        truncated = text[:12000]

        for attempt in range(max_retries + 1):
            prompt = (
                f'请将下面内容修复为合法 JSON。\n'
                f'约束:\n{schema_hint}\n\n'
                '原始内容如下（可能包含无关文本、坏 JSON、注释）:\n'
                f'{truncated}'
            )
            res = ai.simple_chat(
                system_prompt=cls._JSON_REPAIR_SYSTEM_PROMPT,
                user_prompt=prompt,
                temperature=0.0,
                max_tokens=3200,
                operation=f'{operation}.schema_repair',
            )
            content = ai.extract_content(res)
            parsed = ai.extract_json(content)
            if parsed is not None:
                record_schema_event(
                    operation=operation,
                    stage='repair',
                    success=True,
                    metadata={'attempt': attempt + 1, 'schema_key': schema_key},
                )
                return parsed

        record_schema_event(
            operation=operation,
            stage='repair',
            success=False,
            detail='repair_failed',
            metadata={'schema_key': schema_key},
        )
        return None

    @classmethod
    def parse_question_list_with_repair(
        cls,
        ai,
        content: str,
        operation: str,
        allow_empty: bool = False,
    ) -> Optional[List[Dict[str, Any]]]:
        parsed = ai.extract_json(content)
        valid, errors = validate_question_list_payload(parsed, allow_empty=allow_empty)
        if valid:
            record_schema_event(operation=operation, stage='validate', success=True)
            return [item for item in parsed if isinstance(item, dict)]

        record_schema_event(
            operation=operation,
            stage='validate',
            success=False,
            detail=';'.join(errors[:5]),
        )
        repaired = cls._repair_json_payload(ai, content, operation=operation, schema_key='question_list')
        valid_after_repair, errors_after_repair = validate_question_list_payload(repaired, allow_empty=allow_empty)
        if valid_after_repair:
            record_schema_event(
                operation=operation,
                stage='validate_after_repair',
                success=True,
            )
            return [item for item in repaired if isinstance(item, dict)]

        record_schema_event(
            operation=operation,
            stage='validate_after_repair',
            success=False,
            detail=';'.join(errors_after_repair[:5]),
        )
        return None

    @classmethod
    def parse_grading_payload_with_repair(
        cls,
        ai,
        content: str,
        operation: str,
    ) -> Optional[Dict[str, Any]]:
        parsed = ai.extract_json(content)
        valid, errors = validate_grading_payload(parsed)
        if valid and isinstance(parsed, dict):
            record_schema_event(operation=operation, stage='validate', success=True)
            return parsed

        record_schema_event(
            operation=operation,
            stage='validate',
            success=False,
            detail=';'.join(errors[:5]),
        )
        repaired = cls._repair_json_payload(ai, content, operation=operation, schema_key='grading_result')
        valid_after_repair, errors_after_repair = validate_grading_payload(repaired)
        if valid_after_repair and isinstance(repaired, dict):
            record_schema_event(
                operation=operation,
                stage='validate_after_repair',
                success=True,
            )
            return repaired

        record_schema_event(
            operation=operation,
            stage='validate_after_repair',
            success=False,
            detail=';'.join(errors_after_repair[:5]),
        )
        return None

    @classmethod
    def generate_ai_answer(cls, ai, question: Question) -> str:
        template = ai.get_template('quizzes', 'ai_answer_prompt.txt') or ''
        prompt = ai.format_template(
            template,
            q_type_display=question.get_subjective_type_display() if question.q_type == 'subjective' else '客观题',
            question_text=question.text,
            grading_points=question.grading_points or '无',
            correct_answer=question.correct_answer or '',
        )
        return ai.simple_chat_text(
            system_prompt=ai._get_system_prompt(
                'quizzes',
                'system_ai_answer_prompt.txt',
                '你是金融431课程助教，输出结构清晰、可复习的标准答案与解析。',
            ),
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
        """客观题 AI 深度解析：为什么对、为什么错、易错点。失败时回退到简单文本。"""
        try:
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
            response = ai.simple_chat(
                system_prompt=ai._get_system_prompt(
                    'quizzes',
                    'system_ai_answer_prompt.txt',
                    '你是金融431资深讲师，擅长客观题深度解析。仅输出 JSON 对象。',
                ),
                user_prompt=prompt,
                temperature=0.4,
                max_tokens=2000,
                operation='quizzes.objective_analysis',
            )
            content = ai.extract_content(response)
            parsed = cls.parse_grading_payload_with_repair(
                ai, content or '', operation='quizzes.objective_analysis',
            )
            if isinstance(parsed, dict):
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

        except Exception:
            pass

        return cls._fallback_objective_feedback(ai, correct_answer, is_correct)

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
                'fsrs_rating': 4 if is_correct else 1,
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

        response = ai.simple_chat(
            system_prompt=ai._get_system_prompt(
                'quizzes',
                'system_grading_prompt.txt',
                '你是严谨的金融431阅卷老师。仅输出 JSON 对象。',
            ),
            user_prompt=prompt,
            temperature=0.2,
            max_tokens=2500,
            operation='quizzes.grade_question',
        )
        content = ai.extract_content(response)
        parsed = cls.parse_grading_payload_with_repair(
            ai,
            content or '',
            operation='quizzes.grade_question',
        )

        if not isinstance(parsed, dict):
            fallback_feedback = '判分依据和深度解析：未能完成 AI 判分，已返回兜底结果。'
            return {
                'score': 0.0,
                'feedback': fallback_feedback,
                'analysis': f'标准答案：{str(correct_answer or "")}',
                'fsrs_rating': 1,
            }

        try:
            score = float(parsed.get('score', 0))
        except Exception:
            score = 0.0
        score = max(0.0, min(max_score, score))

        try:
            fsrs_rating = int(parsed.get('fsrs_rating', 2))
        except Exception:
            fsrs_rating = 2
        fsrs_rating = min(4, max(1, fsrs_rating))

        return {
            'score': score,
            'feedback': str(parsed.get('feedback', '已评阅')).strip(),
            'analysis': str(parsed.get('analysis', '')).strip() or str(correct_answer or ''),
            'fsrs_rating': fsrs_rating,
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
            module_rules=ai._build_module_rules(kps_data),
            shared_answer_requirements=quizzes_prompt_resources.get_shared_answer_requirements(),
            shared_question_shape_constraints=quizzes_prompt_resources.get_shared_question_shape_constraints(),
            shared_output_schema=quizzes_prompt_resources.get_shared_output_schema(),
        )

        response = ai.simple_chat(
            system_prompt=ai._get_system_prompt(
                'quizzes',
                'system_generate_from_text_prompt.txt',
                '你是431金融题库教研员。仅输出 JSON 数组。',
            ),
            user_prompt=prompt,
            temperature=0.35,
            max_tokens=7000,
            operation='quizzes.generate_from_text',
        )

        content = ai.extract_content(response)
        data = cls.parse_question_list_with_repair(
            ai,
            content or '',
            operation='quizzes.generate_from_text',
            allow_empty=False,
        )
        if not isinstance(data, list):
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

        response = ai.simple_chat(
            system_prompt=ai._get_system_prompt(
                'quizzes',
                'system_preview_parse_prompt.txt',
                '你是题目清洗与结构化专家。仅输出 JSON 数组。',
            ),
            user_prompt=prompt,
            temperature=0.2,
            max_tokens=3200,
            operation='quizzes.preview_parse',
        )
        content = ai.extract_content(response)
        data = cls.parse_question_list_with_repair(
            ai,
            content or '',
            operation='quizzes.preview_parse',
            allow_empty=True,
        )
        if not isinstance(data, list):
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
