import datetime
import random
from typing import Dict, List, Optional

from django.conf import settings
from django.db.models import Q, Sum
from django.utils import timezone

from quizzes.models import Question, UserQuestionStatus
from quizzes.utils import safe_int as _safe_int


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(value, upper))


def _bucket_targets(limit: int, preference: str = "balanced") -> Dict[str, int]:
    if preference == "new_first":
        due_ratio, risk_ratio, new_ratio = 0.20, 0.20, 0.60
    elif preference == "review_first":
        due_ratio, risk_ratio, new_ratio = 0.55, 0.35, 0.10
    else:  # balanced
        due_ratio, risk_ratio, new_ratio = 0.50, 0.30, 0.20

    due_target = max(1, round(limit * due_ratio))
    risk_target = max(1, round(limit * risk_ratio)) if limit > 1 else 0
    new_target = max(0, limit - due_target - risk_target)

    if due_target + risk_target + new_target > limit:
        overflow = due_target + risk_target + new_target - limit
        new_target = max(0, new_target - overflow)

    return {
        "due": due_target,
        "risk": risk_target,
        "new": new_target,
    }


def _select_ids(candidate_ids: List[int], target_count: int, selected_set: set, selected: List[int]) -> int:
    picked = 0
    for qid in candidate_ids:
        if picked >= target_count:
            break
        if qid in selected_set:
            continue
        selected.append(qid)
        selected_set.add(qid)
        picked += 1
    return picked


def build_adaptive_question_ids(
    user,
    limit: int = 10,
    base_queryset=None,
    preference: str = "balanced",
    now=None,
) -> Dict[str, object]:
    """
    preference: "balanced" | "new_first" | "review_first"
    """
    now = now or timezone.now()
    limit = _clamp(_safe_int(limit, 10), 1, 50)

    if base_queryset is None:
        base_queryset = Question.objects.all()

    candidate_subquery = base_queryset.values("id")

    status_qs = UserQuestionStatus.objects.filter(user=user, question_id__in=candidate_subquery)
    active_status_qs = status_qs.filter(is_mastered=False)

    mastered_ids_qs = status_qs.filter(is_mastered=True).values_list("question_id", flat=True)

    due_ids = list(
        active_status_qs.filter(next_review_at__lte=now)
        .order_by("next_review_at", "stability", "-wrong_count")
        .values_list("question_id", flat=True)
    )

    at_risk_window = now + datetime.timedelta(days=3)
    at_risk_ids = list(
        active_status_qs.filter(next_review_at__lte=at_risk_window)
        .exclude(question_id__in=due_ids)
        .filter(Q(wrong_count__gte=1) | Q(stability__lt=7) | Q(last_correct=False))
        .order_by("-wrong_count", "stability", "next_review_at")
        .values_list("question_id", flat=True)
    )

    reinforce_ids = list(
        active_status_qs.filter(wrong_count__gt=0)
        .exclude(question_id__in=due_ids)
        .exclude(question_id__in=at_risk_ids)
        .order_by("-wrong_count", "next_review_at")
        .values_list("question_id", flat=True)
    )

    attempted_ids_qs = status_qs.values_list("question_id", flat=True)

    new_pool_ids = list(
        base_queryset.exclude(id__in=attempted_ids_qs)
        .exclude(id__in=mastered_ids_qs)
        .values_list("id", flat=True)[: max(limit * 4, 40)]
    )
    random.shuffle(new_pool_ids)

    targets = _bucket_targets(limit, preference)

    selected: List[int] = []
    selected_set = set()

    picked_due = _select_ids(due_ids, targets["due"], selected_set, selected)
    picked_risk = _select_ids(at_risk_ids, targets["risk"], selected_set, selected)
    picked_new = _select_ids(new_pool_ids, targets["new"], selected_set, selected)

    picked_reinforce = 0
    if len(selected) < limit:
        picked_reinforce = _select_ids(reinforce_ids, limit - len(selected), selected_set, selected)

    if len(selected) < limit:
        future_ids = set(
            active_status_qs.filter(next_review_at__gt=now)
            .values_list("question_id", flat=True)
        )
        fallback_ids = list(
            base_queryset.exclude(id__in=mastered_ids_qs)
            .exclude(id__in=selected)
            .exclude(id__in=future_ids)
            .order_by("?")
            .values_list("id", flat=True)[: limit * 2]
        )
        _select_ids(fallback_ids, limit - len(selected), selected_set, selected)

    if len(selected) < limit:
        last_resort = list(
            base_queryset.exclude(id__in=mastered_ids_qs)
            .exclude(id__in=selected)
            .order_by("?")
            .values_list("id", flat=True)[: limit * 2]
        )
        _select_ids(last_resort, limit - len(selected), selected_set, selected)

    # 文本去重：同一text的题目只保留第一道，其余替换为备选题
    if len(selected) > 1:
        texts = dict(Question.objects.filter(id__in=selected).values_list("id", "text"))
        deduped = []
        seen = set()
        removed_count = 0
        for qid in selected:
            t = texts.get(qid)
            if t is None:
                continue
            if t in seen:
                removed_count += 1
                continue
            seen.add(t)
            deduped.append(qid)

        if removed_count:
            selected = deduped
            selected_set = set(selected)
            if len(selected) < limit:
                remaining = list(
                    base_queryset.exclude(id__in=selected_set)
                    .exclude(id__in=mastered_ids_qs)
                    .order_by("?")
                    .values_list("id", flat=True)[: removed_count * 2]
                )
                _select_ids(remaining, removed_count, selected_set, selected)

    # ── Memorix-Field: 图扩散重排 ──
    if getattr(settings, 'MEMORIX_FIELD_ENABLED', False):
        alpha = getattr(settings, 'MEMORIX_FIELD_ALPHA', 0.60)
        selected = _field_rerank(selected, user, now, alpha)

    return {
        "question_ids": selected,
        "meta": {
            "requested_limit": limit,
            "actual_count": len(selected),
            "preference": preference,
            "targets": targets,
            "picked": {
                "due": picked_due,
                "risk": picked_risk,
                "new": picked_new,
                "reinforce": picked_reinforce,
            },
            "pool": {
                "due": len(due_ids),
                "risk": len(at_risk_ids),
                "new": len(new_pool_ids),
                "reinforce": len(reinforce_ids),
            },
        },
    }


