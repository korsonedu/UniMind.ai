import json

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from ai_assistant.models import ProjectLearningEvent
from ai_assistant.services.ulr_config import standalone_ulr
from knowledge_builder.block_assessments import context, enqueue_preparation
from knowledge_builder.models import LearningBlock
from knowledge_builder.tasks import assessment_lock_key


class Command(BaseCommand):
    help = 'Resume a legacy block assessment on its original preparation after stopping the old workers.'

    def add_arguments(self, parser):
        parser.add_argument('event_id', type=int)
        parser.add_argument('--legacy-workers-stopped', action='store_true',
                            help='Confirm that the old workers are stopped.')

    def handle(self, *args, **options):
        if not (standalone_ulr() and connection.vendor == 'postgresql' and options['legacy_workers_stopped']):
            raise CommandError('请停止旧工作进程，并在独立 ULR 的 PostgreSQL 环境接管。')
        with transaction.atomic():
            event = ProjectLearningEvent.objects.select_related('project__user').select_for_update(of=('self',)).filter(
                pk=options['event_id'], kind='block_prepare').first()
            if event is None:
                raise CommandError('该检测准备记录不存在。')
            content = event.content
            status, pinned = content.get('status'), content.get('requires_ulr') is True
            queued = False
            if not (pinned and status in ('pending', 'completed')):
                legacy_running = status == 'running' and not pinned
                retryable = status == 'failed' and content.get('queue_retryable')
                if not (legacy_running or retryable):
                    raise CommandError('该检测当前无法接管。')
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_try_advisory_xact_lock(%s)', [assessment_lock_key(event.pk)])
                    if not cursor.fetchone()[0]:
                        raise CommandError('该检测仍有工作进程执行。')
                block = LearningBlock.objects.filter(pk=content.get('block_id')).first()
                try:
                    version = context(event.project.user, block, event.project_id)[2] if block else None
                except (Http404, ValidationError):
                    raise CommandError('原检测对应的学习安排已变化。') from None
                if (version is None or version.pk != content.get('version_id')
                        or content.get('mode') not in ('objective', 'challenge') or type(content.get('retest')) is not bool):
                    raise CommandError('原检测的学习安排或参数无法核对。')
                event.content = {'block_id': block.pk, 'version_id': version.pk, 'mode': content['mode'],
                    'retest': content['retest'], 'status': 'pending', 'requires_ulr': True, 'error': '',
                    'queued_at': timezone.now().timestamp()}
                event.save(update_fields=['content'])
                enqueue_preparation(event.pk, event.content)
                queued = True
        event.refresh_from_db(fields=['content'])
        if queued and event.content.get('queue_retryable'):
            raise CommandError('原检测暂未能启动，可按同一编号重试。')
        self.stdout.write(json.dumps({'event_id': event.pk, 'status': event.content['status'], 'queued': queued}))
