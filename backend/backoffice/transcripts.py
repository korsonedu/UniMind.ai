from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers

from courses.models import Course, TranscriptSegment, VideoTranscript
from .common import managed, identity

MAX_SEGMENTS = 2000
MAX_SEGMENT_TEXT = 4000


def _course(data):
    queryset = managed(Course.objects.select_related('transcript', 'transcript__manual_edited_by', 'outline'))
    return get_object_or_404(queryset, pk=identity(data))


def _operator_name(user):
    if not user:
        return ''
    return user.nickname or user.username


def _segment_updates(transcript, raw):
    if not isinstance(raw, list):
        raise serializers.ValidationError('字幕分段格式无效。')
    if len(raw) > MAX_SEGMENTS:
        raise serializers.ValidationError(f'单次最多提交 {MAX_SEGMENTS} 条字幕。')
    updates = {}
    for item in raw:
        if not isinstance(item, dict):
            raise serializers.ValidationError('字幕分段格式无效。')
        segment_id = item.get('id')
        if isinstance(segment_id, bool) or not isinstance(segment_id, int) or segment_id < 1:
            raise serializers.ValidationError('字幕分段编号无效。')
        if segment_id in updates:
            raise serializers.ValidationError('字幕分段存在重复编号。')
        text = item.get('text')
        if not isinstance(text, str):
            raise serializers.ValidationError('字幕文本格式无效。')
        if len(text) > MAX_SEGMENT_TEXT:
            raise serializers.ValidationError(f'单条字幕不能超过 {MAX_SEGMENT_TEXT} 个字符。')
        updates[segment_id] = text
    owned = set(transcript.segments.filter(pk__in=updates).values_list('pk', flat=True))
    if owned != set(updates):
        raise serializers.ValidationError('字幕分段不属于当前课程。')
    return updates


def get_transcript(request, data):
    course = _course(data)
    transcript = getattr(course, 'transcript', None)
    outline = getattr(course, 'outline', None)
    result = {
        'id': course.pk,
        'title': course.title,
        'outline_status': outline.status if outline else 'not_available',
        'status': 'not_available',
        'provider': '',
        'error_message': '',
        'is_manually_edited': False,
        'manual_edited_at': None,
        'manual_edited_by_name': '',
        'revision': 0,
        'full_text': '',
        'segments': [],
    }
    if not transcript:
        return result
    result.update({
        'status': transcript.asr_status,
        'provider': transcript.asr_provider,
        'error_message': transcript.error_message,
        'is_manually_edited': transcript.is_manually_edited,
        'manual_edited_at': transcript.manual_edited_at,
        'manual_edited_by_name': _operator_name(transcript.manual_edited_by),
        'revision': transcript.revision,
        'full_text': transcript.full_text,
        'segments': list(transcript.segments.values('id', 'start_time', 'end_time', 'text', 'index').order_by('index')),
    })
    return result


def save_transcript(request, data):
    course = _course(data)
    revision = serializers.IntegerField(min_value=0).run_validation(data.get('revision'))
    transcript = VideoTranscript.objects.select_for_update().filter(course=course).first()
    if not transcript:
        raise serializers.ValidationError('该课程暂无字幕，无法保存。')
    if transcript.asr_status == 'processing':
        raise serializers.ValidationError('字幕正在重新识别，请稍后再保存。')
    if transcript.revision != revision:
        raise serializers.ValidationError('字幕已被其他人更新，请刷新后重试')

    updates = _segment_updates(transcript, data.get('segments'))
    segments = list(transcript.segments.order_by('index', 'id'))
    by_id = {segment.pk: segment for segment in segments}
    for segment_id, text in updates.items():
        by_id[segment_id].text = text
    if updates:
        TranscriptSegment.objects.bulk_update([by_id[segment_id] for segment_id in updates], ['text'])

    now = timezone.now()
    transcript.full_text = '\n'.join(segment.text for segment in segments)
    transcript.asr_status = 'completed'
    transcript.error_message = ''
    transcript.is_manually_edited = True
    transcript.manual_edited_at = now
    transcript.manual_edited_by = request.user
    transcript.revision += 1
    transcript.updated_at = now
    transcript.save(update_fields=['full_text', 'asr_status', 'error_message', 'is_manually_edited',
                                   'manual_edited_at', 'manual_edited_by', 'revision', 'updated_at'])
    return {'id': course.pk, 'updated': len(updates), 'revision': transcript.revision,
            'manual_edited_at': transcript.manual_edited_at}


def retranscribe_course(request, data):
    course = _course(data)

    def dispatch():
        from courses.services.task_dispatcher import dispatch_transcription
        dispatch_transcription(course.pk, force=True)

    transaction.on_commit(dispatch, robust=True)
    return {'id': course.pk, 'status': 'processing'}


def regenerate_outline(request, data):
    course = _course(data)

    def dispatch():
        from courses.services.task_dispatcher import dispatch_outline_generation
        dispatch_outline_generation(course.pk)

    transaction.on_commit(dispatch, robust=True)
    return {'id': course.pk, 'status': 'processing'}
