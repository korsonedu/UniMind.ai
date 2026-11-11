from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from users.permissions import IsMember
from .models import ConversationProject, ProjectLearningTask
from .services.learning_tasks import create_task, task_data


class ProjectLearningTaskListView(APIView):
    permission_classes = [IsMember]

    def get(self, request, pk):
        project = get_object_or_404(ConversationProject, pk=pk, user=request.user)
        return Response({'tasks': [task_data(task) for task in project.learning_tasks.select_related('exam', 'project').order_by('created_at', 'id')]})

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
        task = get_object_or_404(ProjectLearningTask.objects.select_related('project', 'exam'),
                                pk=task_id, project_id=pk, project__user=request.user)
        return Response(task_data(task))
