"""A course question keeps the transcript and video position selected for the question."""
import base64
import binascii
import io
import json
import math
from decimal import Decimal
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from django.conf import settings
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError

from courses.access import visible_courses
from courses.models import VideoTranscript
from ai_assistant.models import AIChatMessage


MAX_IMAGE_BYTES = 512 * 1024
MAX_VISUAL_BYTES = 1024 * 1024
MAX_IMAGE_EDGE = 1280
MAX_IMAGE_PIXELS = MAX_IMAGE_EDGE ** 2
JPEG_PREFIX = 'data:image/jpeg;base64,'


def _decode_visual_image(value):
    if not isinstance(value, str) or not value.startswith(JPEG_PREFIX):
        raise ValidationError('截图必须是 JPEG base64 data URL。')
    encoded = value[len(JPEG_PREFIX):]
    if len(encoded) > 4 * ((MAX_IMAGE_BYTES + 2) // 3):
        raise ValidationError('每张截图不能超过 512 KiB。')
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise ValidationError('截图 base64 无效。')
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValidationError('每张截图不能超过 512 KiB。')
    try:
        with Image.open(io.BytesIO(raw), formats=['JPEG']) as image:
            width, height = image.size
            if (image.format != 'JPEG' or max(width, height) > MAX_IMAGE_EDGE
                    or width * height > MAX_IMAGE_PIXELS):
                raise ValidationError('截图必须是 JPEG，最长边不能超过 1280。')
            image.verify()
        with Image.open(io.BytesIO(raw), formats=['JPEG']) as image:
            image.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ValidationError('截图不是有效的 JPEG 图片。')
    return raw


class VisualNumber(serializers.FloatField):
    def to_internal_value(self, data):
        if isinstance(data, bool) or not isinstance(data, (int, float)):
            self.fail('invalid')
        value = super().to_internal_value(data)
        if not math.isfinite(value):
            self.fail('invalid')
        return value


class CourseVisualFrame(serializers.Serializer):
    video_seconds = VisualNumber(min_value=0)
    image = serializers.CharField(trim_whitespace=False)

    def validate_image(self, value):
        _decode_visual_image(value)
        return value


class CourseVisualInput(serializers.Serializer):
    current = CourseVisualFrame()
    previous = CourseVisualFrame(required=False)

    def validate(self, value):
        current = value['current']['video_seconds']
        if 'previous' in value:
            elapsed = Decimal(str(current)) - Decimal(str(value['previous']['video_seconds']))
            if not 0 < elapsed <= 8:
                raise ValidationError('前一帧必须早于当前帧，且间隔最多 8 秒。')
        size = sum(len(base64.b64decode(value[key]['image'][len(JPEG_PREFIX):]))
                   for key in ('previous', 'current') if key in value)
        if size > MAX_VISUAL_BYTES:
            raise ValidationError('截图合计不能超过 1 MiB。')
        return value


class CourseQuestionInput(serializers.Serializer):
    course_id = serializers.IntegerField(min_value=1)
    video_seconds = serializers.FloatField(min_value=0)
    visual = CourseVisualInput(required=False)

    def validate_video_seconds(self, value):
        if not math.isfinite(value):
            raise serializers.ValidationError('视频时间必须是有效的秒数。')
        return value

    def validate(self, value):
        if ('visual' in value and
                abs(Decimal(str(value['visual']['current']['video_seconds']))
                    - Decimal(str(value['video_seconds']))) > Decimal('0.05')):
            raise ValidationError('当前截图时间必须与提问视频时间一致。')
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
    selected_start, selected_end = max(0, position - 30), position + 30
    segments = list(transcript.segments.filter(start_time__lt=selected_end,
        end_time__gt=selected_start).order_by('index').values('id', 'start_time', 'end_time', 'text'))
    if not segments:
        raise ValidationError('当前时间附近没有讲稿，请选择有字幕的位置提问。')
    context = {'course_id': course.pk, 'course_title': course.title,
            'video_seconds': position, 'revision': transcript.revision,
            'selected_start_seconds': selected_start, 'selected_end_seconds': selected_end,
            'start_seconds': segments[0]['start_time'], 'end_seconds': segments[-1]['end_time'],
            'segments': segments}
    if 'visual' in data.validated_data:
        context['visual'] = data.validated_data['visual']
    return context


def _visual_description(visual):
    return {key: {'video_seconds': visual[key]['video_seconds']}
            for key in ('previous', 'current') if key in visual}


def _course_prompt_parts():
    template = Path(settings.BASE_DIR) / 'prompts/ai_assistant/course_context_prompt.txt'
    return template.read_text().split('\n---\n')


def course_visual_messages(context) -> list[dict]:
    """Return at most two validated full screenshots, preserving their original bytes.

    The caller supplies these blocks as one user message's content. No model calls.
    """
    if not context or not context.get('visual'):
        return []
    # Validate snapshots loaded from message metadata as well as fresh requests.
    data = CourseQuestionInput(data=context)
    data.is_valid(raise_exception=True)
    visual = data.validated_data['visual']
    _, previous_prompt, current_prompt = _course_prompt_parts()
    blocks = []
    for key, prompt in (('previous', previous_prompt), ('current', current_prompt)):
        if key in visual:
            seconds = visual[key]['video_seconds']
            minutes, remaining = divmod(int(seconds), 60)
            citation = f'[画面{minutes:02d}:{remaining:02d}](/course/{data.validated_data["course_id"]}?t={seconds})'
            blocks.extend([
                {'type': 'text', 'text': prompt.format(video_seconds=seconds, citation=citation)},
                {'type': 'image_url', 'image_url': {'url': visual[key]['image']}},
            ])
    return blocks


def course_context_text(request, context):
    if not visible_courses(request).filter(pk=context['course_id']).exists():
        raise NotFound('课程不存在或不可访问。')
    template, _, _ = _course_prompt_parts()
    text_context = dict(context)
    if 'visual' in context:
        text_context['visual'] = _visual_description(context['visual'])
    return template.format(context=json.dumps(text_context, ensure_ascii=False))
