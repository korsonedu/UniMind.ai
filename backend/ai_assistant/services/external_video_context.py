"""Normalize the reference material supplied by external video companions."""
import base64
import json
import math
import unicodedata
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from .course_context import (
    CourseVisualFrame,
    JPEG_PREFIX,
    MAX_VISUAL_BYTES,
    VisualNumber,
    _decode_visual_image,
)


class FiniteSeconds(serializers.FloatField):
    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if isinstance(data, bool) or not math.isfinite(value):
            self.fail('invalid')
        return value


class ExternalVideoURL(serializers.CharField):
    def to_internal_value(self, data):
        if isinstance(data, str):
            data = ''.join(char for char in data if unicodedata.category(char) != 'Cc')
        return super().to_internal_value(data)


class IntegrationHookValue(serializers.Field):
    def to_internal_value(self, data):
        if isinstance(data, bool) or not isinstance(data, (int, str)):
            raise ValidationError('关联标识必须是整数、字符串或 null。')
        if isinstance(data, str) and len(data) > 128:
            raise ValidationError('关联标识不能超过 128 个字符。')
        return data

    def to_representation(self, value):
        return value


class ExternalVideoIntegrationHooks(serializers.Serializer):
    knowledge_tree_id = IntegrationHookValue(required=False, default=None, allow_null=True)
    knowledge_node_id = IntegrationHookValue(required=False, default=None, allow_null=True)
    memory_event_target = IntegrationHookValue(required=False, default=None, allow_null=True)


class ExternalVideoSegment(serializers.Serializer):
    start_time = FiniteSeconds(min_value=0)
    end_time = FiniteSeconds()
    text = serializers.CharField(allow_blank=True)

    def validate(self, value):
        value['end_time'] = max(value['start_time'], value['end_time'])
        value['text'] = value['text'].strip()[:1000]
        return value


class ExternalVideoPreviousFrame(serializers.Serializer):
    video_seconds = VisualNumber(min_value=0)
    # Delay image validation until we know whether this comparison frame is usable.
    image = serializers.JSONField(required=False, default=None, allow_null=True)


class ExternalVideoVisualInput(serializers.Serializer):
    current = CourseVisualFrame()
    previous = ExternalVideoPreviousFrame(required=False)

    def validate(self, value):
        previous = value.get('previous')
        if previous is None:
            return value
        elapsed = (Decimal(str(value['current']['video_seconds']))
                   - Decimal(str(previous['video_seconds'])))
        if not 0 < elapsed <= 15:
            value.pop('previous')
            return value
        previous_bytes = _decode_visual_image(previous['image'])
        current_bytes = base64.b64decode(value['current']['image'][len(JPEG_PREFIX):])
        if len(previous_bytes) + len(current_bytes) > MAX_VISUAL_BYTES:
            value.pop('previous')
        return value


class ExternalVideoInput(serializers.Serializer):
    platform = serializers.CharField(required=False, default='generic')
    external_id = serializers.CharField(max_length=128)
    part = serializers.IntegerField(required=False, default=1, allow_null=True)
    url = ExternalVideoURL(max_length=1000, allow_blank=True, required=False, default='')
    title = serializers.CharField(max_length=300, allow_blank=True, required=False, default='')
    video_seconds = FiniteSeconds(min_value=0)
    transcript_source = serializers.CharField(max_length=40, required=False, default='none')
    segments = ExternalVideoSegment(many=True, required=False, default=list)
    visual = ExternalVideoVisualInput(required=False, allow_null=True)
    integration_hooks = ExternalVideoIntegrationHooks(required=False, default=dict)

    def validate_platform(self, value):
        value = value.lower()
        if value not in ('bilibili', 'youtube', 'generic'):
            raise ValidationError('不支持的视频平台。')
        return value

    def validate_part(self, value):
        return max(1, value or 1)

    def validate(self, value):
        segments = [segment for segment in value['segments'] if segment['text']]
        if len(segments) > 80:
            segments = sorted(
                segments,
                key=lambda segment: abs(segment['start_time'] - value['video_seconds']),
            )[:80]
        value['segments'] = sorted(segments, key=lambda segment: segment['start_time'])
        hooks = value['integration_hooks']
        value['integration_hooks'] = {
            key: hooks.get(key)
            for key in ('knowledge_tree_id', 'knowledge_node_id', 'memory_event_target')
        }
        key = f"{value['platform']}:{value['external_id']}"
        if value['platform'] == 'bilibili' or value['part'] > 1:
            key += f":p{value['part']}"
        value['video_key'] = key
        return value


def prepare_external_video_context(request, bot, conversation_id):
    """Accept each turn independently, including text follow-ups and part switches."""
    payload = request.data.get('external_video_context')
    if payload is not None and request.data.get('course_context') is not None:
        raise ValidationError('不能同时传入站内课程与外部视频上下文。')
    if payload is None:
        return None
    if bot.bot_type != 'planner':
        raise ValidationError('视频伴学提问仅支持小宇。')
    data = ExternalVideoInput(data=payload)
    data.is_valid(raise_exception=True)
    return dict(data.validated_data)


def _prompt_parts():
    template = Path(settings.BASE_DIR) / 'prompts/ai_assistant/external_video_context_prompt.txt'
    return template.read_text(encoding='utf-8').split('\n---\n')


def _citation(label, seconds):
    minutes, remaining = divmod(int(seconds), 60)
    return f'[{label} {minutes:02d}:{remaining:02d}](#seek:{seconds})'


def external_video_context_text(context: dict) -> str:
    if not context:
        return ''
    template, _, _ = _prompt_parts()
    text_context = dict(context)
    text_context['segments'] = [
        {**segment, 'citation': _citation('讲稿', segment['start_time'])}
        for segment in context.get('segments', [])
    ]
    if context.get('visual'):
        text_context['visual'] = {
            key: {
                'video_seconds': frame['video_seconds'],
                'citation': _citation('画面', frame['video_seconds']),
            }
            for key, frame in context['visual'].items()
        }
    guidance = (
        '解释具体内容后，可复制对应片段的 citation 作为可点击讲稿引用，原始秒数保持不变。'
        if context.get('segments') else
        '当前时间点暂无字幕文本，请结合视频标题、上下文与画面截图直接解答，无需编造讲稿引用。'
    )
    return template.format(
        context=json.dumps(text_context, ensure_ascii=False),
        transcript_guidance=guidance,
    )


def external_video_visual_messages(context: dict) -> list[dict]:
    if not context or not context.get('visual'):
        return []
    data = ExternalVideoVisualInput(data=context['visual'])
    data.is_valid(raise_exception=True)
    _, previous_prompt, current_prompt = _prompt_parts()
    blocks = []
    for key, prompt in (('previous', previous_prompt), ('current', current_prompt)):
        frame = data.validated_data.get(key)
        if frame:
            seconds = frame['video_seconds']
            blocks.extend([
                {'type': 'text', 'text': prompt.format(
                    video_seconds=seconds, citation=_citation('画面', seconds))},
                {'type': 'image_url', 'image_url': {'url': frame['image']}},
            ])
    return blocks
