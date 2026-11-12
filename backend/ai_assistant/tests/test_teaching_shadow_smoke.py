"""Focused shadow isolation and anchor/budget smoke, not teaching-effect tests."""
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from rest_framework.exceptions import ValidationError, PermissionDenied

from users.models import User
from ai_assistant.models import ConversationProject, TeachingResearchRun
from ai_assistant.services.teaching_shadow import run_shadow, _cases

FIXTURE = Path(__file__).parent / 'fixtures/rsi_shadow_synthetic.json'


@override_settings(UNIMIND_CONTENT_INSTITUTION_ID='global')
class TeachingShadowSmoke(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='shadow_synthetic', is_member=True)
        self.project = ConversationProject.objects.create(user=self.user, name='影子合成目标')
        self.packet = json.loads(FIXTURE.read_text())

    def test_fixture_g_e_are_private_pending_and_never_live_policy(self):
        with patch('ai_assistant.services.teaching_shadow._call_model') as model:
            for kind in ('G', 'E'):
                report = run_shadow(self.project, kind, self.packet)
                self.assertEqual(report['status'], 'awaiting_independent_anchors')
                self.assertEqual(report['execution'], 'synthetic_fixture')
                self.assertFalse(report['eligible'])
                self.assertFalse(report['activated'])
                self.assertEqual(report['metrics']['baseline']['completed_cases'], 3)
                row = TeachingResearchRun.objects.get(pk=report['run_id'])
                self.assertEqual(row.candidate.owner_id, self.user.pk)
                self.assertEqual(row.baseline.owner_id, self.user.pk)
            model.assert_not_called()

    def test_live_anchors_hidden_candidate_budget_charged_and_equal_e_inputs(self):
        self.packet['anchors'] = [{'case_id':'math-hint', 'expected_score':.7,
                                  'expected_independent_support':False, 'source':'SECRET_ANCHOR_SENTINEL'}]
        seen = []
        def invoke(system, material, schema, max_tokens):
            self.assertNotIn('SECRET_ANCHOR_SENTINEL', system + json.dumps(material))
            self.assertNotIn('anchors', material)
            seen.append(deepcopy(material))
            if 'kind' in material:
                return {'instruction':'先核对帮助和标准，不足就暂缓独立支持判断。'}, {'usage':{'prompt_tokens':3,'completion_tokens':4,'total_tokens':7},'observed_model':'mock-observed'}
            return {'score':.7,'independent_support':False,'reason':'影子调用mock，仅验证通道。'}, {'usage':{'prompt_tokens':5,'completion_tokens':6,'total_tokens':11},'observed_model':'mock-observed'}
        with patch('ai_assistant.services.teaching_shadow._call_model', side_effect=invoke):
            report = run_shadow(self.project, 'E', self.packet, live_model=True)
        self.assertEqual(seen[1], seen[2])
        self.assertEqual(report['budget']['engine_call_slots_used'], {'baseline':3,'candidate':4})
        self.assertTrue(report['budget']['proposal_charged_to_candidate'])
        self.assertFalse(report['comparison']['actual_cost_equal'])
        self.assertEqual(report['status'], 'awaiting_independent_anchors')
        self.assertEqual(report['anchor_validation'], 'operator_supplied_not_attested')
        self.assertEqual(report['metrics']['candidate']['operator_anchor_mae'], 0)

    def test_failed_model_and_budget_limits_do_not_create_winner(self):
        self.packet['budget']['max_calls_per_arm'] = 1
        with patch('ai_assistant.services.teaching_shadow._call_model', side_effect=RuntimeError('secret must not persist')):
            report = run_shadow(self.project, 'E', self.packet, live_model=True)
        self.assertEqual(report['status'], 'incomplete')
        self.assertFalse(report['eligible'])
        self.assertNotIn('secret must not persist', json.dumps(report))
        self.assertTrue(any(row['status'] == 'budget_exhausted' for row in report['calls']))

    def test_case_label_injection_and_foreign_observations_rejected(self):
        self.packet['cases'][0]['expected_score'] = 1
        with self.assertRaises(ValidationError):
            run_shadow(self.project, 'E', self.packet)
        del self.packet['cases'][0]['expected_score']
        self.packet['provenance']['origin'] = 'observational'
        self.packet['cases'] = [{'id':'foreign','task_id':'00000000-0000-0000-0000-000000000000'}]
        with self.assertRaises(ValidationError):
            run_shadow(self.project, 'E', self.packet, live_model=True)
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        with self.assertRaises(PermissionDenied):
            run_shadow(self.project, 'E', self.packet)

    def test_observational_frozen_grading_basis_help_and_duplicate_task_rejection(self):
        from ai_assistant.models import ProjectLearning
        from ai_assistant.services.learning_tasks import create_task
        from quizzes.models import QuizExam, ExamQuestionResult
        from django.utils import timezone
        ProjectLearning.objects.create(project=self.project, status='active', plan={
            'goal':'解释缓存', 'stages':[{'id':'s','title':'说明原理','knowledge_nodes':[]}]})
        task = create_task(self.project, {'stage_id':'s','title':'缓存比较','instructions':'说明原因',
            'definition':{'prompt':'说明缓存和主存的容量与速度权衡。','response_type':'explanation',
                          'criteria':['说明速度与容量方向','解释原因'], 'reference_answer':'缓存通常更快且容量较小。'}})
        exam = QuizExam.objects.create(user=self.user, status='completed', total_questions=1)
        task.exam, task.assistance = exam, 'hint'
        task.save(update_fields=['exam', 'assistance'])
        ExamQuestionResult.objects.create(exam=exam, question=None, position=1, user_answer='缓存更快且更小。',
            score=8, max_score=10, status='graded', question_snapshot=task.question_snapshot['0'], graded_at=timezone.now())
        self.packet['provenance']['origin'] = 'observational'
        self.packet['cases'] = [{'id':'actual','task_id':str(task.pk)}]
        case = _cases(self.project, self.packet)[0]
        self.assertEqual(case['results'][0]['criteria'], ['说明速度与容量方向','解释原因'])
        self.assertEqual(case['results'][0]['reference_answer'], '缓存通常更快且容量较小。')
        self.assertEqual(case['results'][0]['correct_answer'], '缓存通常更快且容量较小。')
        self.assertEqual(case['assistance'], 'hint')
        self.assertEqual(case['actual_exposure']['status'], 'unknown')
        self.assertFalse(case['results'][0]['novelty_verified'])
        self.packet['cases'].append({'id':'renamed-duplicate','task_id':str(task.pk)})
        with self.assertRaises(ValidationError):
            _cases(self.project, self.packet)

    def test_live_fixture_adapter_rejected_empty_usage_unknown_and_g_anchor_rejected(self):
        with override_settings(DEBUG=True, UNIMIND_DSH_GENERATION_ENABLED=True, UNIMIND_DSH_FIXTURE_URL='http://127.0.0.1:9999'):
            with self.assertRaises(ValidationError):
                run_shadow(self.project, 'E', self.packet, live_model=True)
        def invoke(system, material, schema, max_tokens):
            if 'kind' in material:
                return {'instruction':'先核对帮助，再判断独立表现。'}, {'usage':{},'observed_model':None}
            return {'score':.5,'independent_support':False,'reason':'usage缺失mock。'}, {'usage':{},'observed_model':None}
        with patch('ai_assistant.services.teaching_shadow._call_model', side_effect=invoke):
            report = run_shadow(self.project, 'E', self.packet, live_model=True)
        self.assertFalse(report['budget']['observed_success_usage_complete'])
        self.assertFalse(report['budget']['provider_total_usage_complete'])
        self.assertIn('configured_model', report['model'])
        self.packet['anchors'] = [{'case_id':'math-hint','expected_score':.5,'source':'operator'}]
        with self.assertRaises(ValidationError):
            run_shadow(self.project, 'G', self.packet)

    def test_command_defaults_fixture_and_private_no_overwrite(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / 'report.json'
            call_command('research_teaching_mechanisms', project=self.project.pk, kind='G', packet=str(FIXTURE),
                         output=str(output), stdout=StringIO())
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(output.read_text())['status'], 'awaiting_independent_anchors')
            with self.assertRaises(CommandError):
                call_command('research_teaching_mechanisms', project=self.project.pk, kind='G', packet=str(FIXTURE),
                             output=str(output), stdout=StringIO())
