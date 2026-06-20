"""
Field: Knowledge Graph Diagnostic Engine — Production Service

Generative model:
  y_k ~ Bernoulli(sigmoid(α(μ_i - d_i)))  for question on KP_i
  μ ~ N(μ_0, (λL + τI)⁻¹)                 GMRF graph prior

Input:  partial exam observations on a few KPs
Output: mastery estimates μ_i for all KPs + posterior uncertainty

Graph is built from KnowledgeEdge + KnowledgePoint tree structure.
Difficulty is estimated from ItemParameter (IRT b-values).
Observations come from GradingRecord.
"""
import logging
import math
import numpy as np
from collections import defaultdict
from typing import Optional

from django.core.cache import cache
from scipy.sparse import csr_matrix, diags, eye
from scipy.optimize import minimize

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Graph Cache
# ──────────────────────────────────────────────

GRAPH_CACHE_PREFIX = 'field_graph_v2_'  # v2: fixed tree structure edge construction
GRAPH_CACHE_TIMEOUT = 3600 * 24  # 24 hours


def _get_graph_key(subject: str, institution_id: Optional[int]) -> str:
    inst = institution_id or 'global'
    return f'{GRAPH_CACHE_PREFIX}{subject}_{inst}'


# ──────────────────────────────────────────────
# Graph Construction
# ──────────────────────────────────────────────

def build_graph_from_db(subject: str, institution_id: Optional[int] = None):
    """
    Build normalized Laplacian and KP index from KnowledgeEdge + KnowledgePoint.

    Returns dict:
      {
        'kp_ids': [id1, id2, ...],         # ordered list of KP primary keys
        'kp_index': {kp_id: matrix_index},   # KP pk → 0-based matrix index
        'L_dense': np.ndarray,               # normalized Laplacian (dense, for optimization)
        'A_sparse': csr_matrix,              # adjacency (for LabelProp baseline)
        'n': int,                            # number of KPs
      }
    """
    from quizzes.models import KnowledgePoint, KnowledgeEdge

    # 1. Get all KP-level nodes for this subject
    kps = KnowledgePoint.objects.filter(
        level='kp',
        subject=subject,
    ).select_related('parent').order_by('id')

    if institution_id is not None:
        kps = kps.filter(institution_id=institution_id)

    kp_ids = [kp.id for kp in kps]
    kp_index = {kp_id: i for i, kp_id in enumerate(kp_ids)}
    n = len(kp_ids)

    if n == 0:
        return None

    # 2. Build adjacency from tree structure (parent-child & sibling)
    #    Use parent_id as grouping key — parent may be a section/chapter, not a KP.
    #    This works for ALL subjects regardless of whether KnowledgeEdge records exist.
    adj = defaultdict(list)  # kp_id → [(other_kp_id, weight)]

    # Sibling edges: KPs sharing the same parent section
    siblings = defaultdict(list)
    for kp in kps:
        if kp.parent_id:
            siblings[kp.parent_id].append(kp.id)
    for sib_list in siblings.values():
        for i in range(len(sib_list)):
            for j in range(i + 1, len(sib_list)):
                adj[sib_list[i]].append((sib_list[j], 0.3))
                adj[sib_list[j]].append((sib_list[i], 0.3))

    # Parent-child: if parent is also a KP-level node (rare but handle it)
    for kp in kps:
        parent = kp.parent
        if parent and parent.id in kp_index and parent.level == 'kp':
            adj[kp.id].append((parent.id, 0.8))
            adj[parent.id].append((kp.id, 0.8))

    # 3. KnowledgeEdge edges (prerequisite, similar, co_occur, etc.)
    #    Exclude 'contains' (tree structure) and 'confusion' (negative correlation)
    edge_types_include = {'prerequisite', 'similar', 'co_occur', 'derivation', 'contrast'}
    edges = KnowledgeEdge.objects.filter(
        source_id__in=kp_ids,
        target_id__in=kp_ids,
        edge_type__in=edge_types_include,
        is_active=True,
    )
    if institution_id is not None:
        edges = edges.filter(institution_id=institution_id)

    for edge in edges:
        if edge.source_id in kp_index and edge.target_id in kp_index:
            w = float(edge.weight)
            adj[edge.source_id].append((edge.target_id, w))
            adj[edge.target_id].append((edge.source_id, w))  # symmetrize

    # 4. Build sparse adjacency matrix
    row, col, data = [], [], []
    for src, neighbors in adj.items():
        if src in kp_index:
            si = kp_index[src]
            for tgt, w in neighbors:
                if tgt in kp_index:
                    row.append(si)
                    col.append(kp_index[tgt])
                    data.append(w)

    A = csr_matrix((data, (row, col)), shape=(n, n))

    # 5. Normalized Laplacian: L = I - D^{-1/2} A D^{-1/2}
    deg = np.array(A.sum(axis=1)).flatten()
    deg[deg < 1e-8] = 1.0
    D_inv_sqrt = diags(1.0 / np.sqrt(deg), 0)
    L = eye(n, format='csr') - D_inv_sqrt.dot(A).dot(D_inv_sqrt)

    return {
        'kp_ids': kp_ids,
        'kp_index': kp_index,
        'L_dense': L.toarray(),
        'A_sparse': A,
        'n': n,
    }


