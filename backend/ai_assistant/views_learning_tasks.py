from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from users.permissions import IsMember
from .models import ConversationProject
from .services.learning_tasks import available_project_tasks, create_task, task_data


class ProjectLearningTaskListView(APIView):
    permission_classes = [IsMember]

    def get(self, request, pk):
        project = get_object_or_404(ConversationProject, pk=pk, user=request.user)
        tasks = available_project_tasks(project).select_related('exam', 'project').order_by('created_at', 'id')
        return Response({'tasks': [task_data(task) for task in tasks]})

    def post(self, request, pk):
        project = get_object_or_404(ConversationProject, pk=pk, user=request.user)
        if request.data.get('action') == 'sample':
            from .services.function_sample import setup_sample
            return Response(setup_sample(project), status=201)
        if request.data.get('action', 'create') != 'create':
            raise ValidationError('未知任务操作。')
        return Response(task_data(create_task(project, request.data)), status=201)


class ProjectLearningTaskDetailView(APIView):
    permission_classes = [IsMember]

    def get(self, request, pk, task_id):
        project = get_object_or_404(ConversationProject, pk=pk, user=request.user)
        task = get_object_or_404(available_project_tasks(project).select_related('project', 'exam'), pk=task_id)
        return Response(task_data(task))
