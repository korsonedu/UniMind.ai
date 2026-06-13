"""
IRT 3PL 参数估计服务。

实现三参数 Logistic 模型的题目参数 (a, b, c) 和学生能力 (θ) 估计。
使用 scipy.optimize.minimize 做 MLE，通过 GradingRecord 积累的答题数据驱动。

仅当某题目的 GradingRecord 数 >= MIN_RESPONSES 时触发估计。
"""

import logging
import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
from django.utils import timezone

logger = logging.getLogger(__name__)

# 估计所需最少答题记录数
MIN_RESPONSES = 50


@dataclass
class ItemEstimate:
    discrimination: float  # a 参数，区分度
    difficulty: float      # b 参数，难度
    guessing: float        # c 参数，猜测概率
    responses_count: int


class IRTEstimator:
    """3PL IRT 参数估计器。所有方法为静态方法。"""

    # ── 3PL 模型 ──────────────────────────────────────

    @staticmethod
    def p_correct(theta: float, a: float, b: float, c: float) -> float:
        """3PL 概率：c + (1-c) / (1 + exp(-a*(theta - b)))"""
        logit = -a * (theta - b)
        # 数值稳定：clamp logit 避免溢出
        logit = max(-50.0, min(50.0, logit))
        return c + (1.0 - c) / (1.0 + math.exp(logit))

    # ── 题目参数估计 ──────────────────────────────────

    @staticmethod
    def estimate_item_parameters(responses: list[dict]) -> Optional[ItemEstimate]:
        """
        估计单题的 3PL 参数 (a, b, c)。

        responses: [{'theta': float, 'is_correct': bool}, ...]
        要求 len(responses) >= MIN_RESPONSES。

        使用 MLE（L-BFGS-B）最大化 log-likelihood。
        """
        if len(responses) < MIN_RESPONSES:
            return None

        try:
            from scipy.optimize import minimize
        except ImportError:
            logger.warning("scipy not installed, skipping IRT estimation")
            return None

        thetas = np.array([r['theta'] for r in responses])
        corrects = np.array([1.0 if r['is_correct'] else 0.0 for r in responses])

        def neg_log_lik(params):
            a, b, c = params
            # 参数约束
            a = max(0.2, min(5.0, a))
            b = max(-3.0, min(3.0, b))
            c = max(0.0, min(0.5, c))

            p = c + (1.0 - c) / (1.0 + np.exp(-a * (thetas - b)))
            p = np.clip(p, 1e-6, 1.0 - 1e-6)  # 避免 log(0)
            ll = corrects * np.log(p) + (1.0 - corrects) * np.log(1.0 - p)
            return -np.sum(ll)

        # 初始值：a=1.0, b=0.0, c=0.25
        result = minimize(
            neg_log_lik,
            x0=[1.0, 0.0, 0.25],
            bounds=[(0.2, 5.0), (-3.0, 3.0), (0.0, 0.5)],
            method='L-BFGS-B',
        )

        a, b, c = result.x
        return ItemEstimate(
            discrimination=round(float(a), 3),
            difficulty=round(float(b), 3),
            guessing=round(float(c), 3),
            responses_count=len(responses),
        )

    # ── 学生能力估计 ──────────────────────────────────

    @staticmethod
    def estimate_user_ability(
        responses: list[dict],
        item_params: dict[int, ItemEstimate],
    ) -> Optional[float]:
        """
        给定题目参数，估计单个学生的 θ（能力）。

        responses: [{'question_id': int, 'is_correct': bool}, ...]
        item_params: {question_id: ItemEstimate, ...}

        只使用有 IRT 参数的题目。MLE 估计 θ。
        """
        valid = [
            r for r in responses
            if r['question_id'] in item_params
        ]
        if len(valid) < 3:
            return None

        try:
            from scipy.optimize import minimize_scalar
        except ImportError:
            return None

        thetas_est = []
        for r in valid:
            ip = item_params[r['question_id']]
            correct = 1.0 if r['is_correct'] else 0.0

            def neg_ll_single(theta):
                p = IRTEstimator.p_correct(theta, ip.discrimination, ip.difficulty, ip.guessing)
                p = max(1e-6, min(1.0 - 1e-6, p))
                return -(correct * math.log(p) + (1.0 - correct) * math.log(1.0 - p))

            result = minimize_scalar(neg_ll_single, bounds=(-3.0, 3.0), method='bounded')
            thetas_est.append(float(result.x))

        if not thetas_est:
            return None

        return round(float(np.mean(thetas_est)), 4)

    # ── 批处理入口 ────────────────────────────────────

    @staticmethod
    def run_batch_estimation(min_responses: int = MIN_RESPONSES, dry_run: bool = False,
                             institution_id: int = None):
        """
        全量批处理入口（机构隔离）。

        1. 对满足 MIN_RESPONSES 的题目按机构估计 a/b/c → ItemParameter
        2. 对每道有 ItemParameter 的题目的作答学生估计 θ → UserAbility

        institution_id: 指定机构（None = 所有机构逐个处理）
        """
        from django.contrib.auth import get_user_model
        from quizzes.models import GradingRecord, ItemParameter, UserAbility, Question
        from users.models import Institution

        User = get_user_model()

        institutions = Institution.objects.filter(is_active=True)
        if institution_id:
            institutions = institutions.filter(id=institution_id)

        result = {'items_estimated': 0, 'users_estimated': 0, 'institutions': 0}

        for inst in institutions:
            inst_result = IRTEstimator._estimate_for_institution(
                inst, min_responses, dry_run
            )
            result['items_estimated'] += inst_result['items_estimated']
            result['users_estimated'] += inst_result['users_estimated']
            result['institutions'] += 1

        items_est = result['items_estimated']
        users_est = result['users_estimated']
        inst_count = result['institutions']
        result['message'] = (
            f'完成：{items_est} 道题目的 IRT 参数已估计，'
            f'{users_est} 名学生能力已估计，'
            f'覆盖 {inst_count} 个机构'
        )
        return result

    @staticmethod
    def _estimate_for_institution(inst, min_responses: int, dry_run: bool):
        """单个机构的 IRT 参数估计"""
        from quizzes.models import GradingRecord, ItemParameter, UserAbility, Question

        # Step 1: 收集该机构的所有 GradingRecord
        records = GradingRecord.objects.filter(
            user__institution=inst
        ).select_related('question').order_by('question_id')
        question_responses: dict[int, list[dict]] = {}
        for r in records:
            if not r.question_id:
                continue
            # 用 UserQuestionStatus.stability 映射初始 θ
            from quizzes.models import UserQuestionStatus
            uqs = UserQuestionStatus.objects.filter(
                user_id=r.user_id, question_id=r.question_id
            ).first()
            init_theta = 0.0
            if uqs and uqs.stability > 1:
                # stability ∈ [1, ∞) → θ ∈ [-2, 2]
                init_theta = min(2.0, max(-2.0, math.log(uqs.stability) / 2.0 - 1.0))

            question_responses.setdefault(r.question_id, []).append({
                'theta': init_theta,
                'is_correct': r.is_correct,
            })

        # Step 2: 估计题目参数
        estimated_items: dict[int, ItemEstimate] = {}
        for qid, responses in question_responses.items():
            if len(responses) < min_responses:
                continue
            est = IRTEstimator.estimate_item_parameters(responses)
            if est is None:
                continue
            estimated_items[qid] = est
            if not dry_run:
                ItemParameter.objects.update_or_create(
                    question_id=qid,
                    institution_id=inst.id,
                    defaults={
                        'discrimination': est.discrimination,
                        'difficulty': est.difficulty,
                        'guessing': est.guessing,
                        'responses_count': est.responses_count,
                        'last_estimated_at': timezone.now(),
                    },
                )
            logger.info(
                "IRT item %d: a=%.3f b=%.3f c=%.3f (n=%d)",
                qid, est.discrimination, est.difficulty, est.guessing, est.responses_count,
            )

        if not estimated_items:
            return {
                'items_estimated': 0,
                'users_estimated': 0,
                'message': '没有满足最小答题数要求的题目',
                'min_responses': min_responses,
            }

        # Step 3: 估计学生能力
        user_responses: dict[int, list[dict]] = {}
        for r in records:
            if r.question_id in estimated_items:
                user_responses.setdefault(r.user_id, []).append({
                    'question_id': r.question_id,
                    'is_correct': r.is_correct,
                })

        # 获取题目→知识点映射
        question_kp = dict(
            Question.objects.filter(id__in=list(estimated_items.keys()))
            .values_list('id', 'knowledge_point_id')
        )

        users_estimated = 0
        for uid, responses in user_responses.items():
            theta = IRTEstimator.estimate_user_ability(responses, estimated_items)
            if theta is None:
                continue

            # 按知识点聚合，对每个知识点写入 UserAbility
            kp_thetas: dict[int, list[float]] = {}
            for r in responses:
                kp_id = question_kp.get(r['question_id'])
                if kp_id:
                    kp_thetas.setdefault(kp_id, []).append(theta)

            if not dry_run:
                for kp_id, thetas in kp_thetas.items():
                    avg_theta = round(float(np.mean(thetas)), 4)
                    UserAbility.objects.update_or_create(
                        user_id=uid,
                        knowledge_point_id=kp_id,
                        institution_id=inst.id,
                        defaults={
                            'theta': avg_theta,
                            'responses_count': len(thetas),
                        },
                    )
                    users_estimated += 1

        return {
            'items_estimated': len(estimated_items),
            'users_estimated': users_estimated,
            'total_questions': len(question_responses),
            'message': f'完成：{len(estimated_items)} 道题目的 IRT 参数已估计',
        }
