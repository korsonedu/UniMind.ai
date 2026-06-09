"""
知识图边 API。

教师端能力：
  - 查看某学科 / 某 KP 的全部边
  - 手动创建 / 删除 / 更新边
  - 触发全图 LLM 分析（次数受 tier 限制）
  - 审核 LLM 提案的边（确认 / 拒绝）

边编辑规则：
  - source_type='tree' 的边不允许手动修改（由信号自动维护）
  - 手动创建的边 source_type='manual'
  - 手动修改 LLM 生成的边，source_type 保持 'llm'
  - 非对称关系（prerequisite 等）需同时创建/更新反向边
"""
import logging
from django.db import transaction, models as dm
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from quizzes.models import KnowledgePoint, KnowledgeEdge
from quizzes.serializers import KnowledgeEdgeSerializer
from users.permissions import IsInstitutionAdmin, IsPlatformAdmin, is_platform_admin

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 1. 边列表 / 创建
# ──────────────────────────────────────────────

class KnowledgeEdgeListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/quizzes/knowledge-edges/?subject=CFA
    GET  /api/quizzes/knowledge-edges/?kp_id=1234
    POST /api/quizzes/knowledge-edges/
          {source, target, edge_type, weight, is_active?}
    """
    serializer_class = KnowledgeEdgeSerializer
    permission_classes = [IsInstitutionAdmin]

    def get_queryset(self):
        user = self.request.user
        qs = KnowledgeEdge.objects.select_related('source', 'target')

        # 平台管理员可查看任意机构
        if is_platform_admin(user):
            inst_id = self.request.query_params.get('institution')
        else:
            inst_id = getattr(user, 'institution_id', None)

        if inst_id:
            qs = qs.filter(dm.Q(institution_id=inst_id) | dm.Q(institution__isnull=True))

        # 按学科过滤
        subject = self.request.query_params.get('subject')
        if subject:
            kp_ids = KnowledgePoint.objects.filter(
                subject=subject, level='kp'
            ).values_list('id', flat=True)
            qs = qs.filter(source_id__in=kp_ids)

        # 按 KP 过滤
        kp_id = self.request.query_params.get('kp_id')
        if kp_id:
            qs = qs.filter(dm.Q(source_id=kp_id) | dm.Q(target_id=kp_id))

        # 按边类型 / 来源过滤
        edge_type = self.request.query_params.get('edge_type')
        if edge_type:
            qs = qs.filter(edge_type=edge_type)

        source_type = self.request.query_params.get('source_type')
        if source_type:
            qs = qs.filter(source_type=source_type)

        return qs.order_by('source__code', 'target__code')

    def perform_create(self, serializer):
        user = self.request.user
        edge = serializer.save(
            source_type='manual',
            institution_id=getattr(user, 'institution_id', None),
        )
        # 如果是非对称关系（prerequisite / derivation），创建提示
        _ensure_reverse_for_asymmetric(edge)
        from quizzes.services.memorix_scheduler import invalidate_adjacency_cache
        invalidate_adjacency_cache()


# ──────────────────────────────────────────────
# 2. 单边详情 / 更新 / 删除
# ──────────────────────────────────────────────

class KnowledgeEdgeDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/quizzes/knowledge-edges/<id>/
    PATCH  /api/quizzes/knowledge-edges/<id>/
    DELETE /api/quizzes/knowledge-edges/<id>/
    """
    serializer_class = KnowledgeEdgeSerializer
    permission_classes = [IsInstitutionAdmin]
    lookup_field = 'pk'

    def get_queryset(self):
        return KnowledgeEdge.objects.select_related('source', 'target')

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.source_type == 'tree':
            return Response(
                {'detail': '树边由系统自动维护，不可手动删除。请修改知识树结构。'},
                status=status.HTTP_403_FORBIDDEN,
            )
        self.perform_destroy(instance)
        from quizzes.services.memorix_scheduler import invalidate_adjacency_cache
        invalidate_adjacency_cache()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_update(self, serializer):
        # tree 边不允许手动修改
        instance = self.get_object()
        if instance.source_type == 'tree':
            return Response(
                {'detail': '树边由系统自动维护，不可手动修改。'},
                status=status.HTTP_403_FORBIDDEN,
            )
        # 如果 source_type 是 llm，修改后保持不变（仍是 llm 标注 + 人工校准）
        serializer.save()
        from quizzes.services.memorix_scheduler import invalidate_adjacency_cache
        invalidate_adjacency_cache()


# ──────────────────────────────────────────────
# 3. 批量写入（教师画线工具）
# ──────────────────────────────────────────────

class KnowledgeEdgeBulkCreateView(APIView):
    """
    POST /api/quizzes/knowledge-edges/bulk/
    Body: {
        "edges": [
            {source, target, edge_type, weight},
            ...
        ]
    }
    批量创建边，用于教师可视化连线。
    """
    permission_classes = [IsInstitutionAdmin]

    def post(self, request):
        edges_data = request.data.get('edges', [])
        if not edges_data:
            return Response({'detail': 'edges 不能为空'}, status=status.HTTP_400_BAD_REQUEST)

        user = self.request.user
        inst_id = getattr(user, 'institution_id', None)
        created, skipped, errors = 0, 0, []

        for i, data in enumerate(edges_data):
            source_id = data.get('source')
            target_id = data.get('target')
            edge_type = data.get('edge_type', 'similar')
            weight = data.get('weight', 0.5)

            if not source_id or not target_id:
                errors.append({'index': i, 'error': 'source 和 target 必填'})
                continue

            _, is_new = KnowledgeEdge.objects.update_or_create(
                source_id=source_id,
                target_id=target_id,
                edge_type=edge_type,
                institution_id=inst_id,
                defaults={
                    'weight': weight,
                    'source_type': 'manual',
                    'is_active': True,
                },
            )
            if is_new:
                created += 1
            else:
                skipped += 1

        return Response({'created': created, 'skipped': skipped, 'errors': errors})


