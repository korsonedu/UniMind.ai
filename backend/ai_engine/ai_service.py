import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from django.conf import settings

from ai_engine.service import AIEngine
from quizzes.models import Question

from quizzes.services.question_normalizer import (
    normalize_question_type,
    normalize_difficulty_level,
    normalize_options,
    normalize_objective_answer,
    normalize_noun_question_text,
    QUESTION_TYPE_ALIASES,
    DIFFICULTY_ORDER,
    TYPE_RATIO_LABELS,
)

from quizzes.services.question_generator import QuestionGenerator

logger = logging.getLogger(__name__)


class _SafeDict(dict):
    def __missing__(self, key):
        return '{' + key + '}'


class AIService:
    """AI 门面层：统一模板、生成、判分与助教对话接口。"""

    # Re-export extracted constants for backward compatibility
    QUESTION_TYPE_ALIASES = QUESTION_TYPE_ALIASES
    DIFFICULTY_ORDER = DIFFICULTY_ORDER
    TYPE_RATIO_LABELS = TYPE_RATIO_LABELS

    # ── Core AI Engine ────────────────────────────────────────────

    @classmethod
    def call_ai(cls, messages, temperature=0.4, max_tokens=4096,
                raise_on_error=False, operation='general', tools=None, tool_choice=None):
        return AIEngine.call_ai(
            list(messages), temperature=temperature, max_tokens=max_tokens,
            raise_on_error=raise_on_error, operation=operation,
            tools=tools, tool_choice=tool_choice,
        )

    @classmethod
    def simple_chat(cls, system_prompt="", user_prompt="", temperature=0.4,
                    max_tokens=4096, raise_on_error=False, operation='general'):
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]
        return cls.call_ai(messages, temperature=temperature, max_tokens=max_tokens,
                           raise_on_error=raise_on_error, operation=operation)

    @classmethod
    def simple_chat_text(cls, system_prompt="", user_prompt="", temperature=0.4,
                         max_tokens=4096, operation='general') -> Optional[str]:
        res = cls.simple_chat(system_prompt, user_prompt, temperature=temperature,
                              max_tokens=max_tokens, operation=operation)
        return cls.extract_content(res)

    @classmethod
    def structured_output(cls, system_prompt, user_prompt, schema,
                          tool_name="output", tool_description="Submit the structured output",
                          temperature=0.7, max_tokens=8192, operation='general',
                          raise_on_error=False):
        """
        强制模型输出符合 JSON Schema 的结构化数据。
        替代 simple_chat_text + extract_json 的脆弱模式。
        """
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]
        return AIEngine.structured_output(
            messages=messages, schema=schema, tool_name=tool_name,
            tool_description=tool_description, temperature=temperature,
            max_tokens=max_tokens, operation=operation,
            raise_on_error=raise_on_error,
        )

    @classmethod
    def call_ai_with_tools(cls, system_prompt, user_prompt, tools, tool_executor,
                           tool_choice="auto", temperature=0.7, max_tokens=8192,
                           operation='general', max_tool_rounds=5,
                           raise_on_error=False):
        """多轮 Agent 循环，详见 AIEngine.call_ai_with_tools。"""
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]
        return AIEngine.call_ai_with_tools(
            messages=messages, tools=tools, tool_executor=tool_executor,
            tool_choice=tool_choice, temperature=temperature,
            max_tokens=max_tokens, operation=operation,
            max_tool_rounds=max_tool_rounds, raise_on_error=raise_on_error,
        )

    @classmethod
    def agentic_structured_output(cls, system_prompt, user_prompt, schema,
                                  tool_name, tool_description,
                                  research_tools, tool_executor,
                                  temperature=0.7, max_tokens=8192,
                                  operation='general', max_tool_rounds=5,
                                  raise_on_error=False):
        """多轮 Agent + 结构化输出，详见 AIEngine.agentic_structured_output。"""
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]
        return AIEngine.agentic_structured_output(
            messages=messages, schema=schema, tool_name=tool_name,
            tool_description=tool_description, research_tools=research_tools,
            tool_executor=tool_executor, temperature=temperature,
            max_tokens=max_tokens, operation=operation,
            max_tool_rounds=max_tool_rounds, raise_on_error=raise_on_error,
        )

    @classmethod
    def extract_json(cls, text: Optional[str]):
        if not text:
            return None
        parsed = AIEngine.extract_json(text)
        if parsed is not None:
            return parsed
        # 括号匹配兜底：跳过字符串内容，定位最外层 JSON 对象/数组
        for left, right in [('{', '}'), ('[', ']')]:
            start = text.find(left)
            if start < 0:
                continue
            depth = 0
            in_string = False
            escape = False
            end = -1
            for i in range(start, len(text)):
                ch = text[i]
                if escape:
                    escape = False
                    continue
                if ch == '\\':
                    escape = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == left:
                    depth += 1
                elif ch == right:
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if end > start:
                try:
                    return json.loads(text[start:end + 1])
                except Exception:
                    continue
        return None

    @classmethod
    def extract_content(cls, response: Optional[Dict[str, Any]]) -> Optional[str]:
        if not response:
            return None
        try:
            choices = response.get('choices') or []
            if not choices:
                return None
            message = choices[0].get('message', {})
            content = message.get('content')
            if content is None:
                content = message.get('reasoning_content')
            content = (content or '').strip()
            return content or None
        except Exception:
            return None

    # ── Template Management ───────────────────────────────────────

    @classmethod
    def get_template(cls, namespace: str, template_name: str) -> Optional[str]:
        """从统一 prompts/ 目录读取模板文件。"""
        base_dir = Path(getattr(settings, 'BASE_DIR', Path(__file__).resolve().parent))
        name = Path(template_name).name
        ns = (namespace or '').strip('/ ')

        candidates = [
            base_dir / 'prompts' / ns / name,
        ]

        for path in candidates:
            if not path.exists():
                continue
            try:
                raw = path.read_text(encoding='utf-8')
                if path.suffix.lower() == '.txt':
                    return cls._strip_template_meta_comment(raw)
                return raw
            except Exception:
                continue
        return None

    @classmethod
    def _strip_template_meta_comment(cls, raw: str) -> str:
        text = (raw or '').lstrip('﻿')
        if not text.startswith('/* PROMPT_META'):
            return raw
        end = text.find('*/')
        if end < 0:
            return raw
        return text[end + 2:].lstrip('\r\n')

    @classmethod
    def format_template(cls, template: str, **kwargs) -> str:
        return template.format_map(_SafeDict(**kwargs))

    # ── Default grading points (inlined, was from prompt_resources) ──

    _DEFAULT_GRADING_POINTS = {
        'noun': '1. 概念定义准确(2分)；2. 关键机制或假设(2分)；3. 实际意义或应用(1分)。',
        'essay': '1. 先解释核心原理并写出关键公式/恒等式(6分)；2. 至少3个分论点，每点含机制链条与定量关系(8分)；3. 结论与术语归纳准确(6分)。',
        'calculate': '1. 公式与方法正确(4分)；2. 过程完整且代入准确(4分)；3. 结果与解释(2分)。',
        'short': '1. 要点覆盖完整(4分)；2. 相近概念边界辨析准确(3分)；3. 逻辑清晰且结论准确(3分)。',
    }

    @classmethod
    def default_grading_points(cls, subjective_type: str) -> str:
        key = str(subjective_type or 'short').strip().lower()
        return cls._DEFAULT_GRADING_POINTS.get(key, cls._DEFAULT_GRADING_POINTS['short'])

    # ── Normalization (delegates to question_normalizer) ──────────

    normalize_question_type = staticmethod(normalize_question_type)
    normalize_difficulty_level = staticmethod(normalize_difficulty_level)
    normalize_options = staticmethod(normalize_options)
    normalize_objective_answer = staticmethod(normalize_objective_answer)
    normalize_noun_question_text = staticmethod(normalize_noun_question_text)

    # ── Question Generation (delegates to QuestionGenerator) ──────

    @classmethod
    def preview_generate_questions(cls, kp_ids, count_per_kp=1, target_types=None,
                                   target_difficulty='normal', target_type_ratio=None,
                                   institution=None, on_progress=None):
        gen = QuestionGenerator(cls)
        return gen.preview_generate_questions(
            kp_ids=kp_ids, count_per_kp=count_per_kp,
            target_types=target_types, target_difficulty=target_difficulty,
            target_type_ratio=target_type_ratio, institution=institution,
            on_progress=on_progress,
        )

    @classmethod
    def batch_generate_questions(cls, kp_queryset, count_per_kp=1,
                                 target_types=None, target_difficulty='normal',
                                 institution=None) -> int:
        gen = QuestionGenerator(cls)
        return gen.batch_generate_questions(
            kp_queryset=kp_queryset, count_per_kp=count_per_kp,
            target_types=target_types, target_difficulty=target_difficulty,
            institution=institution,
        )

    @classmethod
    def generate_ai_answer(cls, question: Question) -> str:
        gen = QuestionGenerator(cls)
        return gen.generate_ai_answer(question)

    @classmethod
    def grade_question(cls, question_text, user_answer, correct_answer,
                       q_type, max_score, grading_points=None, rubric=None,
                       options=None, subjective_type='主观题') -> Dict[str, Any]:
        gen = QuestionGenerator(cls)
        return gen.grade_question(
            question_text=question_text, user_answer=user_answer,
            correct_answer=correct_answer, q_type=q_type,
            max_score=max_score, grading_points=grading_points,
            rubric=rubric, options=options, subjective_type=subjective_type,
        )

    @classmethod
    def generate_questions_from_text(cls, text, num_obj=3, num_short=1,
                                     num_essay=1, num_calc=0, kp_id=None) -> List[Dict[str, Any]]:
        gen = QuestionGenerator(cls)
        return gen.generate_questions_from_text(
            text=text, num_obj=num_obj, num_short=num_short,
            num_essay=num_essay, num_calc=num_calc, kp_id=kp_id,
        )

    @classmethod
    def parse_questions_from_text(cls, raw_text: str) -> List[Dict[str, Any]]:
        gen = QuestionGenerator(cls)
        return gen.parse_questions_from_text(raw_text=raw_text)

    # ── Chat / Assistant ─────────────────────────────────────────

    @classmethod
    def chat_with_assistant(cls, bot, history_messages, user_message, student_context=''):
        from ai_assistant.services.chat_service import AssistantChatService
        return AssistantChatService.chat_with_assistant(
            cls, bot=bot, history_messages=history_messages,
            user_message=user_message, student_context=student_context,
        )

    @classmethod
    def chat_with_assistant_agent(cls, bot, history_messages, user_message,
                                   tool_executor, student_context='',
                                   memory_context='', on_step=None,
                                   on_message=None, adaptive_directives='',
                                   variant_suffix=''):
        from ai_assistant.services.chat_service import AssistantChatService
        return AssistantChatService.chat_with_assistant_agent(
            bot=bot, history_messages=history_messages,
            user_message=user_message, tool_executor=tool_executor,
            student_context=student_context, memory_context=memory_context,
            on_step=on_step, on_message=on_message,
            adaptive_directives=adaptive_directives,
            variant_suffix=variant_suffix,
        )

    @classmethod
    def chat(cls, messages, temperature=0.7, max_tokens=4096,
             response_format=None, operation='general'):
        """通用 AI 对话，支持 response_format (json_object)。"""
        from .service import AIEngine
        return AIEngine.call_ai(
            messages=messages, temperature=temperature,
            max_tokens=max_tokens, operation=operation,
            _response_format=response_format,
        )

    # ── Legacy private methods (delegated to QuestionGenerator) ──

    @classmethod
    def _normalize_generated_question(cls, raw, kp_by_code, kp_by_id,
                                       fallback_kp, include_explanation=False):
        gen = QuestionGenerator(cls)
        return gen._normalize_generated_question(
            raw, kp_by_code, kp_by_id, fallback_kp,
            include_explanation=include_explanation,
        )
