import json

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from ai_assistant.models import ProjectLearning, ProjectLearningEvent
from ai_assistant.services.learning_knowledge import owned_version
from ai_assistant.services.ulr_config import standalone_ulr
from knowledge_builder.block_assessments import context, enqueue_preparation
from knowledge_builder.models import LearningBlock
from knowledge_builder.tasks import assessment_lock_key


SUPERSEDED = 'superseded_learning_version'


class Command(BaseCommand):
    help = 'Recover a legacy block assessment on its original preparation after stopping the old workers.'

    def add_arguments(self, parser):
        parser.add_argument('event_id', type=int)
        parser.add_argument('--legacy-workers-stopped', action='store_true',
                            help='Confirm that the old workers are stopped.')

    def handle(self, *args, **options):
        if not (standalone_ulr() and connection.vendor == 'postgresql' and options['legacy_workers_stopped']):
            raise CommandError('请停止旧工作进程，并在独立 ULR 的 PostgreSQL 环境接管。')
        with transaction.atomic():
            events = ProjectLearningEvent.objects.filter(pk=options['event_id'], kind='block_prepare')
            project_id = events.values_list('project_id', flat=True).first()
            # The student endpoint locks the plan before writing preparations.
            state = ProjectLearning.objects.select_for_update().filter(project_id=project_id).first() if project_id else None
            event = events.select_related('project__user').select_for_update(of=('self',)).first()
            if event is None:
                raise CommandError('该检测准备记录不存在。')
            if state is None or event.project_id != project_id:
                raise CommandError('原检测对应的学习安排无法核对。')
            content = event.content
            status, pinned = content.get('status'), content.get('requires_ulr') is True
            queued = False
            settled = status == 'failed' and content.get('error_code') == SUPERSEDED
            if not (settled or pinned and status in ('pending', 'completed')):
                legacy_running = status == 'running' and not pinned
                retryable = status == 'failed' and content.get('queue_retryable')
                if not (legacy_running or retryable):
                    raise CommandError('该检测当前无法接管。')
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_try_advisory_xact_lock(%s)', [assessment_lock_key(event.pk)])
                    if not cursor.fetchone()[0]:
                        raise CommandError('该检测仍有工作进程执行。')
                block_id, version_id = content.get('block_id'), content.get('version_id')
                if (type(block_id) is not int or type(version_id) is not int or
                        content.get('mode') not in ('objective', 'challenge') or type(content.get('retest')) is not bool):
                    raise CommandError('原检测的学习安排或参数无法核对。')
                block = LearningBlock.objects.filter(pk=block_id).first()
                active_version = (state.plan.get('knowledge_path') or {}).get('version_id')
                if block is None or state.status != 'active' or type(active_version) is not int:
                    raise CommandError('原检测对应的学习安排无法核对。')
                try:
                    if active_version == version_id:
                        context(event.project.user, block, event.project_id)
                        event.content = {'block_id': block_id, 'version_id': version_id, 'mode': content['mode'],
                            'retest': content['retest'], 'status': 'pending', 'requires_ulr': True, 'error': '',
                            'queued_at': timezone.now().timestamp()}
                        queued = True
                    else:
                        original = owned_version(event.project, version_id).snapshot
                        owned_version(event.project, active_version)
                        if (original.get('builder', {}).get('build_id') != str(block.build_id)
                                or not any(block_id in node.get('builder_block_ids', []) for node in original.get('nodes', ()))):
                            raise ValidationError('原检测与原知识版本不一致。')
                        event.content = {**content, 'status': 'failed', 'queue_retryable': False, 'error_code': SUPERSEDED,
                                         'error': '原检测所属的学习版本已被替换。'}
                except (Http404, ValidationError):
                    raise CommandError('原检测对应的学习安排无法核对。') from None
                event.save(update_fields=['content'])
                if queued:
                    enqueue_preparation(event.pk, event.content)
        event.refresh_from_db(fields=['content'])
        if queued and event.content.get('queue_retryable'):
            raise CommandError('原检测暂未能启动，可按同一编号重试。')
        receipt = {'event_id': event.pk, 'status': event.content['status'], 'queued': queued}
        if event.content.get('error_code') == SUPERSEDED:
            receipt['error_code'] = SUPERSEDED
        self.stdout.write(json.dumps(receipt))
