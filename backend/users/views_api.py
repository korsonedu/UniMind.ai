"""API 开放平台 — API Key 管理与对外数据端点。"""
import hashlib
import hmac
import secrets

from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404

from users.permissions import is_institution_owner
from .models import APICredential
from .serializers_institution import APICredentialSerializer


class APIKeyListCreateView(APIView):
    """GET/POST /api/users/institution/me/api-keys/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        inst = getattr(request.user, 'institution', None)
        if not inst:
            return Response({'error': '无机构归属'}, status=403)
        qs = APICredential.objects.filter(institution=inst)
        ser = APICredentialSerializer(qs, many=True)
        return Response(ser.data)

    def post(self, request):
        if not is_institution_owner(request.user):
            return Response({'error': '仅机构所有者可创建 API Key'}, status=403)

        inst = request.user.institution
        ser = APICredentialSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        # 生成 key_id 和 secret
        key_id = 'ak-' + secrets.token_hex(16)
        raw_secret = secrets.token_hex(32)
        key_secret_hash = hashlib.sha256(raw_secret.encode()).hexdigest()

        cred = ser.save(
            institution=inst,
            key_id=key_id,
            key_secret_hash=key_secret_hash,
            created_by=request.user,
        )

        # 只返回一次 raw secret
        data = APICredentialSerializer(cred).data
        data['secret'] = raw_secret  # 仅创建时返回
        return Response(data, status=201)


class APIKeyDetailView(APIView):
    """DELETE /api/users/institution/me/api-keys/<int:pk>/"""
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        inst = getattr(request.user, 'institution', None)
        cred = get_object_or_404(APICredential, pk=pk, institution=inst)
        cred.delete()
        return Response(status=204)

    def put(self, request, pk):
        inst = getattr(request.user, 'institution', None)
        cred = get_object_or_404(APICredential, pk=pk, institution=inst)
        ser = APICredentialSerializer(cred, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)


# ── External API v1 endpoints (API Key authenticated) ──


class ExternalQuestionListView(APIView):
    """GET /api/v1/questions/ — 题库查询 (scope: read:questions)"""
    permission_classes = []  # API Key auth handled in dispatch

    def get(self, request):
        cred = getattr(request, 'api_credential', None)
        if not cred:
            return Response({'error': 'Invalid API key'}, status=401)
        if 'read:questions' not in getattr(request, 'api_scopes', []):
            return Response({'error': 'Insufficient scope'}, status=403)

        from quizzes.models import Question
        qs = Question.objects.filter(institution=cred.institution).order_by('-created_at')[:100]
        results = [{
            'id': q.id, 'text': q.text, 'q_type': q.q_type,
            'options': q.options, 'answer': q.correct_answer,
            'knowledge_point_id': q.knowledge_point_id,
            'difficulty': q.difficulty,
        } for q in qs]
        return Response({'questions': results, 'count': len(results)})


class ExternalAnalyticsView(APIView):
    """GET /api/v1/analytics/overview/ — 分析概览 (scope: read:analytics)"""
    permission_classes = []

    def get(self, request):
        cred = getattr(request, 'api_credential', None)
        if not cred:
            return Response({'error': 'Invalid API key'}, status=401)
        if 'read:analytics' not in getattr(request, 'api_scopes', []):
            return Response({'error': 'Insufficient scope'}, status=403)

        inst = cred.institution
        from quizzes.models import ReviewLog, UserKnowledgeState
        from django.utils import timezone
        from datetime import timedelta

        now = timezone.now()
        week_ago = now - timedelta(days=7)
        students = inst.students.filter(institution_role='student').count()
        weekly_reviews = ReviewLog.objects.filter(
            user__institution=inst, review_time__gte=week_ago
        ).count()

        return Response({
            'institution': inst.name,
            'total_students': students,
            'weekly_reviews': weekly_reviews,
            'generated_at': now.isoformat(),
        })