def get_memorix_session_plan(user, minutes: int = 25, preferred_limit: Optional[int] = None) -> Dict[str, object]:
    now = timezone.now()
    minutes = _clamp(_safe_int(minutes, 25), 10, 120)

    status_qs = UserQuestionStatus.objects.filter(user=user)
    active_qs = status_qs.filter(is_mastered=False)

    due_count = active_qs.filter(next_review_at__lte=now).count()
    at_risk_count = active_qs.filter(
        stability__lt=7,
        next_review_at__lte=now + datetime.timedelta(days=3),
    ).count()
    weak_focus_count = active_qs.filter(Q(wrong_count__gte=2) | Q(last_correct=False)).count()

    attempted_ids = status_qs.values_list("question_id", flat=True)
    new_qs = Question.objects.exclude(id__in=attempted_ids)
    inst = getattr(user, 'institution', None)
    if inst:
        from django.db.models import Q
        new_qs = new_qs.filter(institution=inst)
    new_questions_count = new_qs.count()

    if preferred_limit is not None:
        recommended_questions = _clamp(_safe_int(preferred_limit, 10), 1, 50)
    else:
        minutes_per_q = getattr(settings, 'STUDY_MINUTES_PER_QUESTION', 2.8)
        base = _clamp(round(minutes / float(minutes_per_q)), 5, 40)
        recommended_questions = min(50, max(base, min(30, due_count)))

    targets = _bucket_targets(recommended_questions)

    top_weak_kps = list(
        active_qs.filter(wrong_count__gt=0, question__knowledge_point__isnull=False)
        .values("question__knowledge_point_id", "question__knowledge_point__name")
        .annotate(total_wrong=Sum("wrong_count"))
        .order_by("-total_wrong")[:3]
    )

    return {
        "minutes": minutes,
        "recommended_questions": recommended_questions,
        "estimated_minutes": int(round(recommended_questions * 2.8)),
        "review_goal": due_count,
        "at_risk_count": at_risk_count,
        "weak_focus_count": weak_focus_count,
        "new_questions": new_questions_count,
        "targets": targets,
        "top_weak_knowledge_points": [
            {
                "id": row["question__knowledge_point_id"],
                "name": row["question__knowledge_point__name"],
                "wrong_count": int(row["total_wrong"] or 0),
            }
            for row in top_weak_kps
        ],
    }


# ═══════════════════════════════════════════
# Memorix-Field: Graph Diffusion Scheduling
# ═══════════════════════════════════════════

MEMORIX_ADJ_CACHE_KEY = "memorix:adj"
MEMORIX_ADJ_CACHE_TTL = 3600  # 1 hour
MEMORIX_DYNAMIC_EDGE_PREFIX = "memorix:edge"  # Redis hash: memorix:edge:{source}:{target}


def invalidate_adjacency_cache():
    """KnowledgeEdge 变更时调用，清除邻接表缓存。"""
    from django.core.cache import cache
    cache.delete(MEMORIX_ADJ_CACHE_KEY)