def get_or_build_graph(subject: str, institution_id: Optional[int] = None):
    """Get cached graph or build from DB."""
    from django.core.cache import cache
    cache_key = _get_graph_key(subject, institution_id)
    graph = cache.get(cache_key)
    if graph is None:
        graph = build_graph_from_db(subject, institution_id)
        if graph is not None:
            cache.set(cache_key, graph, GRAPH_CACHE_TIMEOUT)
    return graph


# ──────────────────────────────────────────────
# Difficulty Estimation
# ──────────────────────────────────────────────

def estimate_kp_difficulties(kp_ids: list, institution_id: Optional[int] = None):
    """
    Estimate per-KP difficulty from ItemParameter (IRT b-value).

    For each KP, average the difficulty (b) of questions linked to it.
    Falls back to 0.3 (moderate) if no data.
    """
    from django.db.models import Avg
    from quizzes.models import ItemParameter, Question

    difficulties = np.full(len(kp_ids), 0.3)

    # Get questions linked to these KPs, then their IRT params
    params = (
        ItemParameter.objects
        .filter(question__knowledge_point_id__in=kp_ids)
        .values('question__knowledge_point_id')
        .annotate(avg_b=Avg('difficulty'))
    )

    kp_index = {kp_id: i for i, kp_id in enumerate(kp_ids)}
    for row in params:
        kp_id = row['question__knowledge_point_id']
        if kp_id in kp_index and row['avg_b'] is not None:
            # IRT b is on logit scale; map to [0, 1] via sigmoid
            # For Field we need difficulty on the K scale,
            # b ≈ 0 means medium difficulty, b > 0 means hard
            # We clip to [0.05, 0.95]
            b_val = row['avg_b']
            # Map: b ∈ [-3, 3] → difficulty ∈ [0.05, 0.95]
            d = 1.0 / (1.0 + math.exp(-b_val))
            difficulties[kp_index[kp_id]] = float(np.clip(d, 0.05, 0.95))

    return difficulties


# ──────────────────────────────────────────────
# Observations from GradingRecord
# ──────────────────────────────────────────────

def get_user_observations(user, subject: str, days: int = 90):
    """
    Fetch recent exam/quiz results for a user, grouped by KP.

    Returns:
      obs_by_kp: {kp_id: [0/1, 0/1, ...]}   # list of correct/incorrect
      kp_ids_observed: [kp_id, ...]           # KPs with at least one observation
    """
    from django.utils import timezone
    from datetime import timedelta
    from quizzes.models import GradingRecord

    since = timezone.now() - timedelta(days=days)

    records = (
        GradingRecord.objects
        .filter(
            user=user,
            graded_at__gte=since,
            question__knowledge_point__subject=subject,
            question__knowledge_point__isnull=False,
        )
        .select_related('question__knowledge_point')
        .values('question__knowledge_point_id', 'is_correct')
    )

    obs_by_kp = defaultdict(list)
    for r in records:
        kp_id = r['question__knowledge_point_id']
        obs_by_kp[kp_id].append(1 if r['is_correct'] else 0)

    return dict(obs_by_kp)


# ──────────────────────────────────────────────
# Bernoulli-GMRF MAP Estimation
# ──────────────────────────────────────────────

