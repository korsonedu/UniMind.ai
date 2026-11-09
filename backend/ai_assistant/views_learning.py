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
        if request.data.get('action') not in ('pause', 'resume', 'complete', 'schedule', 'accept', 'reject'):
            raise serializers.ValidationError('学习进展通过当前项目对话记录。')
        return Response(change_learning(project, request.data))

    def post(self, request, pk):
        project = get_object_or_404(ConversationProject, pk=pk, user=request.user)
        return Response(find_resources(project, request.data))
