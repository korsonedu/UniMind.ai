from pathlib import Path

from django.db import transaction
from django.db.models import Case, Count, F, Q, When
from django.db.models.functions import Now
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from courses.access import visible_courses
from users.feature_access import has_learning_feature
from users.permissions import IsMember
from users.workspaces.identity import learner_identity

from .models import WORKBENCH_SOURCE_PREFIX, ConversationProject, ProjectSource
from .serializers_workbench import (
    UPLOAD_FORMATS, ProjectSourceBatchSelectSerializer, ProjectSourceDetailSerializer,
    ProjectSourceImportSerializer, ProjectSourcePatchSerializer, ProjectSourceSummarySerializer,
    ProjectSourceUploadSerializer,
)
from .services.workbench_ingest import dispatch_project_source_processing
from .services.workbench_grounding import active_sources
from .services.workbench_overview import extractive_overview, source_signature, synthesize_overview


class ProjectSourceView(APIView):
    permission_classes = [IsMember]

    def get_project(self, pk, *, for_update=False):
        projects = ConversationProject.objects.select_for_update() if for_update else ConversationProject.objects.all()
        return get_object_or_404(projects, pk=pk, user=self.request.user)

    def sources(self, pk):
        return self.get_project(pk).workbench_sources.filter(user=self.request.user)

    def require_personal_space(self):
        if learner_identity(self.request.user) is not None:
            raise PermissionDenied('请在本人个人空间中处理项目来源。')


class ProjectSourceListView(ProjectSourceView):
    def get(self, request, pk):
        sources = list(self.sources(pk).order_by('-created_at', 'pk'))
        return Response({
            'project_id': pk,
            'total_count': len(sources),
            'selected_count': sum(source.is_selected for source in sources),
            'ready_count': sum(source.status == ProjectSource.Status.READY for source in sources),
            'sources': ProjectSourceSummarySerializer(sources, many=True).data,
        })


class ProjectWorkbenchOverviewView(ProjectSourceView):
    def get(self, request, pk):
        return self.overview(pk, synthesize=False)

    def post(self, request, pk):
        return self.overview(pk, synthesize=True)

    def overview(self, pk, *, synthesize):
        self.require_personal_space()
        project = self.get_project(pk)
        sources = active_sources(project)
        signature = source_signature(sources)
        if project.workbench_overview.get('source_signature') == signature:
            return Response(project.workbench_overview)
        if not synthesize or not sources:
            return Response({**extractive_overview(sources), 'source_signature': signature})

        overview = synthesize_overview(sources)
        if overview is None:
            return Response({'error': '本次未能生成项目概览，请稍后重试。'}, status=status.HTTP_502_BAD_GATEWAY)
        payload = {**overview, 'source_signature': signature}
        with transaction.atomic():
            project = self.get_project(pk, for_update=True)
            if source_signature(active_sources(project)) != signature:
                return Response({'error': '已选资料发生变化，请刷新项目概览。'}, status=status.HTTP_409_CONFLICT)
            if project.workbench_overview.get('source_signature') == signature:
                return Response(project.workbench_overview)
            project.workbench_overview = payload
            project.save(update_fields=['workbench_overview'])
        return Response(payload)


class ProjectSourceUploadView(ProjectSourceView):
    parser_classes = [MultiPartParser]

    def post(self, request, pk):
        project = self.get_project(pk)
        self.require_personal_space()
        files = request.FILES.getlist('files') or request.FILES.getlist('file')
        payload = ProjectSourceUploadSerializer(data={'files': files})
        payload.is_valid(raise_exception=True)

        sources = []
        try:
            with transaction.atomic():
                for file in payload.validated_data['files']:
                    source_type, mime_type = UPLOAD_FORMATS[Path(file.name).suffix.lower()]
                    source = ProjectSource(
                        project=project, user=request.user, source_type=source_type, title=file.name[:240],
                        file=file, file_size=file.size, mime_type=mime_type,
                    )
                    sources.append(source)
                    source.save()
        except Exception:
            # File storage writes are independent of the database transaction.
            for source in sources:
                if source.file._committed:
                    source.file.delete(save=False)
            raise

        for source in sources:
            dispatch_project_source_processing(source)
            source.refresh_from_db()
        return Response({'sources': ProjectSourceSummarySerializer(sources, many=True).data}, status=status.HTTP_201_CREATED)


