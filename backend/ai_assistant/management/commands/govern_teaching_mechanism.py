"""Evaluate, approve, or roll back a teaching mechanism from the operator CLI."""
import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from rest_framework.exceptions import APIException

from ai_assistant.services import rsi_governance


def _read_spec(value):
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return json.loads(Path(value).read_text(encoding='utf-8'))


class Command(BaseCommand):
    help = 'Evaluate a teaching research gate or explicitly approve or roll back a mechanism.'

    def add_arguments(self, parser):
        parser.add_argument('--action', choices=('evaluate', 'approve', 'rollback'), required=True)
        parser.add_argument('--run-id', type=int)
        parser.add_argument('--activation-id', type=int)
        parser.add_argument('--reviewer-id', type=int)
        parser.add_argument('--scope', choices=('project_canary', 'global'), default='project_canary')
        parser.add_argument('--method-spec', help='Reviewed public method spec as JSON or a path to a JSON file.')
        parser.add_argument('--reason', default='')
        parser.add_argument('--restore-previous', action='store_true')

    def handle(self, *args, **options):
        action, run_id = options['action'], options['run_id']
        activation_id, reviewer_id = options['activation_id'], options['reviewer_id']
        if action in ('evaluate', 'approve') and run_id is None:
            raise CommandError(f'--run-id is required for {action}.')
        if action == 'rollback' and activation_id is None:
            raise CommandError('--activation-id is required for rollback.')
        if action != 'evaluate' and reviewer_id is None:
            raise CommandError(f'--reviewer-id is required for {action}.')

        try:
            if action == 'evaluate':
                result = rsi_governance.evaluate_gate(run_id)
            else:
                reviewer = get_user_model().objects.get(pk=reviewer_id)
                if action == 'approve':
                    result = rsi_governance.approve_and_activate(run_id, reviewer, scope=options['scope'],
                        public_method_spec=_read_spec(options['method_spec']))
                else:
                    result = rsi_governance.rollback_activation(activation_id, reviewer, reason=options['reason'],
                        restore_previous=options['restore_previous'])
        except APIException as exc:
            raise CommandError(json.dumps({'action': action, 'error': exc.detail}, ensure_ascii=False)) from exc
        except (ObjectDoesNotExist, OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False, allow_nan=False))
