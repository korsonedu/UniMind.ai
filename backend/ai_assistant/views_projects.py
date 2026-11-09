from rest_framework import generics, serializers
from rest_framework.exceptions import NotFound, PermissionDenied
from users.views import IsMember
from .models import AIChatMessage, Conversation, ConversationProject


class ProjectSerializer(serializers.ModelSerializer):
    learning_summary = serializers.SerializerMethodField()

    def get_learning_summary(self, project):
        from .models import ProjectLearning
        try:
            state = project.learning
        except ProjectLearning.DoesNotExist:
            return None
        return {'status': state.status, 'next_action': state.next_action,
                'conversation_id': str(state.last_conversation.conversation_id) if state.last_conversation else None}

    class Meta:
        model = ConversationProject
        fields = ('id', 'name', 'instructions', 'created_at', 'learning_summary')
        read_only_fields = ('id', 'created_at')


class ProjectAssignmentSerializer(serializers.Serializer):
    project_id = serializers.PrimaryKeyRelatedField(queryset=ConversationProject.objects.none(), allow_null=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['project_id'].queryset = ConversationProject.objects.filter(user=self.context['request'].user)


class ProjectListCreateView(generics.ListCreateAPIView):
    serializer_class = ProjectSerializer
    permission_classes = [IsMember]

    def get_queryset(self):
        return ConversationProject.objects.filter(user=self.request.user).select_related('learning__last_conversation')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ProjectDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ProjectSerializer
    permission_classes = [IsMember]

    def get_queryset(self):
        return ConversationProject.objects.filter(user=self.request.user).select_related('learning__last_conversation')


class ConversationUpdateSerializer(serializers.ModelSerializer):
    title = serializers.CharField(max_length=120, required=False)
    project_id = serializers.PrimaryKeyRelatedField(source='project', queryset=ConversationProject.objects.none(), allow_null=True, required=False)

    class Meta:
        model = Conversation
        fields = ('conversation_id', 'title', 'is_pinned', 'project_id')
        read_only_fields = ('conversation_id',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['project_id'].queryset = ConversationProject.objects.filter(user=self.context['request'].user)


class ConversationDetailView(generics.UpdateAPIView):
    serializer_class = ConversationUpdateSerializer
    permission_classes = [IsMember]
    http_method_names = ['patch', 'options']

    def get_object(self):
        conversation_id = self.kwargs['conversation_id']
        conversation = Conversation.objects.filter(user=self.request.user, conversation_id=conversation_id).first()
        if conversation:
            return conversation
        message = AIChatMessage.objects.filter(user=self.request.user, conversation_id=conversation_id, bot__isnull=False).first()
        if not message or Conversation.objects.filter(conversation_id=conversation_id).exists():
            raise NotFound()
        conversation, _ = Conversation.objects.get_or_create(
            user=self.request.user, conversation_id=conversation_id, defaults={'bot_id': message.bot_id},
        )
        return conversation


def save_new_conversation_project(request, bot, conversation_id):
    serializer = ProjectAssignmentSerializer(data={'project_id': request.data.get('project_id')}, context={'request': request})
    serializer.is_valid(raise_exception=True)
    if (Conversation.objects.filter(conversation_id=conversation_id).exclude(user=request.user).exists()
            or AIChatMessage.objects.filter(conversation_id=conversation_id).exclude(user=request.user).exists()):
        raise PermissionDenied('无权修改此对话')
    # 历史会话未生成元数据时仍属于未分类，归属只在首次创建时确定。
    project = None if AIChatMessage.objects.filter(user=request.user, conversation_id=conversation_id).exists() else serializer.validated_data['project_id']
    conversation, _ = Conversation.objects.get_or_create(
        conversation_id=conversation_id, user=request.user,
        defaults={'bot': bot, 'project': project},
    )
    if conversation.project_id:
        from .models import ProjectLearning
        state, _ = ProjectLearning.objects.get_or_create(project=conversation.project)
        state.last_conversation = conversation
        state.followup_at = None
        state.save(update_fields=['last_conversation', 'followup_at', 'updated_at'])


def add_project_context(user, conversation_id, history):
    conversation = Conversation.objects.filter(
        user=user, conversation_id=conversation_id, project__user=user,
    ).select_related('project').first()
    if not conversation:
        return history
    from .services.project_learning import project_context
    return [{'role': 'user', 'content': project_context(user, conversation_id)}] + history