class ProjectSourceImportView(ProjectSourceView):
    def post(self, request, pk):
        self.get_project(pk)
        self.require_personal_space()
        payload = ProjectSourceImportSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        kind = data['kind']
        if kind == ProjectSource.Type.COURSE:
            if not has_learning_feature(request.user, 'course.video'):
                raise Http404
            course = get_object_or_404(visible_courses(request), pk=data['course_id'])

        with transaction.atomic():
            # Web URLs and course IDs have no unique constraint on ProjectSource.
            project = self.get_project(pk, for_update=True)
            sources = project.workbench_sources.filter(user=request.user)
            pending = {'status': ProjectSource.Status.PENDING, 'error_message': ''}
            if kind == ProjectSource.Type.WEB_URL:
                url = data['url']
                source = sources.select_for_update().filter(source_type=kind).filter(
                    Q(metadata__url=url) | Q(metadata__url__isnull=True, source_url=url),
                ).order_by('created_at', 'pk').first()
                created = source is None
                if created:
                    source = ProjectSource(project=project, user=request.user, source_type=kind, title=url[:240])
                source.metadata = {**source.metadata, 'url': url}
                if 'title' in data:
                    source.title = data['title']
                    source.metadata['title'] = source.title
                source.source_url = url
                source.status = ProjectSource.Status.PENDING
                source.error_message = ''
                source.save()
            elif kind == ProjectSource.Type.COURSE:
                source, created = sources.update_or_create(
                    project=project, user=request.user, source_type=kind, course=course,
                    defaults={**pending, 'title': course.title},
                )
            elif kind == ProjectSource.Type.EXTERNAL_VIDEO:
                source, created = sources.update_or_create(
                    project=project, user=request.user, source_type=kind, external_key=data['external_key'],
                    defaults={
                        **pending, 'title': data['title'], 'source_url': data['url'],
                        'metadata': {key: data[key] for key in (
                            'platform', 'external_id', 'part', 'url', 'duration_seconds', 'segments',
                        )},
                    },
                )
            else:
                source = sources.create(
                    project=project, user=request.user, source_type=kind, title=data['title'],
                    source_url=data.get('source_url', ''), metadata={'text': data['content']},
                )
                created = True

        dispatch_project_source_processing(source)
        source.refresh_from_db()
        return Response(
            ProjectSourceSummarySerializer(source).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ProjectSourceDetailView(ProjectSourceView):
    def get(self, request, pk, source_id):
        source = get_object_or_404(self.sources(pk).prefetch_related('chunks'), pk=source_id)
        return Response(ProjectSourceDetailSerializer(source).data)

    def patch(self, request, pk, source_id):
        with transaction.atomic():
            source = get_object_or_404(self.sources(pk).select_for_update(), pk=source_id)
            payload = ProjectSourcePatchSerializer(data=request.data)
            payload.is_valid(raise_exception=True)
            data = payload.validated_data
            retry = data.pop('action', None) == 'retry'
            if retry:
                self.require_personal_space()
                data.update(status=ProjectSource.Status.PENDING, error_message='')
            if 'title' in data and source.source_type in (ProjectSource.Type.WEB_URL, ProjectSource.Type.EXTERNAL_VIDEO):
                data['metadata'] = {**source.metadata, 'title': data['title']}
            # updated_at identifies the active ingestion attempt until it publishes.
            fields = list(data)
            if retry or source.status != ProjectSource.Status.PROCESSING:
                fields.append('updated_at')
            for field, value in data.items():
                setattr(source, field, value)
            source.save(update_fields=fields)

        if retry:
            dispatch_project_source_processing(source)
            source.refresh_from_db()
        return Response(ProjectSourceSummarySerializer(source).data)

    def delete(self, request, pk, source_id):
        source = get_object_or_404(self.sources(pk), pk=source_id)
        source.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectSourceBatchSelectView(ProjectSourceView):
    def post(self, request, pk):
        sources = self.sources(pk)
        payload = ProjectSourceBatchSelectSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        affected = sources
        source_ids = data.get('source_ids')
        if source_ids is not None:
            affected = sources.filter(pk__in=source_ids)
        with transaction.atomic():
            updated = affected.update(
                is_selected=data['is_selected'],
                updated_at=Case(
                    When(status=ProjectSource.Status.PROCESSING, then=F('updated_at')), default=Now(),
                ),
            )
            if source_ids is not None and updated != len(set(source_ids)):
                raise Http404
            counts = sources.aggregate(
                total_count=Count('pk'),
                selected_count=Count('pk', filter=Q(is_selected=True)),
                ready_count=Count('pk', filter=Q(status=ProjectSource.Status.READY)),
            )
        return Response({'project_id': pk, **counts})


class ProjectSourceFileView(ProjectSourceView):
    def get(self, request, pk, source_id):
        source = get_object_or_404(self.sources(pk), pk=source_id)
        name = source.file.name
        if not name or not name.startswith(f'{WORKBENCH_SOURCE_PREFIX}{source.user_id}/'):
            raise Http404
        suffix = Path(name).suffix.lower()
        _, mime_type = UPLOAD_FORMATS.get(suffix, (None, 'application/octet-stream'))
        inline = mime_type == 'application/pdf' or mime_type.startswith(('video/', 'audio/'))
        try:
            file = source.file.open('rb')
        except FileNotFoundError as exc:
            raise Http404 from exc
        response = FileResponse(
            file, content_type=mime_type, as_attachment=not inline,
            filename=Path(name).name.removeprefix(f'{source.pk}_'),
        )
        response['X-Content-Type-Options'] = 'nosniff'
        response['Cache-Control'] = 'private, no-store'
        return response