def _build_adjacency_from_edges():
    """
    构建邻接表 {kp_id: [(neighbor_kp_id, weight)]}。
    
    两层合并：
    1. KnowledgeEdge 表（固定边：树结构、LLM 生成、手工标注）
    2. Redis 动态边缓存（ReviewLog 学出来的 co_occur/confusion）
    
    结果缓存在 Django cache（Redis），TTL 1 小时。
    """
    from django.core.cache import cache
    from collections import defaultdict

    cached = cache.get(MEMORIX_ADJ_CACHE_KEY)
    if cached is not None:
        # cache 存的是 list-of-tuples，转回 defaultdict
        adj = defaultdict(list)
        for kp_id, neighbors in cached:
            adj[kp_id] = neighbors
        return adj

    # ── 层 1：DB 固定边 ──
    from quizzes.models import KnowledgeEdge
    adj = defaultdict(list)
    for edge in KnowledgeEdge.objects.filter(is_active=True).only(
        'source_id', 'target_id', 'weight'
    ):
        adj[edge.source_id].append((edge.target_id, float(edge.weight)))

    # ── 层 2：Redis 动态边 ──
    try:
        from django_redis import get_redis_connection
        redis_conn = get_redis_connection("default")
        # 扫描所有 memorix:edge:* 键
        cursor = 0
        dynamic_count = 0
        while True:
            cursor, keys = redis_conn.scan(
                cursor, match=f"{MEMORIX_DYNAMIC_EDGE_PREFIX}:*", count=100
            )
            for key in keys:
                # key 格式: memorix:edge:123:456
                data = redis_conn.hgetall(key)
                if not data:
                    continue
                try:
                    source_id = int(data.get(b'source_id', 0))
                    target_id = int(data.get(b'target_id', 0))
                    weight = float(data.get(b'weight', 0))
                except (ValueError, TypeError):
                    continue
                if weight <= 0:
                    continue
                adj[source_id].append((target_id, weight))
                dynamic_count += 1
            if cursor == 0:
                break
    except Exception:
        # Redis 不可用时静默降级，只用 DB 固定边
        pass

    # ── 缓存结果 ──
    # 转为可 pickle 的 list-of-tuples 结构
    cache_payload = [(kp_id, list(neighbors)) for kp_id, neighbors in adj.items()]
    cache.set(MEMORIX_ADJ_CACHE_KEY, cache_payload, MEMORIX_ADJ_CACHE_TTL)

    return adj


def _field_rerank(question_ids, user, now, alpha):
    """
    对候选题目列表进行图扩散重排。
    
    公式: score_i = α × urgency_i + (1-α) × field_benefit_i
    field_benefit_i = Σ_j w_ij × max(0, 1 - R_j(t))
    
    urgency 计算取决于 MEMORIX_REC_ENABLED：
      - 关闭：urgency_i = 1 - R_i(t)                     （标准 Weibull）
      - 打开：urgency_i = P_i(t_elapsed) / P_i(t_opt)    （再巩固窗口）
    
    返回重新排序后的 question_id 列表。
    """
    from quizzes.models import UserQuestionStatus, Question
    from quizzes.memorix.service import predict_retrievability

    rec_enabled = getattr(settings, 'MEMORIX_REC_ENABLED', False)
    rec_tau = getattr(settings, 'MEMORIX_REC_TAU', 0.042)  # 默认 1 小时（天）
    rec_k = getattr(settings, 'MEMORIX_REC_K', 1.2)

    adj = _build_adjacency_from_edges()
    if not adj:
        return question_ids

    q_to_kp = dict(Question.objects.filter(
        id__in=question_ids
    ).values_list('id', 'knowledge_point_id'))

    kp_ids = set(q_to_kp.values())
    statuses = UserQuestionStatus.objects.filter(
        user=user,
        question__knowledge_point_id__in=kp_ids,
    ).select_related('question')

    # kp_id → {'R': float, 'stability': float, 'elapsed': float}
    kp_state = {}
    for st in statuses:
        kp_id = st.question.knowledge_point_id
        elapsed = (now - st.last_review).total_seconds() / 86400 if st.last_review else 999
        R = predict_retrievability(st.stability, elapsed, user_id=user.id)
        kp_state[kp_id] = {
            'R': R,
            'stability': st.stability,
            'elapsed': elapsed,
        }

    # 计算每个题目的 score
    scored = []
    for qid in question_ids:
        kp_id = q_to_kp.get(qid)
        state = kp_state.get(kp_id, {})
        R_self = state.get('R', 0.0)

        # urgency
        if rec_enabled and kp_id and kp_id in kp_state:
            from quizzes.memorix.reconsolidation import compute_urgency
            urgency = compute_urgency(
                state['stability'],
                state['elapsed'],
                k=rec_k,
                tau=rec_tau,
            )
        else:
            urgency = 1.0 - R_self

        # field_benefit: 对每个邻居 j，贡献 = w_ij × (1 - R_j)
        # 注意：field_benefit 始终用标准 (1-R_j)，不受 REC 影响
        fb = 0.0
        if kp_id and kp_id in adj:
            for neighbor_kp, w in adj[kp_id]:
                nbr_state = kp_state.get(neighbor_kp, {})
                R_neighbor = nbr_state.get('R', 0.0)
                fb += w * max(0.0, 1.0 - R_neighbor)

        score = alpha * urgency + (1 - alpha) * fb
        scored.append((qid, score))

    scored.sort(key=lambda x: -x[1])
    return [qid for qid, _ in scored]
