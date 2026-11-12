"""Explicit operator-only shadow run; outputs private, project-scoped results."""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from rest_framework.exceptions import APIException
from ai_assistant.models import ConversationProject
from ai_assistant.services.teaching_shadow import run_shadow


class Command(BaseCommand):
    help = 'Compare G/E shadow artifacts for one project. Never activates or promotes a mechanism.'

    def add_arguments(self, parser):
        parser.add_argument('--project', type=int, required=True)
        parser.add_argument('--kind', choices=['G', 'E'], required=True)
        parser.add_argument('--packet', required=True)
        parser.add_argument('--output', required=True)
        parser.add_argument('--live-model', action='store_true', help='Makes bounded real model calls; default accepts synthetic fixtures only.')

    def handle(self, *args, **options):
        project = ConversationProject.objects.select_related('user').filter(pk=options['project']).first()
        if not project:
            raise CommandError('Project unavailable.')
        try:
            source = Path(options['packet'])
            if source.stat().st_size > 256000:
                raise CommandError('Packet exceeds 256KB.')
            target = Path(options['output'])
            if target.exists():
                raise CommandError('Output already exists; choose a new private report path.')
            packet = json.loads(source.read_text())
            report = run_shadow(project, options['kind'], packet, live_model=options['live_model'])
            # Private report can contain owner source-derived content. Never overwrite arbitrary files.
            with target.open('x', encoding='utf-8') as output:
                target.chmod(0o600)
                json.dump(report, output, ensure_ascii=False, indent=2, allow_nan=False)
                output.write('\n')
        except (OSError, ValueError, APIException) as exc:
            raise CommandError(f'Shadow run rejected: {type(exc).__name__}') from exc
        self.stdout.write(json.dumps({'run_id': report['run_id'], 'status': report['status'], 'eligible': False,
                                     'output': str(target)}, ensure_ascii=False))
