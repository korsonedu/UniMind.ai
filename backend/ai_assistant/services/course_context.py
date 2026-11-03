"""A course question keeps the transcript and video position captured at send time."""
import json
import math
from pathlib import Path

from django.conf import settings
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError

from courses.access import visible_courses
from courses.models import VideoTranscript
from ai_assistant.models import AIChatMessage


class CourseQuestionInput(serializers.Serializer):
    course_id = serializers.IntegerField(min_value=1)
    video_seconds = serializers.FloatField(min_value=0)

    def validate_video_seconds(self, value):
        if not math.isfinite(value):
            raise serializers.ValidationError('视频时间必须是有效的秒数。')
        return value


def prepare_course_context(request, bot, conversation_id):
    payload = request.data.get('course_context')
    previous = AIChatMessage.objects.filter(user=request.user, bot=bot,
        conversation_id=conversation_id, role='user').order_by('id').first()
    previous_course = previous.metadata.get('course_context') if previous else None
    if payload is None:
        if previous_course:
            raise ValidationError('课程提问需要附带本课时间戳。')
        return None
    if bot.bot_type != 'planner':
        raise ValidationError('课程提问仅支持小宇。')
    data = CourseQuestionInput(data=payload)
    data.is_valid(raise_exception=True)
    course = visible_courses(request).filter(pk=data.validated_data['course_id']).first()
    if course is None:
        raise NotFound('课程不存在或不可访问。')
    if previous and (not previous_course or previous_course['course_id'] != course.pk):
        raise ValidationError('请在本课程的独立对话中提问。')
    transcript = VideoTranscript.objects.filter(course=course, asr_status='completed').first()
    if transcript is None:
        raise ValidationError('本课程暂无可用讲稿，请完成转写后提问。')
    position = data.validated_data['video_seconds']
    segments = list(transcript.segments.filter(start_time__lt=position + 60,
        end_time__gt=max(0, position - 60)).order_by('index').values('id', 'start_time', 'end_time', 'text'))
    if not segments:
        raise ValidationError('当前时间附近没有讲稿，请选择有字幕的位置提问。')
    return {'course_id': course.pk, 'course_title': course.title,
            'video_seconds': position, 'revision': transcript.revision,
            'start_seconds': segments[0]['start_time'], 'end_seconds': segments[-1]['end_time'],
            'segments': segments}


def course_context_text(request, context):
    if not visible_courses(request).filter(pk=context['course_id']).exists():
        raise NotFound('课程不存在或不可访问。')
    template = Path(settings.BASE_DIR) / 'prompts/ai_assistant/course_context_prompt.txt'
    return template.read_text().format(context=json.dumps(context, ensure_ascii=False))
