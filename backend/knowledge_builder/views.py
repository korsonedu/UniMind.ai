from django.db.models import F, Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.authentication import CookieTokenAuthentication
from .models import KnowledgeTreeBuild, LearningBlock
from .pipeline import create_build
from .serializers import BuildSummarySerializer, CreateBuildSerializer, FullKnowledgeTreeSerializer, RequirementIntakeSerializer
from . import intake
from .tasks import build_knowledge_tree
from . import block_study
from .serializers import AttachBlockResourceSerializer, BlockQuizRequestSerializer, BlockResourceSerializer


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
            'block_edges', 'cross_block_interfaces', 'blocks__resources',
        )
        build = get_object_or_404(queryset, pk=build_id)
        return Response(self.serializer_class(build, context={'request': request}).data)


class BlockResourceView(BuildStatusView):
    def get_block(self, request, build_id, block_id):
        build = get_object_or_404(_visible_builds(request.user), pk=build_id)
        return get_object_or_404(LearningBlock.objects.select_related('build'), build=build, pk=block_id)

    def get(self, request, build_id, block_id):
        block = self.get_block(request, build_id, block_id)
        resources = block_study.visible_block_resources(request.user, block)
        data = {'resources': BlockResourceSerializer(resources, many=True).data,
                'internal_candidates': block_study.internal_resource_candidates(request.user, block), 'web_candidates': []}
        if 'query' in request.query_params:
            data['web_candidates'] = block_study.search_block_web_resources(block, request.query_params['query'])
        return Response(data)

    def post(self, request, build_id, block_id):
        block = self.get_block(request, build_id, block_id)
        serializer = AttachBlockResourceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resource = block_study.attach_block_resource(request.user, block, serializer.validated_data)
        return Response(BlockResourceSerializer(resource).data, status=status.HTTP_201_CREATED)

    def delete(self, request, build_id, block_id):
        block = self.get_block(request, build_id, block_id)
        from rest_framework import serializers
        resource_id = serializers.IntegerField(min_value=1).run_validation(request.data.get('resource_id'))
        resources = block.resources.all()
        if block.build.created_by_id != request.user.pk:
            resources = resources.filter(created_by=request.user)
        get_object_or_404(resources, pk=resource_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BlockQuizView(BlockResourceView):
    http_method_names = ('post', 'options')

    def post(self, request, build_id, block_id):
        block = self.get_block(request, build_id, block_id)
        serializer = BlockQuizRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        if payload['action'] == 'submit':
            return Response(block_study.submit_block_quiz(request.user, block, payload['questions'], payload['answers']))
        return Response(block_study.generate_block_quiz(request.user, block, payload['mode'], payload['retest']))
