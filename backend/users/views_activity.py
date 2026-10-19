from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from core.utils import apply_institution_filter
from .feature_access import has_learning_feature
from .models import LearningSession
from .permissions import IsMember


class LearningSessionInput(serializers.Serializer):
    session_id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=['video', 'practice'])
    course_id = serializers.IntegerField(min_value=1, required=False, allow_null=True, default=None)
    question_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), max_length=50, default=list)
    started_at = serializers.DateTimeField()
    ended_at = serializers.DateTimeField()
    active_seconds = serializers.IntegerField(min_value=1)
    focused_seconds = serializers.IntegerField(min_value=0)

    def validate(self, data):
        span = (data['ended_at'] - data['started_at']).total_seconds()
        if (span < 0 or data['active_seconds'] > span + 1
                or data['focused_seconds'] > data['active_seconds']
                or data['ended_at'] > timezone.now() + timedelta(seconds=30)):
            raise serializers.ValidationError('学习起止时间或时长无效。')
        if data['kind'] == 'video':
            if not data['course_id'] or data['question_ids']:
                raise serializers.ValidationError('听课记录需要课程编号。')
        elif data['course_id'] or not data['question_ids'] or len(set(data['question_ids'])) != len(data['question_ids']):
            raise serializers.ValidationError('练习记录需要本轮题目编号。')
        return data


class LearningSessionView(APIView):
    permission_classes = [IsMember]

    def post(self, request):
        payload = LearningSessionInput(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        feature = 'course.video' if data['kind'] == 'video' else 'quiz.exam'
        if not has_learning_feature(request.user, feature):
            return Response({'detail': '该功能尚未向你的账号开放。'}, status=403)
        if data['kind'] == 'video':
            from courses.access import visible_courses
            if not visible_courses(request).filter(pk=data['course_id'], video_file__gt='').exists():
                return Response({'detail': '课程不存在。'}, status=404)
        else:
            from quizzes.models import Question
            questions = apply_institution_filter(Question.objects.filter(pk__in=data['question_ids']), request.user, request)
            if questions.count() != len(data['question_ids']):
                return Response({'detail': '题目不存在。'}, status=404)
        session_id = data.pop('session_id')
        with transaction.atomic():
            session, created = LearningSession.objects.select_for_update().get_or_create(
                user=request.user, session_id=session_id, defaults=data)
            if not created:
                if any(getattr(session, key) != data[key] for key in ('kind', 'course_id', 'question_ids', 'started_at')):
                    return Response({'detail': '学习记录编号已用于其他学习内容。'}, status=400)
                # 累计快照使重试和乱序请求不会重复计时或覆盖较新的记录。
                if (data['ended_at'] >= session.ended_at and data['active_seconds'] >= session.active_seconds
                        and data['focused_seconds'] >= session.focused_seconds):
                    for key in ('ended_at', 'active_seconds', 'focused_seconds'):
                        setattr(session, key, data[key])
                    session.save(update_fields=['ended_at', 'active_seconds', 'focused_seconds'])
        return Response({'session_id': str(session_id)}, status=201 if created else 200)
