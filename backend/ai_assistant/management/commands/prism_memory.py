"""Replay SDTM on reference cases; optionally install a scoped experimental memory."""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from ai_assistant.models import PrismMemory, PrismProposal
from users.models import User
from ai_assistant.services.prism_kernel import differentiate, evaluate, induce, validate_splits
from ai_assistant.services.prism_memory import refine


class Command(BaseCommand):
    help = 'Replay reviewed cases. Default is read-only; --install persists a scoped memory.'

    def add_arguments(self, parser):
        parser.add_argument('path')
        parser.add_argument('--install', metavar='KEY')
        parser.add_argument('--student', type=int, help='Omit only for explicitly reviewed public system cases.')
        parser.add_argument('--review', type=int, help='Review a grounded relation proposal using reference cases.')
        parser.add_argument('--reviewer', help='Trusted reviewer username; identity is never supplied by the model.')
        parser.add_argument('--promote-from', help='Personal memory key to propose as a shared abstraction.')
        parser.add_argument('--map-from', help='Public single-relation memory with an alternate encoding.')
        parser.add_argument('--map-to', help='Canonical public single-relation memory.')

    def handle(self, *args, **options):
        try:
            data = json.loads(Path(options['path']).read_text())
            if options['map_from'] or options['map_to']:
                if (not options['map_from'] or not options['map_to'] or not options['reviewer']
                        or any(options[key] for key in ('install', 'student', 'review', 'promote_from'))):
                    raise ValueError('Mapping requires --map-from, --map-to and --reviewer without other actions.')
                from ai_assistant.services.prism_mapping import review_mapping
                proposal = review_mapping(PrismMemory.objects.get(key=options['map_from']).pk,
                    PrismMemory.objects.get(key=options['map_to']).pk, User.objects.get(username=options['reviewer']), data)
                self.stdout.write(json.dumps(proposal.review, ensure_ascii=False, indent=2))
                return
            if options['review'] or options['promote_from']:
                if not options['reviewer'] or options['student']:
                    raise ValueError('A reviewer is required; --student cannot override proposal ownership.')
                from ai_assistant.services.prism_feedback import propose_shared, review_relation, review_shared
                reviewer = User.objects.get(username=options['reviewer'])
                if options['review']:
                    if options['install'] or options['promote_from']:
                        raise ValueError('--review cannot be combined with installation or promotion.')
                    result = review_relation(options['review'], reviewer, data)
                else:
                    if not options['install']:
                        raise ValueError('Promotion requires a new --install target key.')
                    source = PrismMemory.objects.get(key=options['promote_from'])
                    proposal = propose_shared(source.pk, options['install'], reviewer)
                    result = review_shared(proposal.pk, reviewer, data)
                self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
                return
            fields = data['fields']
            training, validation, test = [data[key] for key in ('training', 'validation', 'test')]
            validate_splits(training, validation, test)
            ids = [case['id'] for cases in (training, validation, test) for case in cases]
            if len(ids) != len(set(ids)) or not fields or not set(fields) <= set(training[0]['features']):
                raise ValueError('Splits need distinct case IDs and an observed initial representation.')
            result = differentiate(training, validation, fields)
            selected = result['selected']['fields'] if result['selected'] else fields
            result['test_before'] = evaluate(training, test, fields)
            result['test_after'] = evaluate(training, test, selected)
            if options['install']:
                student = options['student']
                if any(case.get('source_message_id') for cases in (training, validation, test) for case in cases):
                    raise ValueError('CLI installation accepts reviewed, source-independent reference cases only.')
                if student is None and data.get('public_system_cases') is not True:
                    raise ValueError('System installation requires public_system_cases=true.')
                if student is None:
                    from users.permissions import is_platform_admin
                    if not options['reviewer'] or not is_platform_admin(User.objects.get(username=options['reviewer'])):
                        raise PermissionDenied('System installation requires a platform administrator reviewer.')
                with transaction.atomic():
                    if PrismMemory.objects.filter(key=options['install']).exists():
                        raise ValueError('Memory key exists; use the revision-checked refinement service.')
                    memory = PrismMemory.objects.create(key=options['install'], owner_id=student,
                        scope='student' if student is not None else 'system', fields=fields,
                        cases=training, operators=induce(training, fields))
                    refine(memory.pk, memory.revision, training, validation)
                    result['installed'] = memory.key
            self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
        except (OSError, ValueError, TypeError, KeyError, ValidationError, PermissionDenied,
                User.DoesNotExist, PrismMemory.DoesNotExist, PrismProposal.DoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
