"""Unified Online Knowledge Tracing & Memory Mastery Estimator (Memorix-KT).

Unifies UniMind's previously disconnected educational state signals into one
calibrated, O(1)-per-step probabilistic mastery estimator:
  1. Empirical-Bayes item & knowledge-point difficulty priors (IRT / Elo aligned)
  2. Cross-KC global student ability θ_global + fast session momentum θ_recent
  3. Per-KC mastery residual θ_kc with Weibull temporal forgetting decay
  4. Memorix-Field graph residual propagation across related knowledge points
  5. Practice win/fail log-counts (DAS3H-style) & BEP assistance weights
"""

from collections import defaultdict
from dataclasses import dataclass, field
import math
from typing import Dict, Hashable, Iterable, List, Optional, Tuple


ASSISTANCE_WEIGHTS = {
    "independent": 1.0,
    "hint": 0.35,
    "guided": 0.0,
    "unknown": 0.0,
}


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-20.0, min(20.0, x))))


def _logit(p: float) -> float:
    p = min(max(float(p), 0.015), 0.985)
    return math.log(p / (1.0 - p))


@dataclass
class MasteryConfig:
    """Hyperparameters for UnifiedMasteryEstimator (calibrated, zero-NN O(1) online KT)."""

    global_prior: float = 0.70
    prior_strength: float = 5.0
    # Prediction weights
    w_global: float = 0.90
    w_recent: float = 0.35
    w_kc: float = 0.72
    w_graph: float = 0.35
    w_log_wins: float = 0.14
    w_log_fails: float = 0.20
    # Online update rates
    lr_global: float = 0.18
    lr_kc: float = 0.32
    lr_graph: float = 0.06
    recent_decay: float = 0.80
    # Weibull temporal decay for per-KC mastery residual
    weibull_lambda_days: float = 30.0
    weibull_k: float = 0.823


@dataclass
class StudentMasteryState:
    """Mutable per-student online mastery state (JSON-serializable via to_dict/from_dict)."""

    theta_global: float = 0.0
    theta_recent: float = 0.0
    theta_kc: Dict[Hashable, float] = field(default_factory=lambda: defaultdict(float))
    kc_wins: Dict[Hashable, float] = field(default_factory=lambda: defaultdict(float))
    kc_fails: Dict[Hashable, float] = field(default_factory=lambda: defaultdict(float))
    last_kc_ts_sec: Dict[Hashable, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "theta_global": round(self.theta_global, 6),
            "theta_recent": round(self.theta_recent, 6),
            "theta_kc": {str(k): round(v, 6) for k, v in self.theta_kc.items()},
            "kc_wins": {str(k): round(v, 6) for k, v in self.kc_wins.items()},
            "kc_fails": {str(k): round(v, 6) for k, v in self.kc_fails.items()},
            "last_kc_ts_sec": {str(k): v for k, v in self.last_kc_ts_sec.items()},
        }


