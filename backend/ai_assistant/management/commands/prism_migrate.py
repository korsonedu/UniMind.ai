"""Explicit legacy inventory and privately reviewed migration; no automatic promotion."""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from rest_framework.exceptions import APIException

from ai_assistant.models import PrismProposal
from ai_assistant.services import prism_migration
from users.models import User


class Command(BaseCommand):
    help = 'Inventory legacy records or stage/review an owned private migration. Never creates shared memory.'

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['inventory', 'stage', 'review'])
        parser.add_argument('--student', type=int)
        parser.add_argument('--kind', choices=['experience', 'method'])
        parser.add_argument('--source-id', type=int)
        parser.add_argument('--reviewer')
        parser.add_argument('--proposal', type=int)
        parser.add_argument('--spec')

    def handle(self, *args, **options):
        try:
            user = User.objects.get(pk=options['student'], is_active=True) if options['student'] else None
            action = options['action']
            if action == 'inventory':
                result = prism_migration.inventory(user)
            else:
                if not options['reviewer']:
                    raise ValueError('A trusted reviewer identity is required.')
                reviewer = User.objects.get(username=options['reviewer'], is_active=True)
                if action == 'stage':
                    if not user or not options['kind'] or not options['source_id']:
                        raise ValueError('Staging requires --student, --kind and --source-id.')
                    proposal = prism_migration.stage(user, options['kind'], options['source_id'], reviewer)
                    result = {'proposal_id': proposal.pk, 'memory_key': proposal.memory.key, 'status': proposal.status}
                else:
                    if not options['proposal'] or not options['spec'] or options['student']:
                        raise ValueError('Review requires --proposal and --spec; ownership cannot be overridden.')
                    spec = json.loads(Path(options['spec']).read_text())
                    result = prism_migration.review(options['proposal'], reviewer, spec)
            self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        except (OSError, ValueError, TypeError, KeyError, APIException, User.DoesNotExist, PrismProposal.DoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
