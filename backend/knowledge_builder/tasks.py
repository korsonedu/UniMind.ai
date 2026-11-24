from hashlib import blake2b

from celery import shared_task
from django.db import connection
from django.utils import timezone

from ai_assistant.services.ulr_config import standalone_ulr
from ai_engine.observability import observe_background
from .pipeline import run_build


@shared_task(bind=True, max_retries=0)
def build_knowledge_tree(self, build_id):
    build = run_build(build_id, redelivered=bool((self.request.delivery_info or {}).get('redelivered')))
    return str(build.pk)


@shared_task(bind=True, max_retries=0, soft_time_limit=600, time_limit=630,
             acks_late=True, reject_on_worker_lost=True)
def prepare_block_assessment(self, event_id):
    if connection.vendor != 'postgresql':
        return _prepare_block_assessment(event_id)
    digest = blake2b(str(event_id).encode(), digest_size=8, person=b'kb-assessment').digest()
    key = int.from_bytes(digest, 'big', signed=True)
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_try_advisory_lock(%s)', [key])
        if not cursor.fetchone()[0]:
            return
    try:
        return _prepare_block_assessment(event_id, resume_running=bool((self.request.delivery_info or {}).get('redelivered')))
    finally:
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_unlock(%s)', [key])


def _prepare_block_assessment(event_id, *, resume_running=False):
    import logging
    from ai_assistant.models import ProjectLearningEvent
    from .models import LearningBlock
    from .block_assessments import generate_assessment
    statuses = ('pending', 'running') if resume_running else ('pending',)
    events = ProjectLearningEvent.objects.filter(pk=event_id, kind='block_prepare')
    event = events.filter(content__status__in=statuses).select_related('project__user').first()
    if event is None:
        return
    native = standalone_ulr()
    current = events.filter(content=event.content)
    if event.content.get('requires_ulr') and not native:
        current.update(content={**event.content, 'status': 'failed', 'queue_retryable': True,
            'error': '本轮出题需要 ULR，请恢复工作进程配置后重试。'})
        return
    claimed = {**event.content, 'status': 'running', 'started_at': int(timezone.now().timestamp()), 'requires_ulr': native}
    if not current.update(content=claimed):
        return
    event.content = claimed
    try:
        block = LearningBlock.objects.get(pk=event.content['block_id'])
        with observe_background('ulr' if native else 'legacy', f'assessment:{event.pk}'):
            generate_assessment(event, block)
    except Exception:
        logging.getLogger(__name__).exception('Block task preparation failed: event=%s', event_id)
        events.filter(content=claimed).update(content={
            **event.content, 'status': 'failed', 'error': '暂未能准备有效的新题，未创建本轮任务或证据。请稍后重试。'})
