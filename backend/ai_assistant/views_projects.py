from rest_framework import generics, serializers
from rest_framework.exceptions import PermissionDenied
from users.views import IsMember
from .models import AIChatMessage, Conversation, ConversationProject


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversationProject
        fields = ('id', 'name', 'instructions', 'created_at')
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
        return ConversationProject.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ProjectDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ProjectSerializer
    permission_classes = [IsMember]

    def get_queryset(self):
        return ConversationProject.objects.filter(user=self.request.user)


def save_new_conversation_project(request, bot, conversation_id):
    serializer = ProjectAssignmentSerializer(data={'project_id': request.data.get('project_id')}, context={'request': request})
    serializer.is_valid(raise_exception=True)
    if (Conversation.objects.filter(conversation_id=conversation_id).exclude(user=request.user).exists()
            or AIChatMessage.objects.filter(conversation_id=conversation_id).exclude(user=request.user).exists()):
        raise PermissionDenied('无权修改此对话')
    # 历史会话未生成元数据时仍属于未分类，归属只在首次创建时确定。
    project = None if AIChatMessage.objects.filter(user=request.user, conversation_id=conversation_id).exists() else serializer.validated_data['project_id']
    Conversation.objects.get_or_create(
        conversation_id=conversation_id, user=request.user,
        defaults={'bot': bot, 'project': project},
    )


def add_project_context(user, conversation_id, history):
    conversation = Conversation.objects.filter(
        user=user, conversation_id=conversation_id, project__user=user,
    ).select_related('project').first()
    if not conversation or not conversation.project.instructions.strip():
        return history
    project = conversation.project
    return [{'role': 'user', 'content': f'当前学习项目：{project.name}\n以下是我为本项目填写的学习目标、背景与要求，请在本次对话中参考：\n{project.instructions}'}] + history

