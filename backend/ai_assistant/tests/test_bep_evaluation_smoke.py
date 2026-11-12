import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from users.models import User
from ai_assistant.models import (AIChatMessage, Bot, Conversation, ConversationProject, ProjectLearningEvent,
    LearningKnowledgeMap, LearningKnowledgeVersion)
from ai_assistant.services.bayesian_evidence import ALGORITHM_VERSION, belief, GUESS, SLIP
from ai_assistant.services.bayesian_evaluation import evaluate_records


class EvaluationMathSmoke(SimpleTestCase):
    cutoff = datetime(2026, 1, 2, tzinfo=dt_timezone.utc)

    def record(self, key, day, **changes):
        at = self.cutoff + timedelta(days=day, hours=1)
        return {'event_id': key, 'message_id': key, 'probe_id': key, 'version_id': 1, 'node_id': 'n', 'mode': 'apply',
                'question_hash': f'q{key}', 'answer_hash': f'a{key}', 'outcome': 'success', 'assistance': 'independent',
                'at': at.isoformat(), 'task_at': (at-timedelta(minutes=1)).isoformat(), **changes}

    def test_probability_transform_scores_and_empty_holdout(self):
        estimate = belief([], self.cutoff)
        self.assertAlmostEqual(estimate['predicted_success'], GUESS + (1-GUESS-SLIP)*estimate['mean'])
        self.assertAlmostEqual(estimate['predicted_success'], .55)
        report = evaluate_records([self.record(1, 1)], self.cutoff, 'synthetic')
        self.assertAlmostEqual(report['metrics']['bep']['overall']['brier'], (.55-1)**2)
        self.assertFalse(report['calibrated'])
        empty = evaluate_records([self.record(1, -1)], self.cutoff, 'synthetic')
        self.assertIsNone(empty['metrics']['bep']['overall']['brier'])
        self.assertIsNone(empty['metrics']['bep']['overall']['log_loss'])
        json.dumps(empty, allow_nan=False)

    def test_fixed_holdout_no_future_labels_or_same_time_leakage(self):
        train, first, later = self.record(1, -1), self.record(2, 1), self.record(3, 2)
        before = evaluate_records([later, train, first], self.cutoff, 'synthetic')
        after = evaluate_records([later, train, {**first, 'outcome': 'failure'}], self.cutoff, 'synthetic')
        self.assertEqual(before['predictions'][1]['probabilities'], after['predictions'][1]['probabilities'])
        self.assertEqual(before['predictions'][1]['history_count'], 1)
        # A task before the cutoff cannot use a grade recorded at or after that cutoff.
        straddling = {**self.record(4, 0), 'task_at': (self.cutoff-timedelta(seconds=1)).isoformat()}
        report = evaluate_records([train, straddling, first], self.cutoff, 'synthetic')
        self.assertEqual(len(report['predictions']), 1)
        self.assertEqual(report['counts']['straddling'], 1)

    def test_track_duplicate_and_help_conditions(self):
        rows = [self.record(1, -1), self.record(2, 1, mode='transfer'),
                self.record(3, 2, assistance='hint'), self.record(4, 3, question_hash='q1'),
                self.record(5, 4, answer_hash='a1', mode='transfer')]
        report = evaluate_records(rows, self.cutoff, 'synthetic')
        self.assertEqual(len(report['predictions']), 1)
        self.assertAlmostEqual(report['predictions'][0]['probabilities']['bep'], .55)
        self.assertEqual(report['counts']['duplicate'], 2)
        self.assertEqual(report['counts']['unscored_holdout'], 1)
        self.assertEqual(report['metrics']['bep']['transfer']['n'], 1)


