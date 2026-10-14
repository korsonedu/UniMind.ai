import math
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.db.models import Count, Min, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from core.utils import apply_institution_filter
from users.permissions import IsMember
from .models import Course, LearningActivity, VideoProgress, WatchLater


class ProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = VideoProgress
        fields = ('course', 'last_position', 'duration', 'is_finished', 'updated_at')


class ProgressInput(serializers.Serializer):
    position = serializers.FloatField(min_value=0, required=False)
    duration = serializers.FloatField(min_value=0, required=False)
    is_finished = serializers.BooleanField(default=False, required=False)
    watched_seconds = serializers.FloatField(min_value=0, max_value=120, default=0, required=False)
    event_id = serializers.UUIDField(required=False)

    def validate(self, data):
        if any(not math.isfinite(data[key]) for key in ('position', 'duration', 'watched_seconds') if key in data):
            raise serializers.ValidationError('观看记录必须为有效数字。')
        if data['watched_seconds'] and not data.get('event_id'):
            raise serializers.ValidationError('学习活动需要唯一事件编号。')
        return data


def visible_courses(request):
    from .access import visible_courses as accessible
    return accessible(request)


class LearningProgressView(APIView):
    permission_classes = [IsMember]

    def get(self, request):
        records = VideoProgress.objects.filter(user=request.user, course__in=visible_courses(request)).order_by('-updated_at', '-pk')
        return Response(ProgressSerializer(records, many=True).data)


class LearningActivityView(APIView):
    permission_classes = [IsMember]

    def get(self, request):
        zone = ZoneInfo('Asia/Shanghai')
        today = timezone.localdate(timezone=zone)
        events = LearningActivity.objects.filter(user=request.user, course__in=visible_courses(request))
        aggregates = {'watched_seconds': Sum('watched_seconds'), 'completions': Count('pk', filter=Q(completed=True)), 'elo_earned': Sum('elo_earned')}
        days = events.annotate(date=TruncDate('created_at', tzinfo=zone)).filter(date__gte=today - timedelta(days=364)).values('date', 'course').annotate(**aggregates).order_by('date', 'course')
        totals = events.values('course').annotate(**aggregates).order_by('course')
        return Response({'today': today, 'tracking_started_at': events.aggregate(first=Min('created_at'))['first'], 'days': list(days), 'totals': list(totals)})


class WatchLaterListView(APIView):
    permission_classes = [IsMember]

    def get(self, request):
        return Response(list(WatchLater.objects.filter(user=request.user, course__in=visible_courses(request)).values('course', 'created_at')))


class WatchLaterDetailView(APIView):
    permission_classes = [IsMember]

    def put(self, request, pk):
        course = visible_courses(request).filter(pk=pk).first()
        if not course:
            return Response({'error': '课程不存在'}, status=404)
        if not course.video_file:
            return Response({'error': '课程暂无视频'}, status=400)
        item, _ = WatchLater.objects.get_or_create(user=request.user, course=course)
        return Response({'course': item.course_id, 'created_at': item.created_at})

    def delete(self, request, pk):
        if not visible_courses(request).filter(pk=pk).exists():
            return Response({'error': '课程不存在'}, status=404)
        WatchLater.objects.filter(user=request.user, course_id=pk).delete()
        return Response(status=204)