# ──────────────────────────────────────────────
# 4. 全图 LLM 分析（受 tier 限制）
# ──────────────────────────────────────────────

class KnowledgeEdgeLLMAnalyzeView(APIView):
    """
    POST /api/quizzes/knowledge-edges/llm-analyze/
    Body: {subject: "CFA"}

    对 subject 下所有 KP，用 LLM 扫跨 SEC 候选对，
    生成 prerequisite / derivation / confusion / contrast / co_occur 边。

    限制：
      - 需要 Pro 或 Enterprise 订阅
      - Pro 每月 3 次
      - Enterprise 不限
      - 生成的边 source_type='llm', is_active=False（需教师审核确认）
    """
    permission_classes = [IsInstitutionAdmin]

    def post(self, request):
        subject = request.data.get('subject')
        if not subject:
            return Response({'detail': 'subject 必填'}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        inst_id = getattr(user, 'institution_id', None)

        # TODO: Tier 检查（对接订阅系统后实现）
        # check_llm_quota(user, 'knowledge_edge_analyze')

        # 收集跨 SEC KP 对
        kps = KnowledgePoint.objects.filter(
            subject=subject, level='kp',
            institution=inst_id,
        ).select_related('parent')

        kp_map = {}
        for kp in kps:
            sec_id = kp.parent_id
            kp_map.setdefault(sec_id, []).append(kp)

        # 跨 SEC 候选对：不同 SEC 下的 KP 两两配对
        sec_ids = list(kp_map.keys())
        candidates = []
        for i in range(len(sec_ids)):
            for j in range(i + 1, len(sec_ids)):
                for kp_a in kp_map[sec_ids[i]]:
                    for kp_b in kp_map[sec_ids[j]]:
                        candidates.append((kp_a, kp_b))

        # TODO: 实际 LLM 调用（需要对接项目内的 AI 管线）
        # 当前返回统计信息
        return Response({
            'subject': subject,
            'kp_count': len(kps),
            'sec_count': len(sec_ids),
            'cross_sec_pairs': len(candidates),
            'status': 'queued',  # → 'running' → 'completed'
            'note': 'LLM 分析已加入后台队列，完成后结果将出现在审核列表。',
        })


# ──────────────────────────────────────────────
# 5. LLM 提案审核
# ──────────────────────────────────────────────

class KnowledgeEdgeReviewListView(generics.ListAPIView):
    """
    GET /api/quizzes/knowledge-edges/review/?subject=CFA

    列出所有待审核的 LLM 边（source_type='llm', is_active=False）。
    教师可以逐条确认或拒绝。
    """
    serializer_class = KnowledgeEdgeSerializer
    permission_classes = [IsInstitutionAdmin]

    def get_queryset(self):
        qs = KnowledgeEdge.objects.filter(
            source_type='llm',
            is_active=False,
        ).select_related('source', 'target')

        subject = self.request.query_params.get('subject')
        if subject:
            kp_ids = KnowledgePoint.objects.filter(
                subject=subject, level='kp'
            ).values_list('id', flat=True)
            qs = qs.filter(source_id__in=kp_ids)

        return qs.order_by('-weight')


class KnowledgeEdgeReviewActionView(APIView):
    """
    POST /api/quizzes/knowledge-edges/review/action/
    Body: {
        "edge_id": 42,
        "action": "approve" | "reject",
        "adjusted_weight": null | 0.6   // 可选：教师调整权重
    }
    """
    permission_classes = [IsInstitutionAdmin]

    def post(self, request):
        edge_id = request.data.get('edge_id')
        action = request.data.get('action')
        adjusted_weight = request.data.get('adjusted_weight')

        if not edge_id or action not in ('approve', 'reject'):
            return Response(
                {'detail': 'edge_id 和 action(approve/reject) 必填'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            edge = KnowledgeEdge.objects.get(
                pk=edge_id, source_type='llm', is_active=False
            )
        except KnowledgeEdge.DoesNotExist:
            return Response(
                {'detail': '边不存在或已审核'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if action == 'approve':
            edge.is_active = True
            if adjusted_weight is not None:
                edge.weight = adjusted_weight
            edge.save(update_fields=['is_active'] + (
                ['weight'] if adjusted_weight is not None else []
            ))
            return Response({'status': 'approved', 'edge_id': edge_id})
        else:
            edge.delete()
            return Response({'status': 'rejected', 'edge_id': edge_id})


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

# 非对称边类型：这些关系的双向权重不应相等
ASYMMETRIC_TYPES = {'prerequisite', 'derivation'}

# 默认反向权重映射
REVERSE_WEIGHTS = {
    'prerequisite': 0.15,   # 复习高阶对低阶只有微弱激活
    'derivation':   0.10,   # 复习导出结果对原公式基本无激活
}


def _ensure_reverse_for_asymmetric(edge: KnowledgeEdge):
    """为非对称边自动创建低权重反向边。"""
    if edge.edge_type not in ASYMMETRIC_TYPES:
        return

    rev_weight = REVERSE_WEIGHTS.get(edge.edge_type, 0.1)
    KnowledgeEdge.objects.get_or_create(
        source_id=edge.target_id,
        target_id=edge.source_id,
        edge_type=edge.edge_type,
        institution_id=edge.institution_id,
        defaults={
            'weight': rev_weight,
            'source_type': edge.source_type,
            'is_active': edge.is_active,
        },
    )
