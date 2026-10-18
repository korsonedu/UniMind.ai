"""
MemorixService — Production bridge between MemorixOptimizer and Django models.

Core algorithm:
  - Weibull forgetting curve:  R(t) = exp(-(t/λ)^k)
  - Online SGD with Nesterov momentum after every review
  - Brier score loss (strictly proper scoring rule)
  - Regret-minimizing review scheduling
  - Per-user weight vectors persisted in MemorixProfile.weights

Usage:
    status = MemorixService.update_status(user_id, status, rating)
"""

import math
import logging
from typing import Optional

import numpy as np
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from quizzes.models import UserQuestionStatus, MemorixProfile, ReviewLog
from users.models import User
from quizzes.memorix.optimizer import MemorixOptimizer, MEMORIX_DEFAULT_WEIGHTS, W_WEIBULL_K

logger = logging.getLogger(__name__)


def _get_optimizer(user_id: int, profile=None) -> MemorixOptimizer:
    if profile is None:
        profile = MemorixProfile.objects.filter(user_id=user_id).first()
    weights = profile.weights if profile and len(profile.weights or []) == 20 else MEMORIX_DEFAULT_WEIGHTS
    opt = MemorixOptimizer(weights=np.array(weights, dtype=np.float64))
    state = profile.optimizer_state if profile else {}
    if state:
        opt.weights = np.array(state['weights'], dtype=np.float64)
        opt.ema_weights = np.array(state['ema_weights'], dtype=np.float64)
        opt.velocity = np.array(state['velocity'], dtype=np.float64)
        opt.update_count = state['update_count']
        opt.lr = state['learning_rate']
    return opt


def _save_weights(profile: MemorixProfile, opt: MemorixOptimizer):
    """Save all online learning state together with its serving weights."""
    profile.weights = opt.ema_weights.tolist()
    profile.optimizer_state = {
        'weights': opt.weights.tolist(),
        'ema_weights': opt.ema_weights.tolist(),
        'velocity': opt.velocity.tolist(),
        'update_count': opt.update_count,
        'learning_rate': opt.lr,
    }
    profile.total_reviews_used = opt.update_count
    profile.last_optimized_at = timezone.now()
    profile.save(update_fields=['weights', 'optimizer_state', 'total_reviews_used', 'last_optimized_at'])


def load_optimizer(user_id: int) -> MemorixOptimizer:
    """Load one fresh per-user optimizer snapshot for batch predictions."""
    return _get_optimizer(user_id)


def predict_retrievability(
    stability: float,
    elapsed_days: float,
    user_id: Optional[int] = None,
    optimizer: Optional[MemorixOptimizer] = None,
) -> float:
    """
    Weibull forgetting curve: R(t) = exp(-(t/λ)^k)
    Uses population k (w17) if no user_id provided, otherwise per-user k.
    Pass optimizer to reuse one parameter snapshot across a batch.
    """
    if stability <= 0:
        return 0.0
    if optimizer is None and user_id:
        optimizer = _get_optimizer(user_id)
    if optimizer is not None:
        k = max(0.1, min(5.0, optimizer.weights[W_WEIBULL_K]))
    else:
        k = float(MEMORIX_DEFAULT_WEIGHTS[W_WEIBULL_K])
    t_over_lambda = max(0.0, float(elapsed_days) / max(float(stability), 0.01))
    return float(math.exp(-(t_over_lambda ** k)))


class MemorixService:
    """Production interface for Memorix scheduling operations."""

    @staticmethod
    @transaction.atomic
    def update_status(user_id: int, status: UserQuestionStatus, rating: int) -> UserQuestionStatus:
        """
        Update a UserQuestionStatus using Memorix Weibull-based stability/difficulty
        calculation, then perform online SGD weight update.

        rating: 1=Again, 2=Hard, 3=Good, 4=Easy
        """
        # Every learning write uses the same user -> status -> profile lock order.
        User.objects.select_for_update().get(pk=user_id)
        status = UserQuestionStatus.objects.select_for_update().get(pk=status.pk, user_id=user_id)
        profile, _ = MemorixProfile.objects.get_or_create(user_id=user_id)
        profile = MemorixProfile.objects.select_for_update().get(pk=profile.pk)
        opt = _get_optimizer(user_id, profile=profile)
        w = opt.weights
        now = timezone.now()
        rating = max(1, min(4, rating))

        # ── Compute elapsed days since last review ──
        if status.reps == 0 or not status.last_review:
            elapsed_days = 0.0
        else:
            elapsed_days = max(0.0, (now - status.last_review).total_seconds() / 86400.0)

        previous_stability = status.stability
        previous_difficulty = status.difficulty
        first_review = status.reps == 0
        retrievability = 0.0 if first_review else opt.predict_retrievability(previous_stability, elapsed_days)

        if first_review:
            # ── Initial learning ──
            status.stability = float(w[rating - 1])  # w0..w3
            status.difficulty = float(w[4]) - (rating - 3) * float(w[5])  # w4, w5
            status.difficulty = max(1.0, min(10.0, status.difficulty))
            status.reps = 1
            status.last_review = now
            status.next_review_at = now + timezone.timedelta(days=max(1, round(status.stability)))
        else:
            # ── Difficulty update ──
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

        kp_id = status.question.knowledge_point_id
        if kp_id:
            ReviewLog.objects.create(
                user_id=user_id,
                knowledge_point_id=kp_id,
                grade=rating,
                elapsed_days=elapsed_days,
                predicted_retrievability=retrievability,
            )

        if not first_review:
            opt.update(
                grade=rating,
                elapsed_days=elapsed_days,
                stability=previous_stability,
                difficulty=previous_difficulty,
                retrievability_pred=retrievability,
            )
            _save_weights(profile, opt)

        # ── Memorix-Field: 复习传播 ──
        if not first_review and kp_id and getattr(settings, 'MEMORIX_FIELD_ENABLED', False) and rating >= 3:
            inst_id = status.user.institution_id

            def propagate():
                from quizzes.memorix.field import propagate_review
                try:
                    propagate_review(user_id, kp_id, retrievability, institution_id=inst_id)
                except Exception:
                    logger.exception('Memorix field propagation failed for user %s', user_id)

            transaction.on_commit(propagate)

        return status

    @staticmethod
    def predict_retrievability(
        stability: float,
        elapsed_days: float,
        user_id: Optional[int] = None,
        optimizer: Optional[MemorixOptimizer] = None,
    ) -> float:
        """Weibull forgetting curve: R(t) = exp(-(t/λ)^k)."""
        return predict_retrievability(stability, elapsed_days, user_id, optimizer)

    @staticmethod
    @transaction.atomic
    def flush_user_weights(user_id: int):
        """Online updates are durable already; preserve the explicit flush API."""
        User.objects.select_for_update().get(pk=user_id)
        profile = MemorixProfile.objects.select_for_update().filter(user_id=user_id).first()
        if profile:
            _save_weights(profile, _get_optimizer(user_id, profile=profile))
