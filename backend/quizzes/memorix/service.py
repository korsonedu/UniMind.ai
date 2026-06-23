"""
MemorixService — Production bridge between MemorixOptimizer and Django models.

Replaces quizzes.fsrs.FSRS with the full Memorix algorithm:
  - Weibull forgetting curve:  R(t) = exp(-(t/λ)^k)
  - Online SGD with Nesterov momentum after every review
  - Brier score loss (strictly proper scoring rule)
  - Regret-minimizing review scheduling
  - Per-user weight vectors persisted in MemorixProfile.weights

Usage (replaces FSRS.update_status):
    status = MemorixService.update_status(user_id, status, rating)
"""

import math
import logging
from functools import lru_cache
from typing import Optional

import numpy as np
from django.conf import settings
from django.utils import timezone

from quizzes.models import UserQuestionStatus, MemorixProfile
from quizzes.memorix.optimizer import MemorixOptimizer, MEMORIX_DEFAULT_WEIGHTS, W_WEIBULL_K

logger = logging.getLogger(__name__)


@lru_cache(maxsize=5000)
def _load_weights(user_id: int) -> tuple:
    profile = MemorixProfile.objects.filter(user_id=user_id).first()
    if profile and profile.weights and len(profile.weights) == 20:
        return tuple(round(w, 6) for w in profile.weights)
    return tuple(MEMORIX_DEFAULT_WEIGHTS)


def _get_optimizer(user_id: int) -> MemorixOptimizer:
    weights = np.array(_load_weights(user_id), dtype=np.float64)
    return MemorixOptimizer(weights=weights)


def _save_weights(user_id: int, opt: MemorixOptimizer):
    """Persist EMA-smoothed weights back to MemorixProfile."""
    weights_list = [round(float(w), 6) for w in opt.ema_weights]
    MemorixProfile.objects.update_or_create(
        user_id=user_id,
        defaults={
            'weights': weights_list,
            'total_reviews_used': opt.update_count,
            'last_optimized_at': timezone.now(),
        },
    )


def predict_retrievability(stability: float, elapsed_days: float, user_id: Optional[int] = None) -> float:
    """
    Weibull forgetting curve: R(t) = exp(-(t/λ)^k)
    Uses population k (w17) if no user_id provided, otherwise per-user k.
    """
    if stability <= 0:
        return 0.0
    if user_id:
        opt = _get_optimizer(user_id)
        k = max(0.1, min(5.0, opt.weights[W_WEIBULL_K]))
    else:
        k = float(MEMORIX_DEFAULT_WEIGHTS[W_WEIBULL_K])
    t_over_lambda = max(0.0, float(elapsed_days) / max(float(stability), 0.01))
    return float(math.exp(-(t_over_lambda ** k)))


class MemorixService:
    """Production interface — mirrors the old FSRS class API."""

    @staticmethod
    def update_status(user_id: int, status: UserQuestionStatus, rating: int) -> UserQuestionStatus:
        """
        Update a UserQuestionStatus using Memorix Weibull-based stability/difficulty
        calculation, then perform online SGD weight update.

        rating: 1=Again, 2=Hard, 3=Good, 4=Easy
        """
        opt = _get_optimizer(user_id)
        w = opt.weights
        now = timezone.now()
        rating = max(1, min(4, rating))

        # ── Compute elapsed days since last review ──
        if status.reps == 0 or not status.last_review:
            elapsed_days = 0.0
        else:
            elapsed_days = max(0.0, (now - status.last_review).total_seconds() / 86400.0)

        if status.reps == 0:
            # ── Initial learning ──
            status.stability = float(w[rating - 1])  # w0..w3
            status.difficulty = float(w[4]) - (rating - 3) * float(w[5])  # w4, w5
            status.difficulty = max(1.0, min(10.0, status.difficulty))
            status.reps = 1
            status.last_review = now
            status.next_review_at = now + timezone.timedelta(days=max(1, round(status.stability)))
            status.save()
            return status

        # ── Review (Memorix: Weibull retrievability) ──
        retrievability = predict_retrievability(status.stability, elapsed_days, user_id)

        # ── Difficulty update (FSRS-compatible) ──
        status.difficulty = status.difficulty - float(w[5]) * (rating - 3)
        status.difficulty = float(w[7]) * float(w[4]) + (1 - float(w[7])) * status.difficulty
        status.difficulty = max(1.0, min(10.0, status.difficulty))

        # ── Stability update ──
        if rating == 1:  # Again — lapse
            status.stability = (
                float(w[11])
                * (status.difficulty ** -float(w[12]))
                * ((status.stability + 1) ** float(w[13]) - 1)
                * math.exp(float(w[14]) * (1 - retrievability))
            )
            status.lapses += 1
        else:  # Success: grade ∈ {2, 3, 4}
            s_inc = (
                math.exp(float(w[8]))
                * (11 - status.difficulty)
                * (status.stability ** -float(w[9]))
                * (math.exp(float(w[10]) * (1 - retrievability)) - 1)
            )
            if rating == 2:  # Hard
                status.stability = status.stability * (1 + s_inc * float(w[15]))
            elif rating == 3:  # Good
                status.stability = status.stability * (1 + s_inc)
            else:  # Easy
                status.stability = status.stability * (1 + s_inc * float(w[16]))

        status.stability = max(0.01, status.stability)
        status.reps += 1
        status.last_review = now

        # ── Next review: regret-minimizing schedule ──
        k = max(0.1, min(5.0, float(w[17])))
        target_r = 0.90
        lo, hi = 0.1, max(365.0, status.stability * 5)
        for _ in range(50):
            mid = (lo + hi) / 2
            r_mid = math.exp(-(mid / max(status.stability, 0.01)) ** k)
            if r_mid >= target_r:
                lo = mid
            else:
                hi = mid
        interval_days = max(1, round(lo))
        status.next_review_at = now + timezone.timedelta(days=interval_days)

        status.save()

        # ── Online SGD learning step ──
        opt.update(
            grade=rating,
            elapsed_days=elapsed_days,
            stability=status.stability,
            difficulty=status.difficulty,
            retrievability_pred=retrievability,
        )

        # Persist weights every 10 reviews
        if opt.update_count % 10 == 0:
            _save_weights(user_id, opt)

        # ── Memorix-Field: 复习传播 ──
        if getattr(settings, 'MEMORIX_FIELD_ENABLED', False) and rating >= 3:
            from quizzes.memorix.field import propagate_review
            try:
                kp_id = status.question.knowledge_point_id
                if kp_id:
                    inst_id = getattr(status.user, 'institution_id', None)
                    propagate_review(user_id, kp_id, retrievability, institution_id=inst_id)
            except Exception:
                pass  # 传播失败不影响主流程

        return status

    @staticmethod
    def predict_retrievability(stability: float, elapsed_days: float, user_id: Optional[int] = None) -> float:
        """Weibull forgetting curve: R(t) = exp(-(t/λ)^k)."""
        return predict_retrievability(stability, elapsed_days, user_id)

    @staticmethod
    def flush_user_weights(user_id: int):
        """Force-save weights and clear from cache."""
        opt = _get_optimizer(user_id)
        _save_weights(user_id, opt)
        _load_weights.cache_clear()
