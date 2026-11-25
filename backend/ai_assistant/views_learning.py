from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.conf import settings
from django.shortcuts import get_object_or_404
from users.permissions import IsMember
from .models import ConversationProject, Conversation
from .services.project_learning import change_learning, learning_data
from .services.learning_resources import find_resources
from .services.language import request_language
from .services.teaching_sidecar import PRESENTATION_SURFACES, record_exposure_presentation


class LearningExposurePresentSerializer(serializers.Serializer):
    message_id = serializers.IntegerField(min_value=1, max_value=2**63 - 1)
    surface = serializers.ChoiceField(choices=PRESENTATION_SURFACES, default='chat_card')
    card_type = serializers.CharField(max_length=64, allow_blank=True, trim_whitespace=False, default='')

    def validate_card_type(self, value):
        if not isinstance(self.initial_data.get('card_type', ''), str):
            raise serializers.ValidationError('卡片类型须为字符串。')
        return value


class LearningExposurePresentView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LearningExposurePresentSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(record_exposure_presentation(request.user, **serializer.validated_data))


class ProjectLearningView(APIView):
    permission_classes = [IsMember]

    def get(self, request, pk):
        project = get_object_or_404(ConversationProject, pk=pk, user=request.user)
        if request.query_params.get('conversation_id'):
            conversation_id = serializers.UUIDField().run_validation(request.query_params['conversation_id'])
            if Conversation.objects.filter(conversation_id=conversation_id).exclude(user=request.user, project=project).exists():
                from django.http import Http404
                raise Http404
        data = learning_data(project, language=request_language(request))
        if settings.UNIMIND_LEARNING_MEMORY_CONNECTORS:
            from .models import LearningKnowledgeVersion
            from .services.learning_recall import last_viewed_node
            version = LearningKnowledgeVersion.objects.filter(
                pk=(data['plan'].get('knowledge_path') or {}).get('version_id'), knowledge_map__user=request.user).first()
            data.update(memory_connectors=True, last_viewed_node=last_viewed_node(project, version))
        return Response(data)

    def patch(self, request, pk):
        project = get_object_or_404(ConversationProject, pk=pk, user=request.user)
        if request.data.get('action') not in ('pause', 'resume', 'complete', 'schedule', 'accept', 'reject', 'reminders', 'focus'):
            raise serializers.ValidationError('学习进展通过当前项目对话记录。')
        return Response(change_learning(project, request.data, language=request_language(request)))

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
        if request.data.get('action') == 'remember_view' and settings.UNIMIND_LEARNING_MEMORY_CONNECTORS:
            from .services.learning_recall import remember_view
            version_id = serializers.IntegerField(min_value=1).run_validation(request.data.get('version_id'))
            node_id = serializers.CharField(max_length=60).run_validation(request.data.get('node_id'))
            remember_view(project, version_id, node_id)
            return Response(status=204)
        if request.data.get('action') not in ('save', 'prepare', 'from_build'):
            raise serializers.ValidationError('实际检查请在学习对话中完成。')
        return Response(knowledge_operation(project, request.data))
