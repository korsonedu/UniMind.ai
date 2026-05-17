import logging
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView
from quizzes.models import KnowledgePoint, KnowledgePointAnnotation
from quizzes.serializers import KnowledgePointSerializer, KnowledgePointAnnotationSerializer
from users.permissions import IsAdminWriteMemberRead, IsMemberOrAdmin, HasPlanFeature, HasAIQuota, IsAdmin, IsInstitutionAdmin
from users.quota import increment_ai_quota
from ai_service import AIService

logger = logging.getLogger(__name__)


def _build_annotation_map(user):
    rows = KnowledgePointAnnotation.objects.filter(user=user).only(
        "knowledge_point_id", "mastery_level", "priority", "confidence_score", "tags", "updated_at"
    )
    return {row.knowledge_point_id: row for row in rows}


class KnowledgePointListView(generics.ListCreateAPIView):
    # 只返回 parent__isnull=True 的顶层，序列化器会通过 children 把下面所有的全拉出来。
    queryset = KnowledgePoint.objects.filter(parent__isnull=True).order_by('order', 'id')
    serializer_class = KnowledgePointSerializer
    permission_classes = [IsAdminWriteMemberRead]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return qs.none()
        # 平台管理员：只看全局知识树（institution=NULL），不得接触机构资产
        if getattr(user, 'is_platform_admin', False) and user.institution is None:
            return qs.filter(institution__isnull=True)
        # 机构用户：只看本机构知识树
        if user.institution:
            return qs.filter(institution=user.institution)
        return qs.none()

    def perform_create(self, serializer):
        user = self.request.user
        institution = None
        if user.is_authenticated and not getattr(user, 'is_platform_admin', False) and user.institution:
            institution = user.institution
        serializer.save(institution=institution)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.request.user.is_authenticated:
            context["annotation_map"] = _build_annotation_map(self.request.user)
        return context


class KnowledgePointDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = KnowledgePoint.objects.all()
    serializer_class = KnowledgePointSerializer
    permission_classes = [IsAdminWriteMemberRead]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return qs.none()
        # 平台管理员：只接触全局节点
        if getattr(user, 'is_platform_admin', False) and user.institution is None:
            return qs.filter(institution__isnull=True)
        # 机构用户：只接触本机构节点
        if user.institution:
            return qs.filter(institution=user.institution)
        return qs.none()

    def perform_update(self, serializer):
        user = self.request.user
        institution = None
        if not getattr(user, 'is_platform_admin', False) and user.institution:
            institution = user.institution
        serializer.save(institution=institution)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.request.user.is_authenticated:
            context["annotation_map"] = _build_annotation_map(self.request.user)
        return context


