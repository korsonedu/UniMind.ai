import json
import logging
import random
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from django.conf import settings
from django.db import transaction
from django.db.models import Q

from ai_engine.service import AICallError
from quizzes.models import KnowledgePoint, Question
# prompt_resources removed — shared constraints now inlined into prompt templates
from ai_engine.tools import QUESTION_LIST_SCHEMA
from quizzes.services.question_normalizer import (
    normalize_question_type,
    normalize_difficulty_level,
    normalize_target_difficulty,
    normalize_options,
    normalize_objective_answer,
    normalize_noun_question_text,
    canonical_question_type_key,
    normalize_target_types,
    normalize_target_type_ratio,
    render_target_type_ratio,
    DIFFICULTY_ORDER,
    TYPE_RATIO_LABELS,
)

logger = logging.getLogger(__name__)


class QuestionGenerator:
    """题目生成器：从 AIService 剥离的题目生成与校验逻辑。"""

    def __init__(self, ai_service_cls):
        self.ai_service = ai_service_cls

    # ------------------------------------------------------------------
    # 批量生成估算
    # ------------------------------------------------------------------

    def _estimate_bulk_generate_max_tokens(self, count_per_kp: int) -> int:
        # 单次请求按题目数动态分配 token。
        # DeepSeek reasoning 模式会消耗 2000+ tokens 做内部推理，需要额外预留。
        c = max(1, int(count_per_kp or 1))
        return max(4000, min(8192, 3000 + c * 1500))

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # 单轮批量生成请求
    # ------------------------------------------------------------------

    def _request_bulk_generate_once(
        self,
        kps_data: Sequence[Dict[str, Any]],
        count_per_kp: int,
        target_types: Optional[List[str]],
        target_difficulty: str,
        target_type_ratio_text: str,
    ) -> List[Dict[str, Any]]:
        template = self.ai_service.get_template('quizzes', 'bulk_generate_prompt.txt') or ''
        prompt = self.ai_service.format_template(
            template,
            count_per_kp=max(1, int(count_per_kp or 1)),
            target_types=', '.join(target_types or []),
            target_difficulty=target_difficulty,
            target_type_ratio=target_type_ratio_text,
            knowledge_points_json=json.dumps(list(kps_data), ensure_ascii=False, indent=2),
        )

        logger.info(
            "ai.bulk_generate request: kp_count=%s count_per_kp=%s prompt_chars=%s",
            len(kps_data),
            count_per_kp,
            len(prompt),
        )

        max_tokens = self._estimate_bulk_generate_max_tokens(count_per_kp)
        data = self.ai_service.structured_output(
            system_prompt="",
            user_prompt=prompt,
            schema=QUESTION_LIST_SCHEMA,
            tool_name="submit_questions",
            tool_description="提交生成的题目列表",
            temperature=0.35,
            max_tokens=max_tokens,
            raise_on_error=True,
            operation='quizzes.bulk_generate',
        )

        # 重试一次：降 temperature、提 max_tokens
        if not isinstance(data, list):
            logger.info(
                "_request_bulk_generate_once retrying: kp_count=%s count_per_kp=%s",
                len(kps_data), count_per_kp,
            )
            data = self.ai_service.structured_output(
                system_prompt="",
                user_prompt=prompt,
                schema=QUESTION_LIST_SCHEMA,
                tool_name="submit_questions",
                tool_description="提交生成的题目列表",
                temperature=0.15,
                max_tokens=8192,
                raise_on_error=False,
                operation='quizzes.bulk_generate',
            )

        if not isinstance(data, list):
            logger.warning("_request_bulk_generate_once failed after retry")
            raise AICallError(
                "AI 命题结果格式异常，请重试。",
                status_code=502,
                retryable=True,
                error_category='schema_invalid',
            )
        return data

    # ------------------------------------------------------------------
    # 题型 key 提取
    # ------------------------------------------------------------------

    def _question_type_key_from_clean_data(self, question: Dict[str, Any]) -> str:
        return canonical_question_type_key(question.get('q_type'), question.get('subjective_type'))

    # ------------------------------------------------------------------
    # 难度估计
    # ------------------------------------------------------------------

    # 学科分组（用于难度信号匹配）
    SUBJECT_GROUP_MATH = {'高中数学', '高中物理', '计算机408'}
    SUBJECT_GROUP_FINANCE = {'金融431', 'CFA', 'CPA', '金融431_完整版'}
    SUBJECT_GROUP_LAW = {'法学', '法考'}
    SUBJECT_GROUP_EDU = {'教资', '教育学311'}
    SUBJECT_GROUP_MED = {'USMLE'}

    # 通用学术信号（跨学科）
    GENERAL_HARD_SIGNALS = ['推导', '证明', '比较', '辨析', '评价', '边界', '反例']
    GENERAL_EXTREME_SIGNALS = ['批判性', '模型选择', '多目标', '稳健性']

    # 学科专用信号
    DOMAIN_SIGNALS = {
        'math': {
            'hard': ['综合应用', '构造', '参数讨论', '分类讨论', '数形结合', '递推'],
            'extreme': ['存在性', '唯一性', '不等式证明', '极值问题', '收敛性'],
            'calc': ['=', 'Δ', '∂', 'σ', 'β', '∑', '∫', 'lim', '→', '∞'],
        },
        'finance': {
            'hard': ['政策建议', '一般均衡', '跨市场', '传导机制', '约束条件', '情景分析', '敏感性'],
            'extreme': ['现实偏离', '制度约束', '市场失灵', '逆向选择', '道德风险'],
            'calc': ['NPV', 'IRR', 'CAPM', 'WACC', 'r=', 'β', 'σ'],
        },
        'law': {
            'hard': ['构成要件', '法律关系', '归责原则', '竞合', '解释论', '立法论'],
            'extreme': ['法理辨析', '比较法', '漏洞填补', '利益衡量', '合宪性'],
            'calc': [],
        },
        'edu': {
            'hard': ['教学策略', '学习迁移', '认知发展', '课程设计', '评价体系'],
            'extreme': ['建构主义', '元认知', '最近发展区', '质性研究'],
            'calc': [],
        },
        'med': {
            'hard': ['鉴别诊断', '病理生理', '临床表现', '治疗原则', '并发症'],
            'extreme': ['循证医学', '多学科', '预后评估', '罕见病'],
            'calc': [],
        },
    }

    def _get_subject_signals(self, subject: str):
        """根据学科名称返回对应的信号词组。"""
        s = (subject or '').strip()
        if s in self.SUBJECT_GROUP_MATH:
            return self.DOMAIN_SIGNALS['math']
        if s in self.SUBJECT_GROUP_FINANCE:
            return self.DOMAIN_SIGNALS['finance']
        if s in self.SUBJECT_GROUP_LAW:
            return self.DOMAIN_SIGNALS['law']
        if s in self.SUBJECT_GROUP_EDU:
            return self.DOMAIN_SIGNALS['edu']
        if s in self.SUBJECT_GROUP_MED:
            return self.DOMAIN_SIGNALS['med']
        # 未知学科用通用信号（避免默认偏向数学）
        return {
            'structure': ['因为', '所以', '根据', '由此'],
            'quant': ['%', '约', '比例', '比率'],
            'formula': [],
        }

    def _estimate_difficulty_level(self, question: Dict[str, Any], subject: str = '') -> str:
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

        domain = self._get_subject_signals(subject)
        hard_signals = self.GENERAL_HARD_SIGNALS + domain['hard']
        extreme_signals = self.GENERAL_EXTREME_SIGNALS + domain['extreme']
        calc_signals = domain['calc']

        combined = text + answer
        hard_hits = sum(1 for token in hard_signals if token in combined)
        extreme_hits = sum(1 for token in extreme_signals if token in combined)
        calc_hits = sum(1 for token in calc_signals if token in combined)

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

    # ------------------------------------------------------------------
    # 难度校验
    # ------------------------------------------------------------------

    def _apply_difficulty_regression_validation(
        self,
        questions: List[Dict[str, Any]],
        target_difficulty: str,
        subject: str = '',
    ) -> List[Dict[str, Any]]:
        if not getattr(settings, 'AI_DIFFICULTY_CHECK_ENABLED', True):
            for q in questions:
                q['difficulty_estimated_level'] = self._estimate_difficulty_level(q, subject)
                q['difficulty_check_passed'] = True
                q['difficulty_level'] = target_difficulty
            return questions

        if target_difficulty == 'mixed':
            for q in questions:
                estimated_level = self._estimate_difficulty_level(q, subject)
                q['difficulty_estimated_level'] = estimated_level
                q['difficulty_check_passed'] = True
                q['difficulty_level'] = target_difficulty
            return questions

        target_rank = DIFFICULTY_ORDER.get(target_difficulty, DIFFICULTY_ORDER['normal'])
        tolerance = 1
        for q in questions:
            estimated_level = self._estimate_difficulty_level(q, subject)
            estimated_rank = DIFFICULTY_ORDER.get(estimated_level, DIFFICULTY_ORDER['normal'])
            distance = abs(estimated_rank - target_rank)
            q['difficulty_estimated_level'] = estimated_level
            q['difficulty_check_passed'] = distance <= tolerance
            q['difficulty_level'] = target_difficulty
        return questions

    # ------------------------------------------------------------------
    # 题型比例过滤
    # ------------------------------------------------------------------

    def _apply_type_ratio_filter(
        self,
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
            key = self._question_type_key_from_clean_data(q)
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

    # ------------------------------------------------------------------
    # 标准化单道生成题目
    # ------------------------------------------------------------------

    def _normalize_generated_question(
        self,
        raw: Dict[str, Any],
        kp_by_code: Dict[str, KnowledgePoint],
        kp_by_id: Dict[int, KnowledgePoint],
        fallback_kp: Optional[KnowledgePoint],
        include_explanation: bool = False,
    ) -> Optional[Dict[str, Any]]:
        q_type, subjective_type = normalize_question_type(
            raw.get('q_type') or raw.get('question_type') or raw.get('type'),
            raw.get('subjective_type'),
        )

        question_text = str(raw.get('question') or raw.get('text') or '').strip()
        if q_type == 'subjective' and subjective_type == 'noun':
            question_text = normalize_noun_question_text(question_text)
        if not question_text:
            return None

        options = normalize_options(raw.get('options')) if q_type == 'objective' else {}
        answer = str(raw.get('answer') or raw.get('correct_answer') or '').strip()
        if q_type == 'objective':
            answer = normalize_objective_answer(answer, options)

        difficulty_level = normalize_difficulty_level(raw.get('difficulty_level'), raw.get('difficulty'))

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
            grading_points = str(raw.get('grading_points') or '').strip() or self.ai_service.default_grading_points(subjective_type)

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

    # ------------------------------------------------------------------
    # 降级：从本地题库抽取
    # ------------------------------------------------------------------

    def _fallback_fetch_local_questions(
        self,
        kps,
        count_per_kp: int,
        target_types: Optional[List[str]],
        target_difficulty: Any,
        institution=None,
    ) -> List[Dict[str, Any]]:
        fallback_results = []
        for kp in kps:
            qs = Question.objects.filter(knowledge_point=kp)
            if institution:
                qs = qs.filter(institution=institution)
            if target_difficulty and target_difficulty != 'mixed':
                qs = qs.filter(difficulty_level=target_difficulty)

            q_list = list(qs)
            if q_list:
                sampled = random.sample(q_list, min(len(q_list), count_per_kp))
                for q in sampled:
                    fallback_results.append({
                        'q_type': q.q_type,
                        'subjective_type': q.subjective_type or '',
                        'question': q.text,
                        'options': q.options or {},
                        'answer': q.correct_answer,
                        'grading_points': q.grading_points,
                        'difficulty_level': q.difficulty_level,
                        'related_knowledge_id': kp.code,
                        'kp_name': kp.name,
                        'kp_id': kp.id,
                        'is_fallback': True,
                    })
        return fallback_results

    # ------------------------------------------------------------------
    # 主入口：预览生成
    # ------------------------------------------------------------------

    def preview_generate_questions(
        self,
        kp_ids: Iterable[int],
        count_per_kp: int = 1,
        target_types: Optional[List[str]] = None,
        target_difficulty: Any = 'normal',
        target_type_ratio: Optional[Dict[str, Any]] = None,
        institution=None,
        on_progress=None,
    ):
        kps = list(KnowledgePoint.objects.filter(id__in=list(kp_ids), level='kp').order_by('id'))
        if not kps:
            return []

        subject = (kps[0].subject or '').strip() if kps else ''

        normalized_target_difficulty = normalize_target_difficulty(target_difficulty)
        normalized_target_types = normalize_target_types(target_types)
        normalized_type_ratio = normalize_target_type_ratio(target_type_ratio, target_types)
        target_type_ratio_text = render_target_type_ratio(
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

        total_jobs = len(jobs)
        completed_jobs = 0
        job_results: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
        if jobs:
            failed_kp_ids: set[int] = set()
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
                        self._request_bulk_generate_once,
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
                        result = future.result()
                        job_results[(kp_id, batch_index)] = result
                        completed_jobs += 1
                        if on_progress:
                            on_progress(completed_jobs, total_jobs, len(result))
                    except KeyboardInterrupt:
                        for pending in future_map:
                            if not pending.done():
                                pending.cancel()
                        raise
                    except Exception as exc:
                        failed_kp_ids.add(kp_id)
                        logger.warning(
                            "ai.bulk_generate job failed: kp_id=%s batch=%s err=%s",
                            kp_id, batch_index, exc,
                        )

            # 部分失败降级：只对失败的 KP 从本地题库抽题
            if failed_kp_ids:
                failed_kps = [kp for kp in kps if kp.id in failed_kp_ids]
                fallback_qs = self._fallback_fetch_local_questions(
                    failed_kps, total_per_kp, normalized_target_types,
                    normalized_target_difficulty,
                    institution=institution,
                )
                if fallback_qs:
                    for fq in fallback_qs:
                        key = (fq['kp_id'], 0)
                        if key not in job_results:
                            job_results[key] = []
                        job_results[key].append(fq)
                    logger.info(
                        "AI 命题部分成功: %s/%s KPs LLM生成, %s KPs 降级本地题库",
                        len(kps) - len(failed_kps), len(kps), len(failed_kps),
                    )

        for kp, batch_index, _ in jobs:
            data_batch = job_results.get((kp.id, batch_index), [])
            for item in data_batch:
                clean = self._normalize_generated_question(item, kp_by_code, kp_by_id, kp, include_explanation=False)
                if not clean:
                    continue
                normalized_all.append(clean)
                clean_type_key = self._question_type_key_from_clean_data(clean)
                if normalized_target_types and clean_type_key not in normalized_target_types:
                    continue
                normalized.append(clean)

        if not normalized and normalized_target_types:
            normalized = normalized_all

        normalized = self._apply_type_ratio_filter(normalized, normalized_type_ratio)
        normalized = self._apply_difficulty_regression_validation(normalized, normalized_target_difficulty, subject)
        return normalized

    # ------------------------------------------------------------------
    # 主入口：批量生成并持久化
    # ------------------------------------------------------------------

    def batch_generate_questions(
        self,
        kp_queryset,
        count_per_kp: int = 1,
        target_types: Optional[List[str]] = None,
        target_difficulty: Any = 'normal',
        institution=None,
    ) -> int:
        kp_ids = list(kp_queryset.values_list('id', flat=True))
        generated = self.preview_generate_questions(
            kp_ids,
            count_per_kp=count_per_kp,
            target_types=target_types,
            target_difficulty=target_difficulty,
            institution=institution,
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
                    institution=institution,
                )
                created += 1

        return created

    # ------------------------------------------------------------------
    # 委托至 QuizAITaskService
    # ------------------------------------------------------------------

    def generate_ai_answer(self, question: Question) -> str:
        from quizzes.services.ai_task_service import QuizAITaskService

        return QuizAITaskService.generate_ai_answer(self.ai_service, question)

    def grade_question(
        self,
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
        from quizzes.services.ai_task_service import QuizAITaskService

        return QuizAITaskService.grade_question(
            self.ai_service,
            question_text=question_text,
            user_answer=user_answer,
            correct_answer=correct_answer,
            q_type=q_type,
            max_score=max_score,
            grading_points=grading_points,
            rubric=rubric,
            options=options,
            subjective_type=subjective_type,
        )

    def generate_questions_from_text(
        self,
        text: str,
        num_obj: int = 3,
        num_short: int = 1,
        num_essay: int = 1,
        num_calc: int = 0,
        kp_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        from quizzes.services.ai_task_service import QuizAITaskService

        return QuizAITaskService.generate_questions_from_text(
            self.ai_service,
            text=text,
            num_obj=num_obj,
            num_short=num_short,
            num_essay=num_essay,
            num_calc=num_calc,
            kp_id=kp_id,
        )

    def parse_questions_from_text(self, raw_text: str) -> List[Dict[str, Any]]:
        from quizzes.services.ai_task_service import QuizAITaskService

        return QuizAITaskService.parse_questions_from_text(self.ai_service, raw_text=raw_text)
