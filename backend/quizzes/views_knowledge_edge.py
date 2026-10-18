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
  - 有向关系（prerequisite / derivation）仅保留原始方向
"""
import logging
from django.db import transaction, models as dm
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from quizzes.models import KnowledgePoint, KnowledgeEdge
from quizzes.serializers import KnowledgeEdgeSerializer
from users.permissions import IsInstitutionAdmin
from core.utils import apply_institution_filter, get_content_institution_id

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

    def get_serializer(self, *args, **kwargs):
        serializer = super().get_serializer(*args, **kwargs)
        if self.request.method in ('POST', 'PUT', 'PATCH'):
            for field in ('source', 'target'):
                serializer.fields[field].queryset = apply_institution_filter(
                    KnowledgePoint.objects.all(), self.request.user, self.request)
        return serializer

    def get_queryset(self):
        user = self.request.user
        qs = KnowledgeEdge.objects.select_related('source', 'target')

        qs = apply_institution_filter(qs, user, self.request)
        scope_id = get_content_institution_id()
        qs = qs.filter(source__institution_id=scope_id, target__institution_id=scope_id)

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
        from quizzes.services.memorix_scheduler import invalidate_adjacency_cache
        institution_id = get_content_institution_id()
        validated = serializer.validated_data
        existing = KnowledgeEdge.objects.filter(
            source=validated['source'],
            target=validated['target'],
            edge_type=validated['edge_type'],
            institution_id=institution_id,
        ).first()
        if existing is not None:
            if existing.source_type == 'tree':
                raise PermissionDenied('树边由系统自动维护，不可创建相同关系。')
            raise ValidationError({'detail': '该关系已存在。'})
        with transaction.atomic():
            serializer.save(
                source_type='manual',
                institution_id=institution_id,
            )
            transaction.on_commit(invalidate_adjacency_cache)


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

    def get_serializer(self, *args, **kwargs):
        serializer = super().get_serializer(*args, **kwargs)
        if self.request.method in ('POST', 'PUT', 'PATCH'):
            for field in ('source', 'target'):
                serializer.fields[field].queryset = apply_institution_filter(
                    KnowledgePoint.objects.all(), self.request.user, self.request)
        return serializer

    def get_queryset(self):
        scope_id = get_content_institution_id()
        return apply_institution_filter(
            KnowledgeEdge.objects.select_related('source', 'target'), self.request.user, self.request,
        ).filter(source__institution_id=scope_id, target__institution_id=scope_id)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.source_type == 'tree':
            return Response(
                {'detail': '树边由系统自动维护，不可手动删除。请修改知识树结构。'},
                status=status.HTTP_403_FORBIDDEN,
            )
        from quizzes.services.memorix_scheduler import invalidate_adjacency_cache
        with transaction.atomic():
            self.perform_destroy(instance)
            transaction.on_commit(invalidate_adjacency_cache)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_update(self, serializer):
        # tree 边不允许手动修改
        instance = serializer.instance
        if instance.source_type == 'tree':
            raise PermissionDenied('树边由系统自动维护，不可手动修改。')
        from quizzes.services.memorix_scheduler import invalidate_adjacency_cache
        validated = serializer.validated_data
        institution_id = get_content_institution_id()
        if {'source', 'target', 'edge_type'} & set(validated):
            duplicate = KnowledgeEdge.objects.filter(
                source=validated.get('source', instance.source),
                target=validated.get('target', instance.target),
                edge_type=validated.get('edge_type', instance.edge_type),
                institution_id=institution_id,
            ).exclude(pk=instance.pk).first()
            if duplicate is not None:
                if duplicate.source_type == 'tree':
                    raise PermissionDenied('树边由系统自动维护，不可改成相同关系。')
                raise ValidationError({'detail': '该关系已存在。'})
        # 如果 source_type 是 llm，修改后保持不变（仍是 llm 标注 + 人工校准）
        with transaction.atomic():
            serializer.save(institution_id=institution_id)
            transaction.on_commit(invalidate_adjacency_cache)


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

        from quizzes.services.memorix_scheduler import invalidate_adjacency_cache
        inst_id = get_content_institution_id()
        created, skipped, errors = 0, 0, []
        changed = False

        try:
            for i, data in enumerate(edges_data):
                serializer = KnowledgeEdgeSerializer(data={'edge_type': 'similar', 'weight': 0.5, **data})
                for field in ('source', 'target'):
                    serializer.fields[field].queryset = KnowledgePoint.objects.filter(institution_id=inst_id)
                if not serializer.is_valid():
                    errors.append({'index': i, 'error': serializer.errors})
                    continue
                validated = serializer.validated_data
                source_id, target_id = validated['source'].pk, validated['target'].pk
                edge_type, weight = validated['edge_type'], validated['weight']

                existing = KnowledgeEdge.objects.filter(
                    source_id=source_id,
                    target_id=target_id,
                    edge_type=edge_type,
                    institution_id=inst_id,
                ).first()
                if existing is None:
                    KnowledgeEdge.objects.create(
                        source_id=source_id,
                        target_id=target_id,
                        edge_type=edge_type,
                        institution_id=inst_id,
                        weight=weight,
                        source_type='manual',
                        is_active=True,
                    )
                    created += 1
                    changed = True
                elif existing.source_type == 'tree':
                    skipped += 1
                    errors.append({'index': i, 'error': {'detail': '树边由系统自动维护，不可批量覆盖。'}})
                else:
                    existing.weight = weight
                    existing.is_active = True
                    existing.save(update_fields=['weight', 'is_active', 'updated_at'])
                    skipped += 1
                    changed = True
        finally:
            if changed:
                transaction.on_commit(invalidate_adjacency_cache)

        return Response({'created': created, 'skipped': skipped, 'errors': errors})


