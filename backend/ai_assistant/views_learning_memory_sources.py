from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ai_assistant.models import ConversationProject, LearningMemorySource
from ai_assistant.views_learning_memory import _enabled
from courses.access import visible_courses
from notes.models import Note


class SourceSelection(serializers.Serializer):
    kind = serializers.ChoiceField(choices=('course', 'note'))
    source_id = serializers.IntegerField(min_value=1)


class SourceSearch(serializers.Serializer):
    kind = serializers.ChoiceField(choices=('course', 'note'), default='course')
    q = serializers.CharField(max_length=120, allow_blank=True, default='')


def _sources(request, kind):
    if kind == 'course':
        return visible_courses(request)
    return Note.objects.filter(user=request.user, deleted_at__isnull=True)


class LearningMemorySourcesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        _enabled()
        project = get_object_or_404(ConversationProject, pk=project_id, user=request.user)
        search = SourceSearch(data=request.query_params)
        search.is_valid(raise_exception=True)
        kind = search.validated_data['kind']
        linked = list(project.memory_sources.order_by('pk').values('id', 'course_id', 'note_id'))
        course_titles = dict(_sources(request, 'course').filter(
            pk__in=[row['course_id'] for row in linked if row['course_id']],
        ).values_list('pk', 'title'))
        note_titles = dict(_sources(request, 'note').filter(
            pk__in=[row['note_id'] for row in linked if row['note_id']],
        ).values_list('pk', 'title'))
        attached = [{'id': row['id'], 'kind': 'course' if row['course_id'] is not None else 'note',
                     'title': course_titles.get(row['course_id']) if row['course_id'] is not None
                     else note_titles.get(row['note_id'])} for row in linked]
        options = _sources(request, kind).exclude(pk__in=[row[f'{kind}_id'] for row in linked if row[f'{kind}_id']])
        if query := search.validated_data['q']:
            options = options.filter(title__icontains=query)
        return Response({'attached': attached, 'available': list(options.order_by('-updated_at', '-pk').values('id', 'title')[:15])})

    def post(self, request, project_id):
        _enabled()
        project = get_object_or_404(ConversationProject, pk=project_id, user=request.user)
        selection = SourceSelection(data=request.data)
        selection.is_valid(raise_exception=True)
        kind = selection.validated_data['kind']
        source = get_object_or_404(_sources(request, kind), pk=selection.validated_data['source_id'])
        link, created = LearningMemorySource.objects.get_or_create(project=project, **{kind: source})
        return Response({'id': link.pk, 'kind': kind, 'title': source.title}, status=201 if created else 200)


class LearningMemorySourceView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, project_id, source_link_id):
        _enabled()
        get_object_or_404(LearningMemorySource, pk=source_link_id,
                          project_id=project_id, project__user=request.user).delete()
        return Response(status=204)
