"""Explicit operator-only shadow run; outputs private, project-scoped results."""
import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import APIException
from ai_assistant.models import ConversationProject
from ai_assistant.services.rsi_dataset import DECISION_POINTS, build_sdtm_shadow_packet
from ai_assistant.services.teaching_shadow import run_s_offline_replay, run_shadow


def _read_json(source):
    path = Path(source)
    if path.stat().st_size > 256000:
        raise CommandError('Packet exceeds 256KB.')
    return json.loads(path.read_text())


class Command(BaseCommand):
    help = 'Run project-scoped G/E shadow comparisons or offline S policy replay.'

    def add_arguments(self, parser):
        parser.add_argument('--project', type=int, required=True)
        parser.add_argument('--kind', choices=['G', 'E', 'S'], required=True)
        source = parser.add_mutually_exclusive_group(required=True)
        source.add_argument('--packet')
        source.add_argument('--from-sdtm', action='store_true', help='Runs a live G/E temporal holdout or an offline S replay.')
        parser.add_argument('--cutoff', help='ISO-8601 cutoff with timezone. Required for SDTM G/E.')
        parser.add_argument('--baseline-instruction', help='Required for SDTM G/E.')
        parser.add_argument('--decision-point', choices=DECISION_POINTS)
        parser.add_argument('--target-policy', help='S target policy as JSON or the path to a JSON file.')
        parser.add_argument('--output', required=True)
        parser.add_argument('--live-model', action='store_true', help='Makes bounded real model calls; default accepts synthetic fixtures only.')

    def handle(self, *args, **options):
        project = ConversationProject.objects.select_related('user').filter(pk=options['project']).first()
        if not project:
            raise CommandError('Project unavailable.')
        try:
            target = Path(options['output'])
            if target.exists() or target.is_symlink():
                raise CommandError('Output already exists; choose a new private report path.')
            kind = options['kind']
            cutoff = None
            if options['from_sdtm'] and options['cutoff'] is not None:
                cutoff = parse_datetime(options['cutoff'])
                if cutoff is None:
                    raise CommandError('Cutoff must be an ISO-8601 datetime with timezone.')
            if kind == 'S':
                if not options['from_sdtm'] or not options['decision_point'] or not options['target_policy'] or options['live_model']:
                    raise CommandError('Use --from-sdtm, --decision-point and --target-policy for offline S replay.')
                try:
                    policy = json.loads(options['target_policy'])
                except json.JSONDecodeError:
                    policy = _read_json(options['target_policy'])
                report = run_s_offline_replay(project, decision_point=options['decision_point'], target_policy=policy, cutoff_at=cutoff)
            elif options['from_sdtm']:
                if cutoff is None or not options['baseline_instruction']:
                    raise CommandError('SDTM G/E requires --cutoff and --baseline-instruction.')
                packet = build_sdtm_shadow_packet(project, kind=kind, cutoff_at=cutoff,
                                                   baseline_instruction=options['baseline_instruction'])
                report = run_shadow(project, kind, packet, live_model=True)
            else:
                report = run_shadow(project, kind, _read_json(options['packet']), live_model=options['live_model'])
            # Private report can contain owner source-derived content. Never overwrite arbitrary files.
            with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as output:
                os.fchmod(output.fileno(), 0o600)
                json.dump(report, output, ensure_ascii=False, indent=2, allow_nan=False)
                output.write('\n')
        except (OSError, ValueError, APIException) as exc:
            raise CommandError(f'Shadow run rejected: {type(exc).__name__}') from exc
        self.stdout.write(json.dumps({'run_id': report['run_id'], 'status': report['status'], 'eligible': False,
                                     'output': str(target)}, ensure_ascii=False))
