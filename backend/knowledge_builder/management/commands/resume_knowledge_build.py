from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from ai_assistant.services.ulr_config import standalone_ulr
from knowledge_builder.build_state import can_resume_build, lock_build_for_resume, reset_for_queue
from knowledge_builder.models import KnowledgeTreeBuild
from knowledge_builder.views import enqueue_build


class Command(BaseCommand):
    help = 'Requeue a knowledge build in ULR, including builds created without an owner.'

    def add_arguments(self, parser):
        parser.add_argument('build_id', type=UUID)
        parser.add_argument('--legacy-workers-stopped', action='store_true',
                            help='Confirm that the old workers are stopped before adopting an interrupted legacy build.')

    def handle(self, *args, **options):
        if not standalone_ulr():
            raise CommandError('需要在 ULR 环境运行。')
        with transaction.atomic():
            build = KnowledgeTreeBuild.objects.filter(pk=options['build_id']).defer('checkpoint').first()
            if not build:
                raise CommandError('该构建不存在。')
            stopped_legacy_build = (build.status == KnowledgeTreeBuild.Status.RUNNING and not build.requires_ulr
                                    and options['legacy_workers_stopped'] and connection.vendor == 'postgresql')
            if not ((stopped_legacy_build or can_resume_build(build))
                    and lock_build_for_resume(build) and reset_for_queue(build)):
                raise CommandError('该构建当前无法继续。')
        enqueue_build(build)
        self.stdout.write(f'build.id={build.pk}')
