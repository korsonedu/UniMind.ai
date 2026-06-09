"""
知识图边同步服务。

职责：将 KnowledgePoint 树结构映射为 KnowledgeEdge 图边，
处理增量变更（增/删/移 KP）和全量重建。

核心操作：
    rebuild_subject_edges(subject)    — 全量重建（seed、migration、批量导入）
    sync_kp_neighborhood(kp)          — 增量同步（signal 驱动，实时响应单 KP 变更）

生成的边：
    父子 (contains, weight=0.8):  KP ↔ parent，双向
    兄弟 (similar, weight=0.3):  同 parent 下所有 KP 两两相连，双向
"""
from django.db import transaction
from quizzes.models import KnowledgePoint, KnowledgeEdge


def rebuild_subject_edges(subject: str, institution=None, dry_run: bool = False) -> dict:
    """
    全量重建：删掉 subject 下所有 source_type='tree' 的边，从树重新生成。

    用于：初始 seed、migration、批量导入、手动全量修复。
    幂等：多次调用结果一致。
    """
    kp_filter = {'subject': subject, 'level': 'kp'}
    if institution:
        kp_filter['institution'] = institution

    kp_ids = set(
        KnowledgePoint.objects.filter(**kp_filter)
        .values_list('id', flat=True)
    )

    edge_filter = {
        'source_type': 'tree',
        'source_id__in': kp_ids,
    }
    if institution:
        edge_filter['institution'] = institution

    old_count = KnowledgeEdge.objects.filter(**edge_filter).count()

    if not dry_run:
        KnowledgeEdge.objects.filter(**edge_filter).delete()

    # 收集父子关系
    parent_of = {}  # kp_id → parent_id
    children_of = {}  # parent_id → [child_id, ...]
    for kp in KnowledgePoint.objects.filter(**kp_filter).select_related('parent'):
        if kp.parent_id:
            parent_of[kp.id] = kp.parent_id
            children_of.setdefault(kp.parent_id, []).append(kp.id)

    edge_records = []

    # 父子边（双向，contains, 0.8）
    for child_id, parent_id in parent_of.items():
        edge_records.extend([
            KnowledgeEdge(
                source_id=child_id, target_id=parent_id,
                edge_type='contains', weight=0.8,
                source_type='tree', institution=institution,
            ),
            KnowledgeEdge(
                source_id=parent_id, target_id=child_id,
                edge_type='contains', weight=0.8,
                source_type='tree', institution=institution,
            ),
        ])

    # 兄弟边（双向，similar, 0.3）
    for siblings in children_of.values():
        for i in range(len(siblings)):
            for j in range(i + 1, len(siblings)):
                a, b = siblings[i], siblings[j]
                edge_records.extend([
                    KnowledgeEdge(
                        source_id=a, target_id=b,
                        edge_type='similar', weight=0.3,
                        source_type='tree', institution=institution,
                    ),
                    KnowledgeEdge(
                        source_id=b, target_id=a,
                        edge_type='similar', weight=0.3,
                        source_type='tree', institution=institution,
                    ),
                ])

    new_count = len(edge_records)

    if not dry_run and edge_records:
        # 用 get_or_create 逐条创建，避免 duplicate key
        created = 0
        skipped = 0
        for edge in edge_records:
            _, is_new = KnowledgeEdge.objects.get_or_create(
                source_id=edge.source_id,
                target_id=edge.target_id,
                edge_type=edge.edge_type,
                institution=institution,
                defaults={
                    'weight': edge.weight,
                    'source_type': edge.source_type,
                },
            )
            if is_new:
                created += 1
            else:
                skipped += 1

        return {
            'subject':            subject,
            'kp_count':           len(kp_ids),
            'old_tree_edges':     old_count,
            'new_edges_created':  created,
            'new_edges_skipped':  skipped,
            'parent_child_pairs': len(parent_of),
            'sibling_groups':     len(children_of),
        }

    return {
        'subject':            subject,
        'kp_count':           len(kp_ids),
        'old_tree_edges':     old_count,
        'would_create':       new_count,
        'parent_child_pairs': len(parent_of),
        'sibling_groups':     len(children_of),
        'dry_run':            True,
    }


