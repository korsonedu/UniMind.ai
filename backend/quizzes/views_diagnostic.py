"""
AI 学情诊断 — 健康趋势与详情 API。
"""

from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from quizzes.models import StudentHealthSnapshot
from quizzes.services.student_health import compute_student_health


class StudentHealthTrendView(APIView):
    """GET /api/quizzes/health-trend/ — 近 30 天健康分趋势。"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        since = timezone.now().date() - timedelta(days=30)
        snapshots = StudentHealthSnapshot.objects.filter(
            user=request.user,
            snapshot_date__gte=since,
        ).order_by('snapshot_date')

        trend = [
            {'date': s.snapshot_date.isoformat(), 'score': s.score, 'level': s.level}
            for s in snapshots
        ]
        current = compute_student_health(request.user) if not snapshots else None

        return Response({
            'trend': trend,
            'current': {
                'score': current['score'],
                'level': current['level'],
                'components': current['components'],
                'details': current['details'],
            } if current else None,
        })


class StudentHealthDetailView(APIView):
    """GET /api/quizzes/health-detail/ — 当前健康度完整分解。"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        health = compute_student_health(request.user)
        return Response(health)
