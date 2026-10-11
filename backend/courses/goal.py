from django.db import transaction
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsMember
from .models import Course, LearningGoal, VideoProgress
from .portal import visible_courses


class LearningGoalInput(serializers.Serializer):
    title = serializers.CharField(max_length=120)
    deadline = serializers.DateField()
    courses = serializers.PrimaryKeyRelatedField(queryset=Course.objects.none(), many=True, allow_empty=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['courses'].child_relation.queryset = visible_courses(self.context['request']).exclude(video_file='').exclude(video_file__isnull=True)


class LearningGoalView(APIView):
    permission_classes = [IsMember]

    def representation(self, goal, request):
        if goal is None:
            return None
        courses = goal.courses.filter(pk__in=visible_courses(request)).order_by('pk')
        ids = list(courses.values_list('pk', flat=True))
        completed = VideoProgress.objects.filter(user=request.user, course_id__in=ids, is_finished=True).count()
        return {'title': goal.title, 'deadline': goal.deadline.isoformat(), 'courses': ids,
                'completed_courses': completed, 'total_courses': len(ids),
                'progress_percent': round(completed / len(ids) * 100) if ids else 0}

    def get(self, request):
        goal = LearningGoal.objects.filter(user=request.user).first()
        return Response(self.representation(goal, request))

    @transaction.atomic
    def put(self, request):
        serializer = LearningGoalInput(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        goal, _ = LearningGoal.objects.update_or_create(user=request.user, defaults={'title': data['title'], 'deadline': data['deadline']})
        goal.courses.set(data['courses'])
        return Response(self.representation(goal, request))