def sync_kp_neighborhood(kp: KnowledgePoint, old_parent_id: int | None = None) -> dict:
    """
    增量同步：响应单个 KP 的创建或变更（改名除外）。

    1. 删除该 KP 当前所有 tree 边
    2. 与当前 parent 建立双向 contains 边（如有）
    3. 与当前所有兄弟建立双向 similar 边
    4. 如果 parent 变了，用旧 parent 的兄弟群也做一次清理

    对已经存在的边用 get_or_create，不重复。
    """
    result = {'kp_id': kp.id, 'action': 'synced'}

    # 1. 删旧边
    deleted, _ = KnowledgeEdge.objects.filter(
        source_type='tree',
        institution=kp.institution,
    ).filter(
        models.Q(source=kp) | models.Q(target=kp)
    ).delete()
    result['deleted'] = deleted

    # 2. 父子边
    created = 0
    if kp.parent_id:
        for src, tgt in [(kp.id, kp.parent_id), (kp.parent_id, kp.id)]:
            _, is_new = KnowledgeEdge.objects.get_or_create(
                source_id=src, target_id=tgt,
                edge_type='contains',
                institution=kp.institution,
                defaults={'weight': 0.8, 'source_type': 'tree'},
            )
            if is_new:
                created += 1

    # 3. 兄弟边（与同 parent 所有其他 KP）
    if kp.parent_id:
        siblings = KnowledgePoint.objects.filter(
            parent_id=kp.parent_id,
            level='kp',
            institution=kp.institution,
        ).exclude(id=kp.id)

        for sib in siblings:
            for src, tgt in [(kp.id, sib.id), (sib.id, kp.id)]:
                _, is_new = KnowledgeEdge.objects.get_or_create(
                    source_id=src, target_id=tgt,
                    edge_type='similar',
                    institution=kp.institution,
                    defaults={'weight': 0.3, 'source_type': 'tree'},
                )
                if is_new:
                    created += 1

    result['created'] = created

    # 4. Parent 变更：旧兄弟们少了这个 KP，需要清洗他们的边
    if old_parent_id and old_parent_id != kp.parent_id:
        old_siblings = KnowledgePoint.objects.filter(
            parent_id=old_parent_id,
            level='kp',
            institution=kp.institution,
        ).exclude(id=kp.id)

        for sib in old_siblings:
            # 删掉 sib ↔ kp 的 similar 边
            KnowledgeEdge.objects.filter(
                source_type='tree',
                edge_type='similar',
                institution=kp.institution,
            ).filter(
                models.Q(source=kp, target=sib) | models.Q(source=sib, target=kp)
            ).delete()

            # 重建 sib 之间的边（确保没有遗漏）
            _rebuild_sibling_edges_for(sib, parent_id=old_parent_id)

        result['old_siblings_cleaned'] = old_siblings.count()

    return result


def _rebuild_sibling_edges_for(kp: KnowledgePoint, parent_id: int):
    """重建某个 KP 与其所有兄弟的 similar 边（用于父节点变更后修复旧群组）"""
    siblings = KnowledgePoint.objects.filter(
        parent_id=parent_id,
        level='kp',
        institution=kp.institution,
    ).exclude(id=kp.id)

    for sib in siblings:
        for src, tgt in [(kp.id, sib.id), (sib.id, kp.id)]:
            KnowledgeEdge.objects.get_or_create(
                source_id=src, target_id=tgt,
                edge_type='similar',
                institution=kp.institution,
                defaults={'weight': 0.3, 'source_type': 'tree'},
            )


# Django models import for filter expressions
from django.db import models
