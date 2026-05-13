import logging
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView
from quizzes.models import KnowledgePoint, KnowledgePointAnnotation
from quizzes.serializers import KnowledgePointSerializer, KnowledgePointAnnotationSerializer
from users.permissions import IsAdminWriteMemberRead, IsMemberOrAdmin, HasPlanFeature, HasAIQuota
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
    queryset = KnowledgePoint.objects.filter(parent__isnull=True).order_by('id')
    serializer_class = KnowledgePointSerializer
    permission_classes = [IsAdminWriteMemberRead]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.request.user.is_authenticated:
            context["annotation_map"] = _build_annotation_map(self.request.user)
        return context


class KnowledgePointDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = KnowledgePoint.objects.all()
    serializer_class = KnowledgePointSerializer
    permission_classes = [IsAdminWriteMemberRead]

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

        count = AIService.batch_generate_questions(KnowledgePoint.objects.filter(id=kp.id), count_per_kp=3)

        if count == 0:
            return Response({'error': 'AI 生成失败或未生成任何题目'}, status=500)

        increment_ai_quota(request.user.institution)
        return Response({'status': 'success', 'count': count})
