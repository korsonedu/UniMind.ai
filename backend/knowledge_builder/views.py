from django.db import transaction
from django.db.models import F, Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.authentication import CookieTokenAuthentication
from .models import (KnowledgeTreeBuild, LearningBlock, BlockStepAtom,
                     BlockResourceFeedback, ConceptAssetIndex, PublicAssetCatalog)
from .pipeline import create_build
from .serializers import BuildSummarySerializer, CreateBuildSerializer, FullKnowledgeTreeSerializer, RequirementIntakeSerializer
from . import intake
from .tasks import build_knowledge_tree
from . import block_study, public_asset_service
from .serializers import (AttachBlockResourceSerializer, BlockQuizRequestSerializer, BlockResourceSerializer,
                          BlockResourceUpdateSerializer, PublicAssetCatalogSerializer, TreePublicAssetImportSerializer)


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
        region = public_asset_service.get_region_preference(request.user, request)
        resources = block_study.visible_block_resources(request.user, block, request=request, explicit_region=region)
        data = {'resources': BlockResourceSerializer(resources, many=True, context={'request': request}).data,
                'internal_candidates': block_study.internal_resource_candidates(request.user, block, region), 'web_candidates': [],
                'region_pref': region,
                'wiki_candidates': public_asset_service.wiki_candidates_for_block(block, region),
                'catalog_candidates': PublicAssetCatalogSerializer(
                    public_asset_service.catalog_candidates_for_build(block.build, region, block=block), many=True).data}
        if 'query' in request.query_params:
            data['web_candidates'] = block_study.search_block_web_resources(block, request.query_params['query'], region)
        return Response(data)

    def post(self, request, build_id, block_id):
        block = self.get_block(request, build_id, block_id)
        if request.data.get('action') == 'vote':
            resource_id = serializers.IntegerField(min_value=1).run_validation(request.data.get('resource_id'))
            vote = serializers.ChoiceField(choices=(1, -1, 0)).run_validation(request.data.get('vote'))
            visible_ids = block_study.visible_block_resources(request.user, block, request=request).values('pk')
            # Keep a learner's previous vote cancellable after automatic dismissal.
            dismissed_ids = BlockResourceFeedback.objects.filter(
                user=request.user, resource__block=block,
                resource__is_dismissed=True).values('resource_id')
            votable = block.resources.filter(
                Q(pk__in=visible_ids) | Q(pk__in=dismissed_ids))
            with transaction.atomic():
                resource = get_object_or_404(votable.select_for_update(), pk=resource_id)
                if resource.public_asset_id:
                    # Serialize aggregation across mounts of the same public asset.
                    PublicAssetCatalog.objects.select_for_update().get(pk=resource.public_asset_id)
                if vote == 0:
                    BlockResourceFeedback.objects.filter(resource=resource, user=request.user).delete()
                else:
                    BlockResourceFeedback.objects.update_or_create(
                        resource=resource, user=request.user, defaults={'vote': vote})
                resource.upvotes = resource.feedbacks.filter(vote=1).count()
                resource.downvotes = resource.feedbacks.filter(vote=-1).count()
                if resource.origin == 'auto' and (
                        (resource.downvotes >= 2 and resource.downvotes > resource.upvotes)
                        or request.data.get('dismiss') is True):
                    resource.is_dismissed = True
                resource.save(update_fields=('upvotes', 'downvotes', 'is_dismissed'))
                if resource.public_asset_id:
                    feedbacks = BlockResourceFeedback.objects.filter(
                        resource__public_asset_id=resource.public_asset_id,
                        resource__locator=resource.locator)
                    upvotes = feedbacks.filter(vote=1).count()
                    downvotes = feedbacks.filter(vote=-1).count()
                    alignments = ConceptAssetIndex.objects.filter(
                        public_asset_id=resource.public_asset_id, segment_locator=resource.locator)
                    alignments.update(upvotes=upvotes, downvotes=downvotes)
                    if downvotes - upvotes >= 2:
                        alignments.update(is_disabled=True)
            return Response(BlockResourceSerializer(resource, context={'request': request}).data,
                            status=status.HTTP_200_OK)
        if request.data.get('action') == 'attach_project':
            project_id = serializers.IntegerField(min_value=1).run_validation(request.data.get('project_id'))
            resource_id = serializers.IntegerField(min_value=1).run_validation(request.data.get('resource_id'))
            return Response(block_study.attach_project_resource(request.user, block, project_id, resource_id, request))
        serializer = AttachBlockResourceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resource = block_study.attach_block_resource(request.user, block, serializer.validated_data, request=request)
        return Response(BlockResourceSerializer(resource, context={'request': request}).data, status=status.HTTP_201_CREATED)

    def patch(self, request, build_id, block_id):
        block = self.get_block(request, build_id, block_id)
        serializer = BlockResourceUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        resources = block.resources.filter(~Q(source_kind='library') | Q(created_by=request.user))
        if block.build.created_by_id != request.user.pk:
            resources = resources.filter(created_by=request.user)
        resource = get_object_or_404(resources, pk=payload['resource_id'])
        public_asset_service.validate_public_asset_data(
            {'url': resource.url, 'region_scope': resource.region_scope},
            public_asset_service.get_region_preference(request.user, request),
        )
        target = block
        if 'block_id' in payload:
            target = get_object_or_404(LearningBlock, build=block.build, pk=payload['block_id'])
        moved = target.pk != block.pk
        step_id = payload.get('step_id', None if moved else resource.step_id)
        atom_id = payload.get('atom_id', None if moved else resource.atom_id)
        if step_id is not None and not target.steps.filter(pk=step_id).exists():
            raise ValidationError('步骤不属于目标知识块。')
        if atom_id is not None:
            assignment = BlockStepAtom.objects.filter(step__block=target, atom_id=atom_id).first()
            if assignment is None:
                raise ValidationError('原子点不属于目标知识块。')
            if 'step_id' in payload and step_id is not None and assignment.step_id != step_id:
                raise ValidationError('原子点不属于指定步骤。')
            step_id = assignment.step_id
        resource.block, resource.step_id, resource.atom_id = target, step_id, atom_id
        for field in ('asset_track', 'pedagogical_role', 'locator'):
            if field in payload:
                setattr(resource, field, payload[field])
        resource.save(update_fields=('block', 'step', 'atom', 'asset_track', 'pedagogical_role', 'locator'))
        return Response(BlockResourceSerializer(resource, context={'request': request}).data)

    def delete(self, request, build_id, block_id):
        block = self.get_block(request, build_id, block_id)
        from rest_framework import serializers
        resource_id = serializers.IntegerField(min_value=1).run_validation(request.data.get('resource_id'))
        resources = block.resources.all()
        if block.build.created_by_id != request.user.pk:
            resources = resources.filter(created_by=request.user)
        get_object_or_404(resources, pk=resource_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TreePublicAssetView(BuildStatusView):
    def get(self, request, build_id):
        build = get_object_or_404(_visible_builds(request.user), pk=build_id)
        region = public_asset_service.get_region_preference(request.user, request)
        catalog = public_asset_service.catalog_candidates_for_build(build, region)
        listings = public_asset_service.marketplace_candidates(build)
        albums = public_asset_service.album_candidates(build, request.user)
        wiki_assets = {asset.url: asset for asset in catalog if asset.asset_track == 'wiki'}
        wiki_candidates = [
            {'public_asset_id': asset.pk, 'title': asset.title, 'url': asset.url,
             'source_kind': asset.source_kind, 'asset_track': asset.asset_track,
             'region_scope': asset.region_scope, 'summary': asset.description}
            for asset in wiki_assets.values()]
        if not wiki_candidates:
            try:
                from .public_asset_resolvers import search_wikipedia_concepts
            except ModuleNotFoundError as exc:
                if exc.name != f'{__package__}.public_asset_resolvers':
                    raise
            else:
                wiki_candidates = [
                    candidate for candidate in search_wikipedia_concepts(
                        build.subject, lang='en' if region == 'intl' else 'zh', region_pref=region)
                    if public_asset_service.public_asset_allowed(candidate, region)]
        mounted = build.block_resources.filter(is_dismissed=False).filter(~Q(source_kind='library') | Q(created_by=request.user))
        mounted = public_asset_service.filter_resources_for_region(mounted, region)
        summary = {track: 0 for track in ('spine', 'spotlight', 'wiki')}
        for track in mounted.values_list('asset_track', flat=True):
            summary[track] += 1
        summary.update({f'{track}_count': summary[track] for track in ('spine', 'spotlight', 'wiki')})
        return Response({
            'region_pref': region,
            'catalog_assets': PublicAssetCatalogSerializer(catalog, many=True).data,
            'marketplace_listings': [
                {'id': row.pk, 'title': row.title, 'subject': row.subject, 'description': row.description,
                 'content_type': row.content_type, 'license_type': row.license_type, 'status': row.status, 'url': '/courses'}
                for row in listings],
            'albums': [{'id': row.pk, 'name': row.name, 'title': row.name, 'description': row.description,
                        'url': '/courses'} for row in albums],
            'wiki_candidates': wiki_candidates,
            'mounted_summary': summary,
        })

    def post(self, request, build_id):
        build = get_object_or_404(_visible_builds(request.user), pk=build_id)
        if request.data.get('action') == 'auto_discover':
            from . import public_asset_discovery
            result = public_asset_discovery.auto_discover_and_mount_public_assets(
                build, user=request.user, request=request)
            summary = result.get('mounted_summary', {})
            summary = {**summary, **{
                f'{track}_count': summary.get(f'{track}_count', summary.get(track, 0))
                for track in ('spine', 'spotlight', 'wiki')}}
            return Response({
                'mounted_count': result['mounted_count'],
                'discovered_assets_count': result['discovered_assets_count'],
                'reused_concept_count': result['reused_concept_count'],
                'asset_track': 'spotlight',
                'public_asset': None,
                'mounted_summary': summary,
                'resources': BlockResourceSerializer(
                    result['resources'], many=True, context={'request': request}).data,
            }, status=status.HTTP_200_OK)
        serializer = TreePublicAssetImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = public_asset_service.import_tree_public_asset(request.user, build, serializer.validated_data, request=request)
        return Response({
            'mounted_count': result['mounted_count'],
            'asset_track': result['asset_track'],
            'public_asset': PublicAssetCatalogSerializer(result['public_asset']).data if result['public_asset'] else None,
            'resources': BlockResourceSerializer(result['resources'], many=True, context={'request': request}).data,
        }, status=status.HTTP_201_CREATED)


class BlockQuizView(BlockResourceView):
    http_method_names = ('post', 'options')

    def post(self, request, build_id, block_id):
        block = self.get_block(request, build_id, block_id)
        serializer = BlockQuizRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        from .block_assessments import block_assessment
        return Response(block_assessment(request.user, block, **payload))
