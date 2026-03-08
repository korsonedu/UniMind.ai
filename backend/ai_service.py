import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from django.conf import settings
from django.db import transaction

from ai_engine.config import get_llm_config
from ai_engine.service import AICallError, AIEngine
from quizzes.models import KnowledgePoint, Question
from quizzes import prompt_resources as quizzes_prompt_resources

logger = logging.getLogger(__name__)


class _SafeDict(dict):
    def __missing__(self, key):
        return '{' + key + '}'


def _build_question_type_aliases() -> Dict[str, Tuple[str, str]]:
    alias_groups = [
        (('objective', ''), ['objective', '单选', '单选题', '选择题', '单项选择题']),
        (('subjective', ''), ['subjective', '主观题']),
        (('subjective', 'noun'), ['noun', '名词解释']),
        (('subjective', 'short'), ['short', '简答', '简答题', '辨析', '辨析题', '比较题', '对比题', '简析']),
        (('subjective', 'essay'), ['essay', '论述', '论述题']),
        (('subjective', 'calculate'), ['calculate', '计算', '计算题']),
    ]

    alias_map: Dict[str, Tuple[str, str]] = {}
    for target, aliases in alias_groups:
        for alias in aliases:
            key = str(alias).strip()
            if not key:
                continue

            if key in alias_map and alias_map[key] != target:
                raise ValueError(f'QUESTION_TYPE_ALIASES 冲突: {key} -> {alias_map[key]} / {target}')

            alias_map[key] = target

    return alias_map


