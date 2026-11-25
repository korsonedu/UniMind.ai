import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from rest_framework.exceptions import ValidationError

from ai_assistant.models import ProjectLearningTask
from ai_assistant.services.learning_diagnostics import certify_task, register_example
from ai_assistant.services.public_methods import publish_method


class Command(BaseCommand):
    help = 'Import reviewed SDTM task bindings and examples for one pilot project.'

    def add_arguments(self, parser):
        parser.add_argument('manifest', type=Path)
        parser.add_argument('--project', type=int, required=True)
        parser.add_argument('--apply', action='store_true', help='Save the reviewed material.')

    @transaction.atomic
    def handle(self, manifest, project, apply, **options):
        try:
            data = json.loads(manifest.read_text(encoding='utf-8'))
            version = publish_method(data['method'], request_key=data['publication_id'])
            for item in data['tasks']:
                task = ProjectLearningTask.objects.get(pk=item['task_id'], project_id=project)
                certify_task(task, schema=item['schema'], bindings=item['bindings'], decisions=item['decisions'])
            for item in data['examples']:
                register_example(item['card'], schema=item['schema'], bindings=item['bindings'], decisions=item['decisions'],
                                 method_id=version.pk, method_digest=version.digest)
        except (OSError, KeyError, TypeError, ValueError, ValidationError, ProjectLearningTask.DoesNotExist) as error:
            raise CommandError(str(error)) from error
        if not apply:
            transaction.set_rollback(True)
        action = 'Imported' if apply else 'Validated'
        self.stdout.write(f"{action} {len(data['tasks'])} task bindings and {len(data['examples'])} examples.")