class MyKnowledgePointAnnotationView(APIView):
    permission_classes = [IsMemberOrAdmin]

    def get(self, request, pk):
        kp = get_object_or_404(KnowledgePoint, pk=pk)
        annotation, _ = KnowledgePointAnnotation.objects.get_or_create(
            user=request.user,
            knowledge_point=kp,
        )
        return Response(KnowledgePointAnnotationSerializer(annotation).data)

    def patch(self, request, pk):
        kp = get_object_or_404(KnowledgePoint, pk=pk)
        annotation, _ = KnowledgePointAnnotation.objects.get_or_create(
            user=request.user,
            knowledge_point=kp,
        )
        serializer = KnowledgePointAnnotationSerializer(annotation, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        # tags 统一清洗为字符串数组；confidence 控制在 0-100。
        tags = serializer.validated_data.get("tags")
        if tags is not None:
            cleaned_tags = []
            for item in tags:
                text = str(item).strip()
                if text:
                    cleaned_tags.append(text)
            serializer.validated_data["tags"] = cleaned_tags[:20]

        if "confidence_score" in serializer.validated_data:
            try:
                score = int(serializer.validated_data["confidence_score"])
            except (ValueError, TypeError):
                score = 0
            serializer.validated_data["confidence_score"] = max(0, min(score, 100))

        serializer.save()
        return Response(serializer.data)


class MyKnowledgePointAnnotationListView(generics.ListAPIView):
    serializer_class = KnowledgePointAnnotationSerializer
    permission_classes = [IsMemberOrAdmin]

    def get_queryset(self):
        qs = KnowledgePointAnnotation.objects.select_related("knowledge_point").filter(user=self.request.user).order_by("-updated_at")
        mastery = str(self.request.query_params.get("mastery") or "").strip()
        priority = str(self.request.query_params.get("priority") or "").strip()
        if mastery:
            qs = qs.filter(mastery_level=mastery)
        if priority:
            qs = qs.filter(priority=priority)
        return qs


class GenerateBulkQuestionsView(APIView):
    permission_classes = [HasPlanFeature, HasAIQuota]
    required_feature = 'ai.generate'
    def post(self, request, pk):
        try:
            kp = KnowledgePoint.objects.get(pk=pk)
        except KnowledgePoint.DoesNotExist:
            return Response({'error': '知识点不存在'}, status=404)

        count = AIService.batch_generate_questions(KnowledgePoint.objects.filter(id=kp.id), count_per_kp=3, institution=request.user.institution)

        if count == 0:
            return Response({'error': 'AI 生成失败或未生成任何题目'}, status=500)

        increment_ai_quota(request.user.institution)
        return Response({'status': 'success', 'count': count})


# ── MD Knowledge Tree Import / Export ──

import re
from django.db import transaction


def _parse_md_knowledge_tree(md_text: str) -> list:
    """
    Parse Markdown knowledge tree into structured data.
    Format:
      # MB - 货币银行学           → prefix_category, level='sub'
      ## MB-1 - 货币的起源        → level='ch', code='MB-1'
      ### MB-1-1 - 商品交换       → level='sec', code='MB-1-1'
      #### MB-1-1-1 - 一般等价物  → level='kp', code='MB-1-1-1'
    Lines not starting with # are treated as descriptions for the last node.
    """
    nodes = []
    current_path = {1: None, 2: None, 3: None, 4: None}  # heading level → node id

    for line in md_text.strip().split('\n'):
        line = line.strip()
        if not line:
            continue

        # Support both "#" headings and "- [CODE] Name" for KP-level nodes
        heading_match = re.match(r'^(#{1,4})\s+(.+)', line)
        dash_match = re.match(r'^-\s+\[(.*?)\]\s*(.*)$', line)
        if heading_match or dash_match:
            if heading_match:
                level = len(heading_match.group(1))  # 1-4
                content = heading_match.group(2).strip()
                # Parse code and name — supports two formats:
                #   1. "[CODE] Name (extra)"   — from management command style
                #   2. "CODE - Name"           — from frontend import panel
                bracket_match = re.match(r'^\[(.*?)\]\s*(.*)$', content)
                if bracket_match:
                    code = bracket_match.group(1).strip()
                    name = bracket_match.group(2).strip()
                else:
                    parts = content.split(' - ', 1)
                    if len(parts) > 1:
                        code = parts[0].strip()
                        name = parts[1].strip()
                    else:
                        # No recognizable code format — skip (comment or non-node line)
                        continue
            else:
                # dash_match: "- [CODE] Name" → KP level
                level = 4
                code = dash_match.group(1).strip()
                name = dash_match.group(2).strip()

            # Strip parenthesized annotations from name (e.g. "货币银行学（基础理论组）" → "货币银行学")
            name = re.sub(r'[（\(].*?[）\)]', '', name).strip()

            # Determine KP level from heading depth
            kp_level = {1: 'sub', 2: 'ch', 3: 'sec', 4: 'kp'}.get(level, 'kp')

            # Extract prefix from code
            prefix = code.split('-')[0].strip().upper() if code else ''

            node = {
                'code': code,
                'name': name,
                'level': kp_level,
                'prefix_category': prefix,
                'heading_level': level,
                'description': '',
            }
            nodes.append(node)
            current_path[level] = len(nodes) - 1

            # Set parent based on previous heading level, with ancestor fallback
            parent_level = level - 1
            while parent_level >= 1:
                if current_path.get(parent_level) is not None:
                    parent_node = nodes[current_path[parent_level]]
                    if 'children' not in parent_node:
                        parent_node['children'] = []
                    parent_node['children'].append(node)
                    break
                parent_level -= 1

            # Clear deeper levels
            for l in range(level + 1, 5):
                current_path[l] = None
        else:
            # Description line — append to last node
            if nodes:
                last = nodes[-1]
                if last['description']:
                    last['description'] += '\n' + line
                else:
                    last['description'] = line

    # Return only top-level nodes (heading level 1)
    return [n for n in nodes if n['heading_level'] == 1]


def _create_or_update_knowledge_tree(nodes: list, parent=None, prefix='', institution=None):
    """Recursively create/update KnowledgePoint entries from parsed tree."""
    created_count = 0
    updated_count = 0

    for i, node in enumerate(nodes):
        code = node.get('code', '')
        name = node.get('name', '')
        kp_level = node.get('level', 'kp')
        description = node.get('description', '')
        prefix_category = node.get('prefix_category', prefix)

        # Try to find existing by code, strictly scoped to same institution bucket
        existing = None
        if code:
            qs = KnowledgePoint.objects.filter(code=code)
            if institution:
                qs = qs.filter(institution=institution)
            else:
                qs = qs.filter(institution__isnull=True)
            existing = qs.first()

        if existing:
            existing.name = name
            existing.level = kp_level
            existing.description = description
            existing.prefix_category = prefix_category
            existing.parent = parent
            existing.institution = institution
            existing.order = i
            existing.save()
            updated_count += 1
            current = existing
        else:
            current = KnowledgePoint.objects.create(
                code=code or None,
                name=name,
                level=kp_level,
                prefix_category=prefix_category,
                description=description,
                parent=parent,
                order=i,
                institution=institution,
            )
            created_count += 1

        # Recurse children
        children = node.get('children', [])
        if children:
            cc, cu = _create_or_update_knowledge_tree(children, parent=current, prefix=prefix_category, institution=institution)
            created_count += cc
            updated_count += cu

    return created_count, updated_count


class KnowledgePointImportMDView(APIView):
    """从 Markdown 文件导入知识体系。平台管理员或机构管理员可操作。"""
    permission_classes = [IsAdmin | IsInstitutionAdmin]

    @transaction.atomic
    def post(self, request):
        md_text = request.data.get('content', '')
        if not md_text:
            # Try file upload
            file = request.FILES.get('file')
            if file:
                md_text = file.read().decode('utf-8')
            else:
                return Response({'error': '请提供 Markdown 内容或上传文件'}, status=400)

        try:
            tree = _parse_md_knowledge_tree(md_text)
        except Exception as e:
            return Response({'error': f'Markdown 解析失败: {str(e)}'}, status=400)

        if not tree:
            return Response({'error': '未解析到有效的知识树结构'}, status=400)

        # 机构管理员自动关联本机构，平台管理员导入为全局树（不得接触机构资产）
        institution = None
        user = request.user
        if not getattr(user, 'is_platform_admin', False) and user.institution:
            institution = user.institution

        created, updated = _create_or_update_knowledge_tree(tree, institution=institution)
        return Response({
            'status': 'ok',
            'created': created,
            'updated': updated,
            'institution_id': institution.id if institution else None,
            'categories': [n.get('prefix_category', '') for n in tree],
        })


class KnowledgePointExportMDView(APIView):
    """导出知识体系为 Markdown。平台管理员或机构管理员可操作。"""
    permission_classes = [IsAdmin | IsInstitutionAdmin]

    def get(self, request):
        user = request.user
        # 平台管理员导出全局树，机构管理员导出本机构树
        if getattr(user, 'is_platform_admin', False) and user.institution is None:
            root_filter = {'institution__isnull': True}
        elif user.institution:
            root_filter = {'institution': user.institution}
        else:
            return Response({'error': '无法确定所属机构'}, status=400)

        roots = KnowledgePoint.objects.filter(level='sub', parent__isnull=True, **root_filter).order_by('order', 'id')
        if not roots.exists():
            # Fallback: get all top-level nodes
            roots = KnowledgePoint.objects.filter(parent__isnull=True, **root_filter).order_by('order', 'id')

        lines = []
        for root in roots:
            _export_node_md(root, lines, 1)

        md_text = '\n'.join(lines)
        return Response({'content': md_text, 'format': 'markdown'})


def _export_node_md(node, lines, depth):
    """Recursively export a KnowledgePoint node to Markdown lines."""
    heading = '#' * min(depth, 4)
    code_str = f'{node.code} - ' if node.code else ''
    lines.append(f'{heading} {code_str}{node.name}')
    if node.description:
        lines.append(node.description)
        lines.append('')
    for child in node.children.all().order_by('order', 'id'):
        _export_node_md(child, lines, depth + 1)