class AIService:
    """AI 门面层：统一模板、生成、判分与助教对话接口。"""

    QUESTION_TYPE_ALIASES = _build_question_type_aliases()
    DIFFICULTY_ORDER = {
        'entry': 0,
        'easy': 1,
        'normal': 2,
        'hard': 3,
        'extreme': 4,
    }
    TYPE_RATIO_LABELS = {
        'objective': '单项选择题',
        'subjective:noun': '名词解释',
        'subjective:short': '简答题',
        'subjective:essay': '论述题',
        'subjective:calculate': '计算题',
    }

    @classmethod
    def call_ai(
        cls,
        messages: Sequence[Dict[str, str]],
        temperature: float = 0.4,
        max_tokens: int = 4096,
        raise_on_error: bool = False,
        operation: str = 'general',
    ):
        return AIEngine.call_ai(
            list(messages),
            temperature=temperature,
            max_tokens=max_tokens,
            raise_on_error=raise_on_error,
            operation=operation,
        )

    @classmethod
    def simple_chat(
        cls,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.4,
        max_tokens: int = 4096,
        raise_on_error: bool = False,
        operation: str = 'general',
    ):
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]
        return cls.call_ai(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            raise_on_error=raise_on_error,
            operation=operation,
        )

    @classmethod
    def simple_chat_text(
        cls,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.4,
        max_tokens: int = 4096,
        operation: str = 'general',
    ) -> Optional[str]:
        res = cls.simple_chat(
            system_prompt,
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            operation=operation,
        )
        return cls.extract_content(res)

    @classmethod
    def extract_json(cls, text: Optional[str]):
        if not text:
            return None

        parsed = AIEngine.extract_json(text)
        if parsed is not None:
            return parsed

        candidates = [
            re.search(r'\{[\s\S]*\}', text),
            re.search(r'\[[\s\S]*\]', text),
        ]
        for match in candidates:
            if not match:
                continue
            try:
                return json.loads(match.group(0).strip())
            except Exception:
                continue
        return None

    @classmethod
    def get_llm_config(cls):
        return get_llm_config()

    @classmethod
    def get_template(cls, namespace: str, template_name: str) -> Optional[str]:
        base_dir = Path(getattr(settings, 'BASE_DIR', Path(__file__).resolve().parent))
        clean_name = Path(template_name).name
        clean_ns = (namespace or '').strip('/ ')

        if clean_ns == 'ai_assistant':
            # 机器人/助教统一从 core/prompts 读取，避免与 ai_assistant/templates 双份漂移。
            candidates = [base_dir / 'core' / 'prompts' / clean_name]
        elif clean_ns == 'quizzes':
            # quizzes 已明确单源：仅从 quizzes/templates 读取，避免 core/prompts 重复漂移。
            candidates = [base_dir / 'quizzes' / 'templates' / clean_name]
        else:
            candidates = [
                base_dir / clean_ns / 'templates' / clean_name if clean_ns else None,
                base_dir / 'core' / 'prompts' / clean_name,
            ]

        for path in candidates:
            if not path or not path.exists():
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
        """
        支持在模板文件顶部使用注释块写维护说明，加载时自动剥离：
        /* PROMPT_META
        ...
        */
        """
        text = (raw or '').lstrip('\ufeff')
        if not text.startswith('/* PROMPT_META'):
            return raw

        end = text.find('*/')
        if end < 0:
            return raw

        return text[end + 2:].lstrip('\r\n')

    @classmethod
    def _get_system_prompt(cls, namespace: str, template_name: str, fallback: str) -> str:
        template = cls.get_template(namespace, template_name)
        return (template or '').strip() or fallback

    @classmethod
    def format_template(cls, template: str, **kwargs) -> str:
        return template.format_map(_SafeDict(**kwargs))

    @classmethod
    def extract_content(cls, response: Optional[Dict[str, Any]]) -> Optional[str]:
        if not response:
            return None
        try:
            choices = response.get('choices') or []
            if not choices:
                return None
            return (choices[0].get('message', {}).get('content') or '').strip() or None
        except Exception:
            return None

    @classmethod
    def _normalize_question_type(cls, q_type: Any, subjective_type: Any = None) -> Tuple[str, str]:
        raw_q_type = str(q_type or '').strip()
        raw_sub_type = str(subjective_type or '').strip()

        if raw_q_type in cls.QUESTION_TYPE_ALIASES:
            mapped_q_type, mapped_sub_type = cls.QUESTION_TYPE_ALIASES[raw_q_type]
            if mapped_sub_type:
                return mapped_q_type, mapped_sub_type
            if raw_sub_type in cls.QUESTION_TYPE_ALIASES:
                _, mapped_sub = cls.QUESTION_TYPE_ALIASES[raw_sub_type]
                return mapped_q_type, mapped_sub
            return mapped_q_type, raw_sub_type.lower() if raw_sub_type.lower() in {'noun', 'short', 'essay', 'calculate'} else ''

        q_lower = raw_q_type.lower()
        if q_lower in cls.QUESTION_TYPE_ALIASES:
            mapped_q_type, mapped_sub_type = cls.QUESTION_TYPE_ALIASES[q_lower]
            if mapped_sub_type:
                return mapped_q_type, mapped_sub_type
            if raw_sub_type.lower() in {'noun', 'short', 'essay', 'calculate'}:
                return mapped_q_type, raw_sub_type.lower()
            return mapped_q_type, ''

        if q_lower in {'noun', 'short', 'essay', 'calculate'}:
            return 'subjective', q_lower

        if raw_sub_type.lower() in {'noun', 'short', 'essay', 'calculate'}:
            return 'subjective', raw_sub_type.lower()

        return 'subjective', 'short'

    @classmethod
    def normalize_question_type(cls, q_type: Any, subjective_type: Any = None) -> Tuple[str, str]:
        return cls._normalize_question_type(q_type, subjective_type)

    @classmethod
    def _normalize_difficulty_level(cls, difficulty_level: Any, difficulty: Any = None) -> str:
        if difficulty_level:
            level = str(difficulty_level).strip().lower()
            if level in {'entry', 'easy', 'normal', 'hard', 'extreme'}:
                return level

        try:
            value = int(float(difficulty))
        except Exception:
            return 'normal'

        if value <= 900:
            return 'entry'
        if value <= 1100:
            return 'easy'
        if value <= 1300:
            return 'normal'
        if value <= 1500:
            return 'hard'
        return 'extreme'

    @classmethod
    def normalize_difficulty_level(cls, difficulty_level: Any, difficulty: Any = None) -> str:
        return cls._normalize_difficulty_level(difficulty_level, difficulty)

    @classmethod
    def _normalize_target_difficulty(cls, target_difficulty: Any) -> str:
        if target_difficulty is None:
            return 'normal'
        level = str(target_difficulty).strip().lower()
        if level in {'entry', 'easy', 'normal', 'hard', 'extreme'}:
            return level
        if level in {'mixed', 'auto', 'any', 'random'}:
            return 'mixed'
        return 'normal'

    @classmethod
    def _canonical_question_type_key(cls, q_type: Any, subjective_type: Any = None) -> str:
        normalized_q_type, normalized_subjective_type = cls._normalize_question_type(q_type, subjective_type)
        if normalized_q_type == 'objective':
            return 'objective'
        return f"subjective:{normalized_subjective_type or 'short'}"

    @classmethod
    def _normalize_target_types(cls, target_types: Optional[List[str]]) -> List[str]:
        normalized: List[str] = []
        for item in target_types or []:
            key = cls._canonical_question_type_key(item, '')
            if key not in normalized:
                normalized.append(key)
        return normalized

    @classmethod
    def _normalize_target_type_ratio(cls, target_type_ratio: Any, target_types: Optional[List[str]]) -> Dict[str, float]:
        ratio_map: Dict[str, float] = {}
        if isinstance(target_type_ratio, dict):
            for raw_key, raw_value in target_type_ratio.items():
                key = cls._canonical_question_type_key(raw_key, '')
                try:
                    weight = float(raw_value)
                except Exception:
                    continue
                if weight <= 0:
                    continue
                ratio_map[key] = ratio_map.get(key, 0.0) + weight

        if not ratio_map:
            for key in cls._normalize_target_types(target_types):
                ratio_map[key] = 1.0

        if not ratio_map:
            ratio_map = {
                'objective': 1.0,
                'subjective:short': 1.0,
                'subjective:essay': 1.0,
            }

        total = sum(ratio_map.values())
        if total <= 0:
            return {'objective': 1.0}
        return {k: v / total for k, v in ratio_map.items()}

    @classmethod
    def _render_target_type_ratio(cls, ratio_map: Dict[str, float], count_per_kp: int) -> str:
        if not ratio_map:
            return '未指定，按教学常规自动配比。'

        lines = []
        for key, weight in sorted(ratio_map.items(), key=lambda x: x[1], reverse=True):
            label = cls.TYPE_RATIO_LABELS.get(key, key)
            per_kp = weight * max(1, int(count_per_kp or 1))
            lines.append(f"- {label}: {weight * 100:.0f}% (每考点约 {per_kp:.1f} 题)")
        return '\n'.join(lines)

    @classmethod
    def _estimate_bulk_generate_max_tokens(cls, count_per_kp: int) -> int:
        # 单次请求按题目数动态分配 token，避免大批量请求压垮时延。
        c = max(1, int(count_per_kp or 1))
        return max(2200, min(5600, 1200 + c * 1200))

    @classmethod
    def _request_bulk_generate_once(
        cls,
        kps_data: Sequence[Dict[str, Any]],
        count_per_kp: int,
        target_types: Optional[List[str]],
        target_difficulty: str,
        target_type_ratio_text: str,
    ) -> List[Dict[str, Any]]:
        template = cls.get_template('quizzes', 'bulk_generate_prompt.txt') or ''
        prompt = cls.format_template(
            template,
            count_per_kp=max(1, int(count_per_kp or 1)),
            module_rules=cls._build_module_rules(kps_data),
            target_types=', '.join(target_types or []),
            target_difficulty=target_difficulty,
            target_type_ratio=target_type_ratio_text,
            knowledge_points_json=json.dumps(list(kps_data), ensure_ascii=False, indent=2),
            shared_answer_requirements=quizzes_prompt_resources.get_shared_answer_requirements(),
            shared_question_shape_constraints=quizzes_prompt_resources.get_shared_question_shape_constraints(),
            shared_output_schema=quizzes_prompt_resources.get_shared_output_schema(),
        )

        logger.info(
            "ai.bulk_generate request: kp_count=%s count_per_kp=%s prompt_chars=%s",
            len(kps_data),
            count_per_kp,
            len(prompt),
        )

        response = cls.simple_chat(
            system_prompt=cls._get_system_prompt(
                'quizzes',
                'system_bulk_generate_prompt.txt',
                '你是431金融命题专家。只输出可被 json.loads 解析的 JSON 数组，不输出其他文字。',
            ),
            user_prompt=prompt,
            temperature=0.35,
            max_tokens=cls._estimate_bulk_generate_max_tokens(count_per_kp),
            raise_on_error=True,
            operation='quizzes.bulk_generate',
        )

        content = cls.extract_content(response)
        from quizzes.services.ai_task_service import QuizAITaskService

        data = QuizAITaskService.parse_question_list_with_repair(
            cls,
            content or '',
            operation='quizzes.bulk_generate',
            allow_empty=False,
        )
        if not isinstance(data, list):
            raise AICallError(
                "AI 命题结果格式异常，请重试。",
                status_code=502,
                retryable=True,
                error_category='schema_invalid',
            )
        return data

    @classmethod
    def _question_type_key_from_clean_data(cls, question: Dict[str, Any]) -> str:
        return cls._canonical_question_type_key(question.get('q_type'), question.get('subjective_type'))

    @classmethod
    def _estimate_difficulty_level(cls, question: Dict[str, Any]) -> str:
        text = str(question.get('question') or '').strip()
        answer = str(question.get('answer') or '').strip()
        q_type = str(question.get('q_type') or '')
        subjective_type = str(question.get('subjective_type') or '')
        options = question.get('options') or {}

        complexity_score = 0
        text_len = len(text)
        answer_len = len(answer)

        if text_len >= 120:
            complexity_score += 1
        if text_len >= 240:
            complexity_score += 1
        if answer_len >= 400:
            complexity_score += 1
        if answer_len >= 800:
            complexity_score += 1

        if q_type == 'objective':
            complexity_score -= 1
            if isinstance(options, dict):
                option_text_total = sum(len(str(v or '').strip()) for v in options.values())
                if option_text_total >= 120:
                    complexity_score += 1
        elif subjective_type == 'noun':
            complexity_score -= 1
        elif subjective_type == 'short':
            complexity_score += 1
        elif subjective_type == 'essay':
            complexity_score += 2
        elif subjective_type == 'calculate':
            complexity_score += 2

        hard_signals = [
            '推导', '证明', '比较', '辨析', '评价', '边界', '反例', '政策建议',
            '一般均衡', '跨市场', '传导机制', '约束条件', '情景分析', '敏感性',
        ]
        extreme_signals = ['批判性', '模型选择', '现实偏离', '多目标', '制度约束', '稳健性']
        calc_signals = ['=', 'Δ', '∂', 'σ', 'β', 'r=', 'NPV', 'IRR', 'CAPM', 'WACC']

        hard_hits = sum(1 for token in hard_signals if token in text or token in answer)
        extreme_hits = sum(1 for token in extreme_signals if token in text or token in answer)
        calc_hits = sum(1 for token in calc_signals if token in text or token in answer)

        if hard_hits >= 2:
            complexity_score += 1
        if hard_hits >= 4:
            complexity_score += 1
        if extreme_hits >= 2:
            complexity_score += 1
        if calc_hits >= 3:
            complexity_score += 1

        if complexity_score <= 0:
            return 'entry'
        if complexity_score == 1:
            return 'easy'
        if complexity_score in {2, 3}:
            return 'normal'
        if complexity_score in {4, 5}:
            return 'hard'
        return 'extreme'

    @classmethod
    def _apply_difficulty_regression_validation(
        cls,
        questions: List[Dict[str, Any]],
        target_difficulty: str,
    ) -> List[Dict[str, Any]]:
        # 允许通过环境变量直接跳过难度校验，避免前端出现“难度未通过”
        if not getattr(settings, 'AI_DIFFICULTY_CHECK_ENABLED', True):
            for q in questions:
                q['difficulty_estimated_level'] = cls._estimate_difficulty_level(q)
                q['difficulty_check_passed'] = True
                q['difficulty_level'] = target_difficulty
            return questions

        if target_difficulty == 'mixed':
            for q in questions:
                estimated_level = cls._estimate_difficulty_level(q)
                q['difficulty_estimated_level'] = estimated_level
                q['difficulty_check_passed'] = True
                q['difficulty_level'] = target_difficulty
            return questions

        target_rank = cls.DIFFICULTY_ORDER.get(target_difficulty, cls.DIFFICULTY_ORDER['normal'])
        tolerance = 1  # 严控在 ±1 档内
        for q in questions:
            estimated_level = cls._estimate_difficulty_level(q)
            estimated_rank = cls.DIFFICULTY_ORDER.get(estimated_level, cls.DIFFICULTY_ORDER['normal'])
            distance = abs(estimated_rank - target_rank)
            check_passed = distance <= tolerance
            q['difficulty_estimated_level'] = estimated_level
            q['difficulty_check_passed'] = check_passed
            q['difficulty_level'] = target_difficulty
        # 保留所有题目，只打标是否通过，避免题目数量被裁掉
        return questions

    @classmethod
    def _apply_type_ratio_filter(
        cls,
        questions: List[Dict[str, Any]],
        ratio_map: Dict[str, float],
    ) -> List[Dict[str, Any]]:
        if not questions or not ratio_map:
            return questions

        total = len(questions)
        desired_counts: Dict[str, int] = {}
        for key, weight in ratio_map.items():
            desired_counts[key] = max(0, int(round(weight * total)))

        # 修正四舍五入导致的总数偏差
        delta = total - sum(desired_counts.values())
        ordered_keys = sorted(ratio_map.keys(), key=lambda k: ratio_map[k], reverse=True)
        idx = 0
        while delta != 0 and ordered_keys:
            key = ordered_keys[idx % len(ordered_keys)]
            if delta > 0:
                desired_counts[key] += 1
                delta -= 1
            elif desired_counts[key] > 0:
                desired_counts[key] -= 1
                delta += 1
            idx += 1

        selected: List[Dict[str, Any]] = []
        type_buckets: Dict[str, List[Dict[str, Any]]] = {}
        for q in questions:
            key = cls._question_type_key_from_clean_data(q)
            type_buckets.setdefault(key, []).append(q)

        for key in ordered_keys:
            quota = desired_counts.get(key, 0)
            bucket = type_buckets.get(key, [])
            selected.extend(bucket[:quota])

        if len(selected) < total:
            selected_ids = {id(item) for item in selected}
            for q in questions:
                if id(q) not in selected_ids:
                    selected.append(q)
                if len(selected) >= total:
                    break

        return selected[:total]

    @classmethod
    def _normalize_options(cls, options: Any) -> Dict[str, str]:
        letters = ['A', 'B', 'C', 'D']
        normalized = {key: '' for key in letters}

        if isinstance(options, dict):
            for key, value in options.items():
                letter = str(key).strip().upper()[:1]
                if letter in normalized:
                    normalized[letter] = str(value or '').strip()
            return normalized

        if isinstance(options, list):
            for idx, value in enumerate(options[:4]):
                text = str(value or '').strip()
                match = re.match(r'^([A-Da-d])[\.、\s:：-]*(.*)$', text)
                if match:
                    normalized[match.group(1).upper()] = match.group(2).strip()
                elif idx < 4:
                    normalized[letters[idx]] = text
            return normalized

        return normalized

    @classmethod
    def normalize_options(cls, options: Any) -> Dict[str, str]:
        return cls._normalize_options(options)

    @classmethod
    def _normalize_objective_answer(cls, answer: Any, options: Optional[Dict[str, str]] = None) -> str:
        text = str(answer or '').strip()
        if not text:
            return ''

        m = re.match(r'^([A-Da-d])(?:[\.、\s:：-].*)?$', text)
        if m:
            return m.group(1).upper()

        if options:
            for letter, content in options.items():
                if text == content:
                    return letter

        upper = text.upper()
        return upper if upper in {'A', 'B', 'C', 'D'} else text

    @classmethod
    def normalize_objective_answer(cls, answer: Any, options: Optional[Dict[str, str]] = None) -> str:
        return cls._normalize_objective_answer(answer, options)

    @classmethod
    def _default_grading_points(cls, subjective_type: str) -> str:
        return quizzes_prompt_resources.get_default_grading_points(subjective_type)

    @classmethod
    def default_grading_points(cls, subjective_type: str) -> str:
        return cls._default_grading_points(subjective_type)

    @classmethod
    def _normalize_noun_question_text(cls, question_text: str) -> str:
        text = str(question_text or '').strip()
        if not text:
            return ''

        prefixes = [
            r'^名词解释[\s:：-]*',
            r'^请解释(?:下列)?(?:名词|概念)?[\s:：-]*',
            r'^请对(?:下列)?(?:名词|概念)进行解释[\s:：-]*',
            r'^什么是[\s:：-]*',
        ]
        for pattern in prefixes:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE).strip()

        text = re.sub(r'[。；;？！?]+$', '', text).strip()
        return text

    @classmethod
    def _build_module_rules(cls, kps_data: Sequence[Dict[str, Any]]) -> str:
        return quizzes_prompt_resources.build_module_rules_text(kps_data)

    @classmethod
    def _normalize_generated_question(
        cls,
        raw: Dict[str, Any],
        kp_by_code: Dict[str, KnowledgePoint],
        kp_by_id: Dict[int, KnowledgePoint],
        fallback_kp: Optional[KnowledgePoint],
        include_explanation: bool = False,
    ) -> Optional[Dict[str, Any]]:
        q_type, subjective_type = cls._normalize_question_type(
            raw.get('q_type') or raw.get('question_type') or raw.get('type'),
            raw.get('subjective_type'),
        )

        question_text = str(raw.get('question') or raw.get('text') or '').strip()
        if q_type == 'subjective' and subjective_type == 'noun':
            question_text = cls._normalize_noun_question_text(question_text)
        if not question_text:
            return None

        options = cls._normalize_options(raw.get('options')) if q_type == 'objective' else {}
        answer = str(raw.get('answer') or raw.get('correct_answer') or '').strip()
        if q_type == 'objective':
            answer = cls._normalize_objective_answer(answer, options)

        difficulty_level = cls._normalize_difficulty_level(raw.get('difficulty_level'), raw.get('difficulty'))

        related_code = str(
            raw.get('related_knowledge_id')
            or raw.get('knowledge_code')
            or raw.get('kp_code')
            or ''
        ).strip()

        kp_obj = None
        if related_code:
            kp_obj = kp_by_code.get(related_code)

        kp_id_raw = raw.get('kp_id')
        if kp_obj is None and kp_id_raw is not None:
            try:
                kp_obj = kp_by_id.get(int(kp_id_raw))
            except Exception:
                kp_obj = None

        if kp_obj is None:
            kp_obj = fallback_kp

        if q_type == 'objective':
            grading_points = '无'
        else:
            grading_points = str(raw.get('grading_points') or '').strip() or cls._default_grading_points(subjective_type)

        clean_data = {
            'q_type': q_type,
            'subjective_type': subjective_type if q_type == 'subjective' else '',
            'question': question_text,
            'options': options,
            'answer': answer,
            'grading_points': grading_points,
            'difficulty_level': difficulty_level,
            'related_knowledge_id': kp_obj.code if kp_obj else related_code,
            'kp_name': kp_obj.name if kp_obj else '未匹配知识点',
            'kp_id': kp_obj.id if kp_obj else None,
        }

        if include_explanation:
            clean_data['explanation'] = str(raw.get('analysis') or raw.get('explanation') or '').strip()

        return clean_data

    @classmethod
    def preview_generate_questions(
        cls,
        kp_ids: Iterable[int],
        count_per_kp: int = 1,
        target_types: Optional[List[str]] = None,
        target_difficulty: Any = 'normal',
        target_type_ratio: Optional[Dict[str, Any]] = None,
    ):
        kps = list(KnowledgePoint.objects.filter(id__in=list(kp_ids), level='kp').order_by('id'))
        if not kps:
            return []

        normalized_target_difficulty = cls._normalize_target_difficulty(target_difficulty)
        normalized_target_types = cls._normalize_target_types(target_types)
        normalized_type_ratio = cls._normalize_target_type_ratio(target_type_ratio, target_types)
        target_type_ratio_text = cls._render_target_type_ratio(
            normalized_type_ratio,
            max(1, int(count_per_kp or 1)),
        )

        kp_by_code = {kp.code: kp for kp in kps if kp.code}
        kp_by_id = {kp.id: kp for kp in kps}
        max_per_request = max(1, int(getattr(settings, 'AI_BULK_GENERATE_MAX_PER_REQUEST', 3) or 3))
        max_concurrency = max(1, int(getattr(settings, 'AI_BULK_GENERATE_CONCURRENCY', 2) or 2))
        total_per_kp = max(1, int(count_per_kp or 1))

        normalized: List[Dict[str, Any]] = []
        normalized_all: List[Dict[str, Any]] = []
        jobs: List[Tuple[KnowledgePoint, int, int]] = []

        for kp in kps:
            remaining = total_per_kp
            batch_index = 0

            while remaining > 0:
                batch_count = min(remaining, max_per_request)
                jobs.append((kp, batch_index, batch_count))
                remaining -= batch_count
                batch_index += 1

        logger.info(
            "ai.bulk_generate dispatch: kp_count=%s total_jobs=%s max_per_request=%s max_concurrency=%s",
            len(kps),
            len(jobs),
            max_per_request,
            max_concurrency,
        )

        job_results: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
        if jobs:
            first_error: Optional[BaseException] = None
            with ThreadPoolExecutor(max_workers=min(max_concurrency, len(jobs))) as executor:
                future_map = {}
                for kp, batch_index, batch_count in jobs:
                    kp_payload = [{
                        'id': kp.id,
                        'code': kp.code,
                        'name': kp.name,
                        'description': kp.description,
                    }]
                    future = executor.submit(
                        cls._request_bulk_generate_once,
                        kp_payload,
                        batch_count,
                        target_types,
                        normalized_target_difficulty,
                        target_type_ratio_text,
                    )
                    future_map[future] = (kp.id, batch_index)

                for future in as_completed(future_map):
                    kp_id, batch_index = future_map[future]
                    try:
                        job_results[(kp_id, batch_index)] = future.result()
                    except BaseException as exc:  # noqa: BLE001
                        first_error = exc
                        for pending in future_map:
                            if not pending.done():
                                pending.cancel()
                        break

            if first_error:
                if isinstance(first_error, AICallError):
                    raise first_error
                raise AICallError('AI 命题服务异常，请稍后重试。', status_code=500, retryable=False) from first_error

        for kp, batch_index, _ in jobs:
            data_batch = job_results.get((kp.id, batch_index), [])
            for item in data_batch:
                clean = cls._normalize_generated_question(item, kp_by_code, kp_by_id, kp, include_explanation=False)
                if not clean:
                    continue
                normalized_all.append(clean)
                clean_type_key = cls._question_type_key_from_clean_data(clean)
                if normalized_target_types and clean_type_key not in normalized_target_types:
                    continue
                normalized.append(clean)

        if not normalized and normalized_target_types:
            normalized = normalized_all

        normalized = cls._apply_type_ratio_filter(normalized, normalized_type_ratio)
        normalized = cls._apply_difficulty_regression_validation(normalized, normalized_target_difficulty)
        return normalized

    @classmethod
    def batch_generate_questions(
        cls,
        kp_queryset,
        count_per_kp: int = 1,
        target_types: Optional[List[str]] = None,
        target_difficulty: Any = 'normal',
    ) -> int:
        kp_ids = list(kp_queryset.values_list('id', flat=True))
        generated = cls.preview_generate_questions(
            kp_ids,
            count_per_kp=count_per_kp,
            target_types=target_types,
            target_difficulty=target_difficulty,
        )
        if not generated:
            return 0

        created = 0
        with transaction.atomic():
            for q in generated:
                if not q.get('question'):
                    continue
                Question.objects.create(
                    knowledge_point_id=q.get('kp_id'),
                    text=q['question'],
                    q_type=q['q_type'],
                    subjective_type=(q.get('subjective_type') or None) if q['q_type'] == 'subjective' else None,
                    options=q.get('options') if q['q_type'] == 'objective' else {},
                    correct_answer=q.get('answer', ''),
                    grading_points=q.get('grading_points', ''),
                    ai_answer='',
                    difficulty_level=q.get('difficulty_level', 'normal'),
                )
                created += 1

        return created

    @classmethod
    def generate_ai_answer(cls, question: Question) -> str:
        from quizzes.services.ai_task_service import QuizAITaskService

        return QuizAITaskService.generate_ai_answer(cls, question)

    @classmethod
    def grade_question(
        cls,
        question_text: str,
        user_answer: Any,
        correct_answer: Any,
        q_type: str,
        max_score: float,
        grading_points: Optional[str] = None,
        subjective_type: str = '主观题',
    ) -> Dict[str, Any]:
        from quizzes.services.ai_task_service import QuizAITaskService

        return QuizAITaskService.grade_question(
            cls,
            question_text=question_text,
            user_answer=user_answer,
            correct_answer=correct_answer,
            q_type=q_type,
            max_score=max_score,
            grading_points=grading_points,
            subjective_type=subjective_type,
        )

    @classmethod
    def generate_questions_from_text(
        cls,
        text: str,
        num_obj: int = 3,
        num_short: int = 1,
        num_essay: int = 1,
        num_calc: int = 0,
        kp_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        from quizzes.services.ai_task_service import QuizAITaskService

        return QuizAITaskService.generate_questions_from_text(
            cls,
            text=text,
            num_obj=num_obj,
            num_short=num_short,
            num_essay=num_essay,
            num_calc=num_calc,
            kp_id=kp_id,
        )

    @classmethod
    def parse_questions_from_text(cls, raw_text: str) -> List[Dict[str, Any]]:
        from quizzes.services.ai_task_service import QuizAITaskService

        return QuizAITaskService.parse_questions_from_text(cls, raw_text=raw_text)

    @classmethod
    def chat_with_assistant(
        cls,
        bot,
        history_messages: Sequence[Dict[str, str]],
        user_message: str,
        student_context: str = '',
    ):
        from ai_assistant.services.chat_service import AssistantChatService

        return AssistantChatService.chat_with_assistant(
            cls,
            bot=bot,
            history_messages=history_messages,
            user_message=user_message,
            student_context=student_context,
        )
