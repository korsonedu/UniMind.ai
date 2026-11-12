from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from users.permissions import IsMember
from .models import ConversationProject
from .services.project_learning import change_learning, learning_data
from .services.learning_resources import find_resources


class ProjectLearningView(APIView):
    permission_classes = [IsMember]

    def get(self, request, pk):
        project = get_object_or_404(ConversationProject, pk=pk, user=request.user)
        return Response(learning_data(project))

    def patch(self, request, pk):
        project = get_object_or_404(ConversationProject, pk=pk, user=request.user)
        if request.data.get('action') not in ('pause', 'resume', 'complete', 'schedule', 'accept', 'reject', 'reminders'):
            raise serializers.ValidationError('学习进展通过当前项目对话记录。')
        return Response(change_learning(project, request.data))

    def post(self, request, pk):
        project = get_object_or_404(ConversationProject, pk=pk, user=request.user)
        return Response(find_resources(project, request.data))


class ProjectLearningLibraryView(APIView):
    permission_classes = [IsMember]

    def get(self, request, pk):
        from .services.learning_library import library_data, validate
        get_object_or_404(ConversationProject, pk=pk, user=request.user)
        data = validate({'action': 'search', 'query': request.query_params.get('query', ''), 'domain': request.query_params.get('domain', '')})
        if request.query_params.get('resource_id'):
            from .models import LearningResource, LearningResourceVersion
            resource_id = serializers.IntegerField(min_value=1).run_validation(request.query_params['resource_id'])
            revision = serializers.IntegerField(min_value=1).run_validation(request.query_params.get('revision'))
            resource = get_object_or_404(LearningResource, pk=resource_id, user=request.user)
            version = get_object_or_404(LearningResourceVersion, resource=resource, revision=revision)
            return Response({'resource': version.snapshot, 'current_revision': resource.revision})
        return Response(library_data(request.user, data['query'], data['domain']))

    def post(self, request, pk):
        from .services.learning_library import resource_operation, strategy_operation
        project = get_object_or_404(ConversationProject, pk=pk, user=request.user)
        if request.data.get('kind') == 'resource':
            return Response(resource_operation(project, request.data))
        if request.data.get('kind') == 'strategy' and request.data.get('action') in ('save', 'retire', 'restore'):
            return Response(strategy_operation(project, request.data))
        raise serializers.ValidationError('方法试用与结果检查请在实际学习对话中完成。')


class ProjectLearningKnowledgeView(APIView):
    permission_classes = [IsMember]

    def get(self, request, pk):
        from .services.learning_knowledge import knowledge_operation
        project = get_object_or_404(ConversationProject, pk=pk, user=request.user)
        if request.query_params.get('version_id'):
            return Response(knowledge_operation(project, {'action': 'read', 'version_id': request.query_params['version_id']}))
        return Response(knowledge_operation(project, {'action': 'search', 'query': request.query_params.get('query', '')}))

    def post(self, request, pk):
        from .services.learning_knowledge import knowledge_operation
        project = get_object_or_404(ConversationProject, pk=pk, user=request.user)
        if request.data.get('action') not in ('save', 'prepare'):
            raise serializers.ValidationError('实际检查请在学习对话中完成。')
        return Response(knowledge_operation(project, request.data))
