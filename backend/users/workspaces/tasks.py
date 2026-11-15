import logging
from celery import shared_task
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from users.models_workspace import WorkspaceCourse

logger = logging.getLogger(__name__)
SCHEMA = {'type': 'array', 'minItems': 1, 'maxItems': 30, 'items': {
    'type': 'object', 'properties': {
        'name': {'type': 'string', 'maxLength': 100},
        'children': {'type': 'array', 'minItems': 1, 'maxItems': 12, 'items': {'type': 'string', 'maxLength': 200}},
        'source_segment_ids': {'type': 'array', 'minItems': 1, 'items': {'type': 'integer'}},
    }, 'required': ['name', 'children', 'source_segment_ids'], 'additionalProperties': False,
}}


def dispatch_processing(link_id):
    try:
        process_course.delay(link_id)
    except Exception:
        logger.exception('Workspace processing dispatch failed: %s', link_id)
        WorkspaceCourse.objects.filter(pk=link_id).update(processing_status='failed', error_message='处理任务投递失败，请重试。')


@shared_task(bind=True, max_retries=2, default_retry_delay=30, soft_time_limit=5100, time_limit=5400)
def process_course(self, link_id):
    from ai_engine.ai_service import AIService
    from courses.services.ai_course_service import AICourseService
    from rest_framework import serializers
    with transaction.atomic():
        link = WorkspaceCourse.objects.select_for_update().select_related('course').get(pk=link_id)
        if link.processing_status == 'completed':
            return
        if link.processing_status == 'processing' and link.updated_at > timezone.now() - timedelta(seconds=5400):
            return
        link.processing_status = 'processing'
        link.error_message = ''
        link.save(update_fields=['processing_status', 'error_message', 'updated_at'])
        claim = link.updated_at
    try:
        transcript = getattr(link.course, 'transcript', None)
        if not transcript or transcript.asr_status != 'completed':
            transcript = AICourseService().transcribe_video(link.course)
        if transcript.asr_status != 'completed':
            raise ValueError('ASR not completed')
        segments = list(transcript.segments.order_by('index').values('id', 'start_time', 'text'))
        source_revision = transcript.revision
        text = '\n'.join(f"[{s['id']}|{s['start_time']}] {s['text']}" for s in segments)
        # Bound each model request; long courses are processed by contiguous transcript batches.
        batches, current = [], ''
        for line in text.splitlines():
            if len(current) + len(line) > 18000 and current:
                batches.append(current)
                current = ''
            current += line + '\n'
        if current:
            batches.append(current)
        topics = []
        valid_ids = {s['id'] for s in segments}
        for batch in batches:
            prompt = AIService.format_template(AIService.get_template('courses', 'workspace_knowledge_prompt.txt'), transcript_text=batch)
            result = AIService.structured_output(system_prompt='', user_prompt=prompt, schema=SCHEMA,
                tool_name='submit_course_knowledge', tool_description='提交基于讲稿的课程知识结构',
                temperature=0.2, max_tokens=4096, raise_on_error=True, operation='courses.workspace_knowledge')
            class Topic(serializers.Serializer):
                name = serializers.CharField(max_length=100)
                children = serializers.ListField(child=serializers.CharField(max_length=200), min_length=1, max_length=12)
                source_segment_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), min_length=1)
            parsed = Topic(data=result, many=True, allow_empty=False)
            parsed.is_valid(raise_exception=True)
            for topic in parsed.validated_data:
                if not set(topic['source_segment_ids']).issubset(valid_ids):
                    raise ValueError('Unknown source segment')
                topics.append(dict(topic))
        if not topics:
            raise ValueError('Empty knowledge structure')
        with transaction.atomic():
            locked = WorkspaceCourse.objects.select_for_update().get(pk=link_id)
            transcript.refresh_from_db()
            if locked.updated_at != claim:
                return
            if transcript.asr_status != 'completed' or transcript.revision != source_revision:
                raise ValueError('Transcript changed during knowledge construction')
            locked.knowledge = topics
            locked.transcript_revision = transcript.revision
            locked.processing_status = 'completed'
            locked.error_message = ''
            locked.save(update_fields=['knowledge', 'transcript_revision', 'processing_status', 'error_message', 'updated_at'])
    except Exception as exc:
        logger.exception('Workspace course processing failed: %s', link_id)
        WorkspaceCourse.objects.filter(pk=link_id, updated_at=claim).update(
            processing_status='failed', error_message='ASR 或知识结构构建失败，请重试。', updated_at=timezone.now())
        raise self.retry(exc=exc)


@shared_task
def recover_stalled_courses():
    WorkspaceCourse.objects.filter(processing_status__in=['pending', 'processing'],
        updated_at__lt=timezone.now() - timedelta(seconds=5500)).update(
            processing_status='failed', error_message='处理任务超时，请重试。', updated_at=timezone.now())
