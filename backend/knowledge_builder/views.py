from django.db.models import F, Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.authentication import CookieTokenAuthentication
from .models import KnowledgeTreeBuild
from .pipeline import create_build
from .serializers import BuildSummarySerializer, CreateBuildSerializer, FullKnowledgeTreeSerializer, RequirementIntakeSerializer
from . import intake
from .tasks import build_knowledge_tree


def _visible_builds(user):
    """Builds created by the user or shared system/CLI builds with no owner."""
    return KnowledgeTreeBuild.objects.filter(Q(created_by=user) | Q(created_by__isnull=True))


def _listable_builds(user):
    """Show all own builds plus completed unowned (CLI/curated) builds."""
    return KnowledgeTreeBuild.objects.filter(
        Q(created_by=user)
        | Q(created_by__isnull=True, status=KnowledgeTreeBuild.Status.COMPLETED)
    ).order_by(F('completed_at').desc(nulls_last=True), '-created_at')


class BuildCreateView(APIView):
    authentication_classes = (CookieTokenAuthentication,)
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        builds = _listable_builds(request.user)
        return Response(BuildSummarySerializer(builds, many=True).data)

    def post(self, request):
        serializer = CreateBuildSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        build = create_build(
            serializer.validated_data['subject'],
            archetype_override=serializer.validated_data['archetype'],
            created_by=request.user,
            requirements=serializer.validated_data.get('requirements') or {},
        )
        enqueue_build(build)
        return Response(BuildSummarySerializer(build).data, status=status.HTTP_202_ACCEPTED)


class BuildIntakeView(APIView):
    authentication_classes = (CookieTokenAuthentication,)
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        serializer = RequirementIntakeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(intake.inquire_requirements(request.user, serializer.validated_data))


def enqueue_build(build):
    """Record broker submission failure and preserve the original exception."""
    try:
        return build_knowledge_tree.delay(str(build.pk))
    except Exception as exc:
        build.status = KnowledgeTreeBuild.Status.FAILED
        build.error_message = f'Task submission failed: {exc}'
        build.save(update_fields=('status', 'error_message', 'updated_at'))
        raise


class BuildStatusView(APIView):
    authentication_classes = (CookieTokenAuthentication,)
    permission_classes = (IsAuthenticated,)
    serializer_class = BuildSummarySerializer

    def get(self, request, build_id):
        build = get_object_or_404(_visible_builds(request.user), pk=build_id)
        return Response(self.serializer_class(build).data)


class BuildDetailView(BuildStatusView):
    serializer_class = FullKnowledgeTreeSerializer

    def get(self, request, build_id):
        queryset = _visible_builds(request.user).prefetch_related(
            'modules', 'atoms', 'atom_edges', 'blocks__steps__step_atoms',
            'block_edges', 'cross_block_interfaces',
        )
        build = get_object_or_404(queryset, pk=build_id)
        return Response(self.serializer_class(build).data)