def run_field_diagnosis(
    graph: dict,
    difficulties: np.ndarray,
    obs_by_kp: dict,
    lam: float = 0.5,
    prior_mean: float = 0.5,
    prior_prec: float = 0.5,
    alpha: float = 5.0,
):
    """
    Run Bernoulli-GMRF MAP estimation.

    Args:
      graph: from build_graph_from_db()
      difficulties: per-KP difficulty array (shape: [n])
      obs_by_kp: {kp_id: [0/1, ...]}  — observations
      lam: graph smoothness weight
      prior_mean: default K value when no information
      prior_prec: strength of prior toward prior_mean
      alpha: IRT discrimination parameter

    Returns:
      mu: np.ndarray [n] — mastery estimates for all KPs
      metadata: dict with convergence info
    """
    n = graph['n']
    kp_index = graph['kp_index']
    L = graph['L_dense']

    # Flatten observations into (idx, y) lists
    obs_idx = []
    obs_y = []
    for kp_id, outcomes in obs_by_kp.items():
        if kp_id in kp_index:
            idx = kp_index[kp_id]
            for y in outcomes:
                obs_idx.append(idx)
                obs_y.append(y)

    n_obs = len(obs_idx)
    if n_obs == 0:
        return np.full(n, prior_mean), {'n_obs': 0, 'converged': False}

    # ── L-BFGS-B optimization ──
    mu0 = np.full(n, prior_mean)
    mu0_vec = np.full(n, prior_mean)
    bounds = [(0.001, 0.999) for _ in range(n)]

    def obj_grad(mu):
        nlp = 0.0
        g = np.zeros(n)
        for k in range(n_obs):
            i = obs_idx[k]
            d = difficulties[i]
            x = alpha * (mu[i] - d)
            if x > 30:
                p = 1.0
            elif x < -30:
                p = 0.0
            else:
                p = 1.0 / (1.0 + math.exp(-x))
            p = max(1e-12, min(1 - 1e-12, p))
            y = obs_y[k]
            nlp -= y * math.log(p) + (1 - y) * math.log(1 - p)
            g[i] -= alpha * (y - p)
        diff = mu - mu0_vec
        nlp += 0.5 * lam * mu.dot(L.dot(mu)) + 0.5 * prior_prec * diff.dot(diff)
        g += lam * L.dot(mu) + prior_prec * diff
        return nlp, g

    try:
        result = minimize(
            lambda x: obj_grad(x)[0], mu0,
            method='L-BFGS-B',
            jac=lambda x: obj_grad(x)[1],
            bounds=bounds,
            options={'maxiter': 50, 'ftol': 1e-5},
        )
        converged = result.success
        mu = result.x
        if not converged or np.any(np.isnan(mu)) or np.any(np.isinf(mu)):
            mu = mu0
            converged = False
        if np.max(mu) > 2 or np.min(mu) < -1:
            mu = mu0
            converged = False
    except Exception:
        mu = mu0
        converged = False

    return mu, {
        'n_obs': n_obs,
        'n_kps': n,
        'converged': bool(converged),
    }


# ──────────────────────────────────────────────
# High-Level API
# ──────────────────────────────────────────────

def diagnose_user(
    user,
    subject: str,
    institution_id: Optional[int] = None,
    observations: Optional[dict] = None,
    lam: float = 0.5,
    days: int = 90,
):
    """
    Main entry point: run Field diagnosis for a user on a subject.

    Args:
      user: Django User instance
      subject: e.g. '金融431', '高中数学'
      institution_id: optional institution filter
      observations: optional {kp_id: [0/1, ...]} — if None, auto-fetch from GradingRecord
      lam: graph smoothness (0 = no graph, 0.5 = moderate, >2 = strong)
      days: lookback for observations

    Returns:
      {
        'subject': str,
        'kp_ids': [...],           # ordered KP primary keys
        'kp_names': [...],         # ordered KP names
        'mastery': [...],          # μ_i estimates [0, 1]
        'n_observations': int,     # total observations used
        'converged': bool,         # optimization converged?
      }
    """
    from quizzes.models import KnowledgePoint

    # 1. Get/build graph
    graph = get_or_build_graph(subject, institution_id)
    if graph is None:
        return {'error': f'No knowledge points found for subject={subject}'}

    # 2. Get difficulties
    difficulties = estimate_kp_difficulties(graph['kp_ids'], institution_id)

    # 3. Get observations
    if observations is None:
        obs_by_kp = get_user_observations(user, subject, days=days)
    else:
        obs_by_kp = observations

    # 4. Run diagnosis
    mu, meta = run_field_diagnosis(
        graph, difficulties, obs_by_kp,
        lam=lam,
        prior_mean=0.5,
        prior_prec=0.5,
        alpha=5.0,
    )

    # 5. Map back to KP names
    kp_names = []
    kp_map = dict(KnowledgePoint.objects.filter(
        id__in=graph['kp_ids']
    ).values_list('id', 'name'))

    kp_names = [kp_map.get(kp_id, f'KP-{kp_id}') for kp_id in graph['kp_ids']]

    return {
        'subject': subject,
        'kp_ids': graph['kp_ids'],
        'kp_names': kp_names,
        'mastery': mu.tolist(),
        'n_observations': meta['n_obs'],
        'converged': meta['converged'],
    }


def invalidate_graph_cache(subject: str, institution_id: Optional[int] = None):
    """Call this when KnowledgeEdge or KnowledgePoint tree changes."""
    from django.core.cache import cache
    cache_key = _get_graph_key(subject, institution_id)
    cache.delete(cache_key)
    logger.info(f'Field graph cache invalidated: {cache_key}')
