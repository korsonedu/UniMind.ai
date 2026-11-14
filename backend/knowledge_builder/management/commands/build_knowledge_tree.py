import json

from django.core.management.base import BaseCommand

from knowledge_builder.archetypes import PROFILES
from knowledge_builder.pipeline import create_build, run_build
from knowledge_builder.views import enqueue_build


class Command(BaseCommand):
    help = 'Build a complete two-layer knowledge tree from a subject.'

    def add_arguments(self, parser):
        parser.add_argument('subject')
        parser.add_argument('--archetype', choices=('auto', *PROFILES), default='auto')
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument('--sync', action='store_true')
        mode.add_argument('--async', dest='asynchronous', action='store_true')

    def handle(self, *args, **options):
        build = create_build(options['subject'], archetype_override=options['archetype'])
        self.stdout.write(f'build.id={build.pk}')
        if options['asynchronous']:
            enqueue_build(build)
            self.stdout.write('status=PENDING')
            return
        build = run_build(build.pk, progress=self.stdout.write)
        self.stdout.write(f'status={build.status}')
        self.stdout.write(json.dumps(build.stats, ensure_ascii=False, allow_nan=False))
