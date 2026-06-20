"""
Field Diagnostic API

POST /api/quizzes/field/diagnose/
  Run Field diagnostic for the current user on a subject.
  Body: {"subject": "金融431", "lam": 0.5, "days": 90, "observations": optional}

GET /api/quizzes/field/subjects/
  List subjects with available knowledge graphs.

POST /api/quizzes/field/invalidate-cache/
  Admin-only: invalidate graph cache for a subject.
"""
import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from quizzes.services.field_service import (
    diagnose_user,
    get_or_build_graph,
    invalidate_graph_cache,
)
from users.permissions import IsAdminWriteMemberRead

logger = logging.getLogger(__name__)


class FieldDiagnoseView(APIView):
    """
    Run Field GMRF diagnostic.

    POST /api/quizzes/field/diagnose/
    {
      "subject": "金融431",      # required
      "lam": 0.5,                # optional, graph smoothness (default 0.5)
      "days": 90,                # optional, lookback days for observations
      "observations": {          # optional, manual observations
        "123": [1, 0, 1],
        "456": [0]
      }
    }

    Response:
    {
      "subject": "金融431",
      "kp_ids": [1, 2, 3, ...],
      "kp_names": ["KP名称1", ...],
      "mastery": [0.72, 0.35, ...],
      "n_observations": 45,
      "converged": true
    }
    """

    permission_classes = [IsAdminWriteMemberRead]

    def post(self, request):
        subject = request.data.get('subject', '').strip()
        if not subject:
            return Response(
                {'error': 'subject is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        lam = float(request.data.get('lam', 0.5))
        days = int(request.data.get('days', 90))
        observations = request.data.get('observations', None)

        # Get user's institution
        user = request.user
        institution_id = None
        if hasattr(user, 'institution') and user.institution:
            institution_id = user.institution_id

        try:
            result = diagnose_user(
                user=user,
                subject=subject,
                institution_id=institution_id,
                observations=observations,
                lam=lam,
                days=days,
            )
        except Exception as e:
            logger.exception(f'Field diagnosis failed: {e}')
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(result)


class FieldSubjectsView(APIView):
    """
    List subjects with available Field graphs.

    GET /api/quizzes/field/subjects/
    → {"subjects": ["金融431", "高中数学", ...]}
    """

    permission_classes = [IsAdminWriteMemberRead]

    def get(self, request):
        from quizzes.models import KnowledgePoint

        subjects = (
            KnowledgePoint.objects
            .filter(level='kp')
            .values_list('subject', flat=True)
            .distinct()
            .order_by('subject')
        )

        return Response({
            'subjects': [s for s in subjects if s],
        })


class FieldInvalidateCacheView(APIView):
    """
    Admin-only: invalidate graph cache.

    POST /api/quizzes/field/invalidate-cache/
    {"subject": "金融431"}
    """

    permission_classes = [IsAdminWriteMemberRead]

    def post(self, request):
        if not request.user.is_staff and not getattr(request.user, 'is_platform_admin', False):
            return Response(
                {'error': 'Admin only'},
                status=status.HTTP_403_FORBIDDEN,
            )

        subject = request.data.get('subject', '').strip()
        if not subject:
            return Response(
                {'error': 'subject is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        invalidate_graph_cache(subject)
        return Response({'status': 'ok', 'subject': subject})
