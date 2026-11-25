import json

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from ai_assistant.services.ulr_config import standalone_ulr
from quizzes.models import ContentPipelineTask
from quizzes.tasks import lock_question_pipeline, question_pipeline_may_have_partial_result


class Command(BaseCommand):
    help = 'Close a reviewed legacy bulk generation task while preserving the task and existing questions.'

    def add_arguments(self, parser):
        parser.add_argument('task_id', type=int)
        parser.add_argument('--legacy-workers-stopped', action='store_true',
                            help='Confirm that the old workers are stopped.')
        parser.add_argument('--review-reference', required=True, help='Reference to the completed review of partial results.')

    def handle(self, *args, **options):
        if not (standalone_ulr() and connection.vendor == 'postgresql' and options['legacy_workers_stopped']):
            raise CommandError('请停止旧工作进程，并在独立 ULR 的 PostgreSQL 环境结案。')
        reference = options['review_reference'].strip()
        if not reference:
            raise CommandError('请提供已完成结果核对的记录编号。')
        with transaction.atomic():
            task = ContentPipelineTask.objects.select_for_update().filter(
                pk=options['task_id'], task_type='ai_generate', payload__bulk_mode=True,
                payload__kind__isnull=True,
            ).first()
            if task is None or not question_pipeline_may_have_partial_result(task):
                raise CommandError('该任务不属于待核对的旧批量出题。')
            if task.status == 'cancelled' and task.payload.get('legacy_review_reference') == reference:
                closed = False
            elif task.status in ('running', 'failed') and lock_question_pipeline(task.pk):
                task.payload = {**task.payload, 'legacy_review_reference': reference, 'legacy_review_previous_status': task.status}
                task.status = 'cancelled'
                task.finished_at = task.finished_at or timezone.now()
                task.save(update_fields=['payload', 'status', 'finished_at', 'updated_at'])
                closed = True
            else:
                raise CommandError('该任务正在执行或已结案，请核对原记录。')
        self.stdout.write(json.dumps({'task_id': task.pk, 'status': task.status, 'closed': closed}))