class UnifiedMasteryEstimator:
    """Calibrated online mastery predictor unifying IRT/Elo, Memorix-Field, Weibull decay & BEP."""

    def __init__(
        self,
        config: Optional[MasteryConfig] = None,
        kc_priors: Optional[Dict[Hashable, float]] = None,
        question_priors: Optional[Dict[Hashable, float]] = None,
        kc_graph: Optional[Dict[Hashable, List[Tuple[Hashable, float]]]] = None,
    ):
        self.config = config or MasteryConfig()
        self.g_logit = _logit(self.config.global_prior)
        self.kc_bias: Dict[Hashable, float] = {
            k: _logit(p) - self.g_logit for k, p in (kc_priors or {}).items()
        }
        self.question_bias: Dict[Hashable, float] = {
            q: _logit(p) - self.g_logit for q, p in (question_priors or {}).items()
        }
        # Normalize outgoing neighbor weights per KC
        self.kc_graph: Dict[Hashable, List[Tuple[Hashable, float]]] = {}
        for src, edges in (kc_graph or {}).items():
            pos = [(dst, float(w)) for dst, w in edges if w > 0]
            tot = sum(w for _, w in pos)
            if tot > 0:
                self.kc_graph[src] = [(dst, w / tot) for dst, w in pos]

    @classmethod
    def fit_priors(
        cls,
        interactions: Iterable[Tuple[Optional[Hashable], Hashable, int]],
        *,
        config: Optional[MasteryConfig] = None,
        kc_graph: Optional[Dict[Hashable, List[Tuple[Hashable, float]]]] = None,
    ) -> "UnifiedMasteryEstimator":
        """Fit empirical-Bayes population priors from training (question_id, kc_id, correct) tuples."""
        cfg = config or MasteryConfig()
        q_cnt: Dict[Hashable, List[int]] = defaultdict(lambda: [0, 0])
        c_cnt: Dict[Hashable, List[int]] = defaultdict(lambda: [0, 0])
        tot_ok, tot_n = 0, 0
        for q, c, y in interactions:
            y_int = 1 if y else 0
            tot_ok += y_int
            tot_n += 1
            c_cnt[c][0] += y_int
            c_cnt[c][1] += 1
            if q is not None:
                q_cnt[q][0] += y_int
                q_cnt[q][1] += 1
        gmean = (tot_ok / tot_n) if tot_n else cfg.global_prior
        m = cfg.prior_strength
        cfg_fitted = MasteryConfig(**{**cfg.__dict__, "global_prior": gmean})
        kc_priors = {c: (ok + m * gmean) / (n + m) for c, (ok, n) in c_cnt.items()}
        q_priors = {q: (ok + m * gmean) / (n + m) for q, (ok, n) in q_cnt.items()}
        return cls(config=cfg_fitted, kc_priors=kc_priors, question_priors=q_priors, kc_graph=kc_graph)

    def _weibull_decay(self, state: StudentMasteryState, kc_id: Hashable, ts_sec: Optional[float]) -> float:
        if ts_sec is None or kc_id not in state.last_kc_ts_sec:
            return 1.0
        dt_days = max(0.0, (ts_sec - state.last_kc_ts_sec[kc_id]) / 86400.0)
        if dt_days <= 0.0:
            return 1.0
        lam = max(0.1, self.config.weibull_lambda_days)
        k = max(0.1, min(5.0, self.config.weibull_k))
        return math.exp(-((dt_days / lam) ** k))

    def _item_bias(self, question_id: Optional[Hashable], kc_id: Hashable) -> float:
        if question_id is not None and question_id in self.question_bias:
            return self.question_bias[question_id]
        return self.kc_bias.get(kc_id, 0.0)

    def predict(
        self,
        state: StudentMasteryState,
        kc_id: Hashable,
        *,
        question_id: Optional[Hashable] = None,
        ts_sec: Optional[float] = None,
    ) -> float:
        """Predict calibrated probability P(correct) ∈ (0, 1)."""
        cfg = self.config
        b_item = self._item_bias(question_id, kc_id)
        decay = self._weibull_decay(state, kc_id, ts_sec)
        nbs = self.kc_graph.get(kc_id, ())
        graph_delta = sum(w * state.theta_kc[nb] for nb, w in nbs if nb in state.theta_kc)
        z = (
            self.g_logit
            + b_item
            + cfg.w_global * state.theta_global
            + cfg.w_recent * state.theta_recent
            + cfg.w_kc * (state.theta_kc.get(kc_id, 0.0) * decay)
            + cfg.w_graph * graph_delta
            + cfg.w_log_wins * math.log1p(state.kc_wins.get(kc_id, 0.0))
            - cfg.w_log_fails * math.log1p(state.kc_fails.get(kc_id, 0.0))
        )
        return _sigmoid(z)

    def update(
        self,
        state: StudentMasteryState,
        kc_id: Hashable,
        is_correct: bool,
        *,
        question_id: Optional[Hashable] = None,
        ts_sec: Optional[float] = None,
        assistance: str = "independent",
        primary_step: bool = True,
    ) -> float:
        """Update online mastery state after an observation; returns pre-update prediction."""
        cfg = self.config
        y = 1.0 if is_correct else 0.0
        p_pred = self.predict(state, kc_id, question_id=question_id, ts_sec=ts_sec)
        weight = ASSISTANCE_WEIGHTS.get(assistance, 1.0)
        if weight <= 0.0:
            return p_pred

        decay = self._weibull_decay(state, kc_id, ts_sec)
        err = (y - p_pred) * weight

        if primary_step:
            state.theta_global = max(-4.0, min(4.0, state.theta_global + cfg.lr_global * err))
            momentum_signal = 1.2 if is_correct else -1.8
            state.theta_recent = (
                cfg.recent_decay * state.theta_recent + (1.0 - cfg.recent_decay) * momentum_signal * weight
            )
            state.theta_kc[kc_id] = max(
                -4.0, min(4.0, state.theta_kc.get(kc_id, 0.0) * decay + cfg.lr_kc * err)
            )
            # Propagate residual update along Memorix-Field knowledge graph
            for nb, w in self.kc_graph.get(kc_id, ()):
                state.theta_kc[nb] = max(-4.0, min(4.0, state.theta_kc.get(nb, 0.0) + cfg.lr_graph * w * err))
        else:
            state.theta_kc[kc_id] = max(
                -4.0, min(4.0, state.theta_kc.get(kc_id, 0.0) * decay + 0.5 * cfg.lr_kc * err)
            )

        if ts_sec is not None:
            state.last_kc_ts_sec[kc_id] = ts_sec
        if is_correct:
            state.kc_wins[kc_id] = state.kc_wins.get(kc_id, 0.0) + weight
        else:
            state.kc_fails[kc_id] = state.kc_fails.get(kc_id, 0.0) + weight
        return p_pred
