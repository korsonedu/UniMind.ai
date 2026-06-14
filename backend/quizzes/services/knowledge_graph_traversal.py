"""
Knowledge Graph Traversal — 沿 KnowledgeEdge 有向图找下游知识点。

用于 Phase 3 经验验证：给定一个 KP，沿着依赖边找到其下游 KP，
在学生做了下游题后触发反事实验证。

支持机构隔离：每个机构只能看到全局边 + 本机构私有边。
"""

import logging
from collections import defaultdict, deque
from typing import Optional

from django.core.cache import cache

logger = logging.getLogger(__name__)

# 缓存 key 前缀
DOWNSTREAM_CACHE_PREFIX = 'exp:downstream:'
DOWNSTREAM_CACHE_TTL = 3600  # 1 小时

# BFS 最大深度（防止无限遍历）
MAX_DEPTH = 5


def get_downstream_kps(
    kp_id: int,
    institution_id: Optional[int] = None,
    max_depth: int = MAX_DEPTH,
) -> list[dict]:
    """
    沿 KnowledgeEdge 有向图，从 kp_id 出发 BFS 找到所有下游 KP。

    Args:
        kp_id: 起始知识点 ID
        institution_id: 机构 ID（NULL 表示只看全局边）
        max_depth: BFS 最大深度

    Returns:
        list[dict]: 下游 KP 列表，每个元素：
            {
                'kp_id': int,
                'depth': int,          # 离起始 KP 的距离
                'path_weight': float,  # 路径累积权重（乘积）
                'edge_type': str,      # 入边的类型
            }
    """
    adj = _build_adjacency(institution_id)
    if kp_id not in adj:
        return []

    # BFS
    visited = {kp_id: (0, 1.0, '')}  # kp_id → (depth, path_weight, edge_type)
    queue = deque([kp_id])

    while queue:
        current = queue.popleft()
        depth = visited[current][0]
        if depth >= max_depth:
            continue

        for neighbor_id, weight, edge_type in adj.get(current, []):
            if neighbor_id in visited:
                continue
            new_weight = visited[current][1] * weight
            visited[neighbor_id] = (depth + 1, new_weight, edge_type)
            queue.append(neighbor_id)

    # 排除起始 KP 自身
    result = []
    for kp, (depth, path_weight, edge_type) in visited.items():
        if kp == kp_id:
            continue
        result.append({
            'kp_id': kp,
            'depth': depth,
            'path_weight': round(path_weight, 4),
            'edge_type': edge_type,
        })

    # 按深度→权重的优先级排序
    result.sort(key=lambda x: (x['depth'], -x['path_weight']))
    return result


def get_direct_downstream(kp_id: int, institution_id: Optional[int] = None) -> list[dict]:
    """
    只获取直接下游（距离=1）。
    用于触发验证：学生做完某 KP 的题后，看哪些 KP 是直接下游。
    """
    return [kp for kp in get_downstream_kps(kp_id, institution_id, max_depth=2)
            if kp['depth'] == 1]


def _build_adjacency(institution_id: Optional[int] = None) -> dict:
    """
    构建 KnowledgeEdge 邻接表，支持机构过滤。

    两层合并：
    1. 全局 KnowledgeEdge（institution__isnull=True）
    2. 机构私有 KnowledgeEdge（institution=institution_id）

    结果缓存在 Django cache，TTL 1 小时。

    Returns:
        dict: {kp_id: [(neighbor_kp_id, weight, edge_type), ...]}
    """
    from quizzes.models import KnowledgeEdge
    from django.db.models import Q

    cache_key = f'{DOWNSTREAM_CACHE_PREFIX}{institution_id or 0}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    adj = defaultdict(list)

    # 边过滤：全局边 + 机构私有边
    q = Q(is_active=True) & (Q(institution__isnull=True))
    if institution_id is not None:
        q |= Q(institution_id=institution_id)

    edges = KnowledgeEdge.objects.filter(q).only(
        'source_id', 'target_id', 'weight', 'edge_type'
    )

    for edge in edges:
        adj[edge.source_id].append((edge.target_id, float(edge.weight), edge.edge_type))

    # 转为普通 dict 并缓存
    result = dict(adj)
    cache.set(cache_key, result, DOWNSTREAM_CACHE_TTL)

    logger.debug(
        "_build_adjacency: institution=%s, %d nodes, %d edges",
        institution_id or 'global', len(result), edges.count(),
    )
    return result


def clear_downstream_cache(institution_id: Optional[int] = None):
    """清除下游缓存（KnowledgeEdge 变更时调用）。"""
    cache_key = f'{DOWNSTREAM_CACHE_PREFIX}{institution_id or 0}'
    cache.delete(cache_key)
