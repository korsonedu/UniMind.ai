"""Privately report a bounded, paired formal-question replay."""
import json
import os
from pathlib import Path
from types import SimpleNamespace

from django.core.management.base import BaseCommand, CommandError
from rest_framework.exceptions import APIException

from ai_assistant.services.prism_feedback import _reviewer
from ai_assistant.services.prism_replay import replay
from users.models import User


class Command(BaseCommand):
    help = 'Replay 1-6 fixed objective bank questions. Default prepares only; --live-model makes bounded paid calls.'

    def add_arguments(self, parser):
        parser.add_argument('--student', type=int, required=True)
        parser.add_argument('--reviewer', required=True)
        parser.add_argument('--questions', type=int, nargs='+', required=True)
        parser.add_argument('--output', required=True)
        parser.add_argument('--live-model', action='store_true')
        parser.add_argument('--data-origin', choices=['local_historical_unverified', 'observational'],
                            default='local_historical_unverified')

    def handle(self, *args, **options):
        try:
            target = Path(options['output'])
            if target.exists():
                raise ValueError('Output exists; select a new private report path.')
            user = User.objects.get(pk=options['student'], is_active=True)
            reviewer = User.objects.get(username=options['reviewer'], is_active=True)
            _reviewer(SimpleNamespace(owner_id=user.pk), reviewer)
            # Reserve a private file before any paid calls; never overwrite existing artifacts.
            with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as output:
                try:
                    report = replay(user, options['questions'], live_model=options['live_model'], data_origin=options['data_origin'])
                except Exception as exc:
                    json.dump({'status': 'rejected', 'error_type': type(exc).__name__}, output)
                    raise
                json.dump(report, output, ensure_ascii=False, indent=2, allow_nan=False)
                output.write('\n')
        except (OSError, ValueError, TypeError, KeyError, APIException, User.DoesNotExist) as exc:
            raise CommandError(f'Replay rejected: {type(exc).__name__}') from exc
        self.stdout.write(json.dumps({'status': report['status'], 'cases': len(report['cases']),
                                     'output': str(target)}, ensure_ascii=False))
