"""Read-only, explicitly scoped replay; never tunes or deploys parameters."""
import json
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from ai_assistant.models import ConversationProject, LearningKnowledgeVersion
from ai_assistant.services.learning_knowledge import verified_knowledge_events
from ai_assistant.services.bayesian_evaluation import evaluate_records


class Command(BaseCommand):
    help = 'Evaluate BEP on independent held-out tasks for one project and map version; outputs aggregate JSON without source text.'

    def add_arguments(self, parser):
        parser.add_argument('--project-id', type=int, required=True)
        parser.add_argument('--version-id', type=int, required=True)
        parser.add_argument('--test-after', required=True, help='Timezone-aware ISO timestamp; fixed holdout starts here.')
        parser.add_argument('--data-origin', required=True, choices=['synthetic', 'observational'], help='Operator declaration, not verified learner provenance.')

    def handle(self, *args, **options):
        try:
            cutoff = datetime.fromisoformat(options['test_after'])
            if cutoff.tzinfo is None or cutoff.utcoffset() is None:
                raise ValueError()
        except ValueError as exc:
            raise CommandError('--test-after must be an ISO timestamp with a timezone.') from exc
        project = ConversationProject.objects.filter(pk=options['project_id']).first()
        if not project or not LearningKnowledgeVersion.objects.filter(pk=options['version_id'], knowledge_map__user_id=project.user_id).exists():
            raise CommandError('Project or owned knowledge version is unavailable.')
        verified = verified_knowledge_events(project, options['version_id'])
        records = []
        for event, probe in verified['events']:
            check = event.content['knowledge_check']
            records.append({key: check[key] for key in ('version_id', 'node_id', 'mode', 'outcome', 'assistance', 'answer_hash')} | {
                'event_id': event.pk, 'message_id': event.message_id, 'probe_id': probe.pk,
                'question_hash': probe.content['question_hash'], 'at': event.created_at.isoformat(), 'task_at': probe.created_at.isoformat()})
        report = evaluate_records(records, cutoff, options['data_origin'])
        report['scope'] = {'project_id': project.pk, 'version_id': options['version_id']}
        report['provenance'] = {key: value for key, value in verified.items() if key != 'events'}
        report['notice'] = ('Offline fixed holdout against XiaoYu rubric judgements; task and grading reliability are unvalidated. '
                            'Data origin is operator-declared. Scores do not establish calibration or learning improvement. '
                            'Historical source availability is rechecked at report time. No state or parameter writes.')
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