class EvaluationCommandSmoke(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='bep_eval_synthetic')
        self.bot = Bot.objects.create(name='小宇', bot_type='planner')
        self.project = ConversationProject.objects.create(user=self.user, name='合成评估')
        self.cid = uuid.uuid4()
        Conversation.objects.create(user=self.user, bot=self.bot, project=self.project, conversation_id=self.cid)
        knowledge_map = LearningKnowledgeMap.objects.create(user=self.user, title='合成知识')
        self.version = LearningKnowledgeVersion.objects.create(knowledge_map=knowledge_map, revision=1, snapshot={'title':'合成知识','nodes':[]})
        self.start = timezone.now()-timedelta(days=4)
        self.cutoff = self.start+timedelta(days=2)
        self.fixture(0); self.fixture(3)

    def fixture(self, day):
        at = self.start+timedelta(days=day)
        def message(role, content, minute, **extra):
            row = AIChatMessage.objects.create(user=self.user, bot=self.bot, conversation_id=self.cid, role=role, content=content, **extra)
            AIChatMessage.objects.filter(pk=row.pk).update(timestamp=at+timedelta(minutes=minute))
            row.refresh_from_db();return row
        trigger = message('user', '准备任务', 0)
        question = f'解释第 {day} 个程序里变量的变化和执行顺序。'
        probe = ProjectLearningEvent.objects.create(project=self.project, message=trigger, kind='probe', content={
            'version_id':self.version.pk,'node_id':'n','mode':'apply','question':question,'rubric':'解释先后顺序',
            'question_hash':hashlib.sha256(question.encode()).hexdigest()})
        ProjectLearningEvent.objects.filter(pk=probe.pk).update(created_at=at+timedelta(minutes=1))
        message('assistant', question, 2, metadata={'learning_turn':{'message_id':trigger.pk,'completed':True,'completed_at':(at+timedelta(minutes=2)).isoformat()}})
        answer = message('user', f'我独立说明第 {day} 个程序的变量先后变化。', 3)
        event = ProjectLearningEvent.objects.create(project=self.project, message=answer, kind='progress', content={'knowledge_check':{
            'algorithm':ALGORITHM_VERSION,'probe_id':probe.pk,'version_id':self.version.pk,'node_id':'n','mode':'apply',
            'outcome':'success','assistance':'independent','quote':answer.content,'answer_hash':hashlib.sha256(answer.content.encode()).hexdigest()}})
        ProjectLearningEvent.objects.filter(pk=event.pk).update(created_at=at+timedelta(minutes=4))

    def evaluate(self, **overrides):
        output=StringIO()
        call_command('evaluate_bep', project_id=self.project.pk, version_id=self.version.pk,
            test_after=self.cutoff.isoformat(), data_origin='synthetic', stdout=output, **overrides)
        return json.loads(output.getvalue())

    def test_read_only_scoped_report_and_deleted_provenance(self):
        with CaptureQueriesContext(connection) as queries:
            report = self.evaluate()
        self.assertEqual(len(report['predictions']), 1)
        self.assertTrue(all(query['sql'].lstrip().upper().startswith('SELECT') for query in queries))
        encoded=json.dumps(report)
        self.assertNotIn('我独立说明',encoded)
        self.assertNotIn('解释第',encoded)
        self.assertNotIn(self.user.username,encoded)
        AIChatMessage.objects.filter(role='assistant').delete()
        empty = self.evaluate()
        self.assertEqual(empty['provenance']['excluded_provenance'], 2)
        self.assertEqual(empty['predictions'], [])

    def test_command_rejects_foreign_version_and_naive_cutoff(self):
        with self.assertRaises(CommandError):
            call_command('evaluate_bep',project_id=self.project.pk,version_id=self.version.pk,test_after='2026-01-02',data_origin='synthetic',stdout=StringIO())
        other=User.objects.create_user(username='eval_other')
        foreign=ConversationProject.objects.create(user=other,name='其他人的项目')
        with self.assertRaises(CommandError):
            call_command('evaluate_bep',project_id=foreign.pk,version_id=self.version.pk,test_after=self.cutoff.isoformat(),data_origin='synthetic',stdout=StringIO())
