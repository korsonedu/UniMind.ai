"""Smoke coverage for explicit RSI approvals and live rollback boundaries."""
import json
from hashlib import sha256
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.exceptions import PermissionDenied, ValidationError

from ai_assistant.models import (
    AIChatMessage, Bot, Conversation, ConversationProject, ProjectLearning, TaskMemoryProgram,
    TeachingDecisionLog, TeachingMechanismActivation, TeachingResearchRun,
)
from ai_assistant.services import public_methods, task_memory_store, teaching_sidecar
from ai_assistant.services.decision import rsi_governance, rsi_policy
from ai_assistant.services.learning_tasks import create_task
from users.models import CourseStudentStatus, User


@override_settings(UNIMIND_LEARNING_RUNTIME='ulr', UNIMIND_CONTENT_INSTITUTION_ID='global',
    UNIMIND_PRISM_MODE='off', UNIMIND_SDTM_TASK_MEMORY_MODE='active', USE_MEM0=False,
    UNIMIND_ULR_RECHECK_STRATEGY='immediate', UNIMIND_RSI_ONLINE_POLICY_MODE='active',
    UNIMIND_RSI_EXPLORATION_RATE=0.0)
class RSIGovernanceSmoke(TestCase):
    method_spec = {'key': 'compare-cache', 'requires': {'purpose': 'recheck'}, 'source': 'Reviewed teaching method'}

    def setUp(self):
        self.user = User.objects.create_user(username='rsi_governance_learner')
        CourseStudentStatus.objects.create(user=self.user, is_course_student=True)
        self.admin = User.objects.create_superuser(username='rsi_governance_admin')
        self.unmapped = User.objects.create_superuser(username='rsi_governance_unmapped')
        self.project = self.make_project('缓存')
        self.other = self.make_project('其他项目')
        self.bot = Bot.objects.create(name='小宇', bot_type='planner')
        self.room = Conversation.objects.create(user=self.user, bot=self.bot, project=self.project, conversation_id=uuid4())
        self.enterContext(self.settings(UNIMIND_DIRECTUS_ADMIN_MAP={str(uuid4()): self.admin.pk, str(uuid4()): 9999},
                                       UNIMIND_RSI_POLICY_PROJECTS=frozenset({self.project.pk})))

    def make_project(self, name):
        project = ConversationProject.objects.create(user=self.user, name=name)
        ProjectLearning.objects.create(project=project, planning_enabled=True, status='active', current_stage='start',
            plan={'goal': '解释缓存', 'stages': [{'id': 'start', 'title': '起点', 'knowledge_nodes': []}]})
        return project

    def task(self, project):
        return create_task(project, {'stage_id': 'start', 'title': '缓存边界', 'instructions': '自己解释。',
            'purpose': 'recheck', 'definition': {'prompt': '请解释缓存未命中的过程。',
                                                'response_type': 'explanation', 'criteria': ['说明访问过程']}})

    def message(self):
        return AIChatMessage.objects.create(user=self.user, bot=self.bot, role='user', content='请继续。',
            conversation_id=self.room.conversation_id)

    def make_run(self, kind, *, decision_point='recheck_timing', policy=None, instruction='比较缓存命中和未命中。'):
        baseline = teaching_sidecar.register_mechanism(kind, {'scope': 'baseline'}, owner=self.user)
        if kind == 'S':
            # Match T5's persisted replay schema, including legacy top-level metrics and probabilities.
            content = {'decision_point': decision_point, 'probabilities': {'delayed-v1': .75, 'immediate-v1': .25}}
            if policy is not None:
                content = {'decision_point': decision_point, 'target_policy': policy}
            protocol = {'decision_point': decision_point}
            report = {'status': 'evaluated_offline_replay', 'execution': 'offline_replay', 'n': 3,
                      'effective_sample_size': 2.5, 'snips_estimate': .8, 'baseline_mean_reward': .7}
        else:
            protocol = {}
            content = {'instruction': instruction}
            report = {'execution': 'live_model', 'status': 'evaluated_objective_anchors',
                      'anchor_validation': 'objective_answer_key_verified', 'scope': {'origin': 'observational'},
                      'comparison': {'candidate_instruction_changed': True},
                      'metrics': {'baseline': {'operator_anchor_mae': .2, 'proxy_mean': .6},
                                  'candidate': {'completed_cases': 3, 'operator_anchor_count': 3,
                                                'operator_anchor_mae': .1, 'proxy_mean': .8,
                                                'operator_false_independent_support': 0}}}
        candidate = teaching_sidecar.register_mechanism(kind, content, owner=self.user, parent=baseline)
        return TeachingResearchRun.objects.create(owner=self.user, project=self.project, kind=kind, baseline=baseline,
            candidate=candidate, packet_hash='fixture', protocol=protocol, report=report)

    def test_gate_rejects_unsafe_or_unsupported_results(self):
        for kind in ('E', 'G'):
            run = self.make_run(kind)
            with self.subTest(kind=kind):
                self.assertTrue(rsi_governance.evaluate_gate(run.pk)['passed'])
                run.report['execution'] = 'synthetic_fixture'
                run.report['scope']['origin'] = 'synthetic_fixture'
                run.report['anchor_validation'] = 'operator_supplied_not_attested'
                run.report['metrics']['candidate'].update(operator_anchor_mae=.3, proxy_mean=.5,
                                                           operator_false_independent_support=1)
                run.save(update_fields=['report'])
                expected = ['live_model_required', 'false_independent_support']
                expected += ['unattested_anchors', 'mae_regression'] if kind == 'E' else [
                    'observational_data_required', 'insufficient_proxy_gain']
                self.assertEqual(rsi_governance.evaluate_gate(run.pk)['failures'], expected)
                if kind == 'E':
                    self.assertIn('unattested_anchors', rsi_governance.evaluate_gate(
                        run.pk, require_attested_anchors=False)['failures'])
                with self.assertRaisesRegex(ValidationError, 'false_independent_support'):
                    rsi_governance.approve_and_activate(run.pk, self.admin)
        run = self.make_run('S')
        run.report.update(effective_sample_size=1.5, snips_estimate=.6)
        run.save(update_fields=['report'])
        self.assertEqual(rsi_governance.evaluate_gate(run.pk)['failures'], ['insufficient_ess', 'snips_regression'])
        self.assertFalse(TeachingMechanismActivation.objects.exists())

    def test_only_mapped_platform_admin_can_activate_or_rollback(self):
        run = self.make_run('E')
        for reviewer in (self.user, self.unmapped):
            with self.assertRaises(PermissionDenied):
                rsi_governance.approve_and_activate(run.pk, reviewer)
        with self.assertRaises(ValidationError):
            rsi_governance.approve_and_activate(run.pk, self.admin, scope='global')
        with self.assertRaises(ValidationError):
            rsi_governance.approve_and_activate(run.pk, self.admin, project=self.other)
        result = rsi_governance.approve_and_activate(run.pk, self.admin)
        self.assertEqual((result['status'], result['project_id'], result['published_program_id']),
                         ('canary_active', self.project.pk, None))
        with self.assertRaises(PermissionDenied):
            rsi_governance.rollback_activation(result['activation_id'], self.unmapped)

    def test_recheck_canary_records_exact_probabilities_and_rolls_back(self):
        run = self.make_run('S')
        task = self.task(self.project)
        self.assertTrue(rsi_governance.evaluate_gate(run.pk)['passed'])
        self.assertIsNone(rsi_governance.active_s_policy(self.project.pk, 'recheck_timing'))
        result = rsi_governance.approve_and_activate(run.pk, self.admin)
        activation_id = result['activation_id']
        pick, log = rsi_policy.select_recheck_timing(self.project, task, self.message(), source_result_id=713)
        draw = int(sha256(f'recheck:{self.project.pk}:713:activation-{activation_id}'.encode()).hexdigest(), 16) / (1 << 256)
        self.assertEqual(pick, 'delayed-v1' if draw < .75 else 'immediate-v1')
        self.assertEqual(log.propensity, {'delayed-v1': .75, 'immediate-v1': .25}[pick])
        self.assertEqual(log.selection_mode, 'stratified_random')
        self.assertEqual((log.mechanism_id, log.policy_version, log.context_snapshot['activation_id']),
                         (run.candidate_id, f'{rsi_policy.RECHECK_VERSION}:activation-{activation_id}', activation_id))
        with self.settings(UNIMIND_RSI_ONLINE_POLICY_MODE='off'):
            pick, off = rsi_policy.select_recheck_timing(self.project, task, self.message(), source_result_id=713)
        self.assertEqual((pick, off.policy_version, off.propensity), ('immediate-v1', rsi_policy.RECHECK_VERSION, None))
        rsi_governance.rollback_activation(activation_id, self.admin)
        pick, fallback = rsi_policy.select_recheck_timing(self.project, task, self.message(), source_result_id=713)
        self.assertEqual((pick, fallback.policy_version), ('immediate-v1', rsi_policy.RECHECK_VERSION))
        self.assertNotEqual(fallback.mechanism_id, run.candidate_id)
        log.refresh_from_db()
        self.assertEqual(log.mechanism_id, run.candidate_id)

    def test_method_ranking_canary_supersedes_global_and_restores_predecessor(self):
        decision_point = 'method_ranking'
        global_run = self.make_run('S', decision_point=decision_point, policy={'exploration_rate': .4})
        global_activation = rsi_governance.approve_and_activate(global_run.pk, self.admin, scope='global')
        canary_run = self.make_run('S', decision_point=decision_point, policy={'public:1': 1.0})
        canary = rsi_governance.approve_and_activate(canary_run.pk, self.admin)
        new_run = self.make_run('S', decision_point=decision_point, policy={'public:2': 1.0})
        replacement = rsi_governance.approve_and_activate(new_run.pk, self.admin)
        self.assertEqual(replacement['previous_id'], canary['activation_id'])
        self.assertEqual(TeachingMechanismActivation.objects.get(pk=canary['activation_id']).rollback_reason,
                         f"superseded_by:{replacement['activation_id']}")
        public = [{'method_id': 2}, {'method_id': 1}]
        for activation, expected_action, expected_probabilities in [
            (replacement, 'public:2', {'public:2': 1.0, 'public:1': 0.0}),
            (canary, 'public:1', {'public:2': 0.0, 'public:1': 1.0}),
            (global_activation, None, {'public:2': .8, 'public:1': .2}),
        ]:
            message = self.message()
            ranking = rsi_policy.rank_method_candidates(self.project, message, public_methods=public)
            log = TeachingDecisionLog.objects.get(message=message)
            self.assertEqual(log.mechanism_id, activation['mechanism_id'])
            self.assertEqual(log.policy_version, f"{rsi_policy.METHOD_VERSION}:activation-{activation['activation_id']}")
            self.assertEqual(log.context_snapshot['activation_id'], activation['activation_id'])
            self.assertEqual(log.selected_action, expected_action or ranking['method_candidate_order'][0])
            self.assertEqual(log.propensity, expected_probabilities[log.selected_action])
            self.assertEqual({row['action']: row['propensity'] for row in log.candidates}, expected_probabilities)
            rsi_governance.rollback_activation(activation['activation_id'], self.admin, restore_previous=True)
        ranking = rsi_policy.rank_method_candidates(self.project, self.message(), public_methods=public)
        self.assertEqual(ranking['public_methods'], public)

    def test_public_method_canary_rolls_back_without_losing_frozen_sdtm_frames(self):
        self.task(self.project)
        self.task(self.other)
        run = self.make_run('G')
        result = rsi_governance.approve_and_activate(run.pk, self.admin, public_method_spec=self.method_spec)
        program_id = result['published_program_id']
        self.assertEqual(TaskMemoryProgram.objects.get(pk=program_id).definition['instruction'], run.candidate.content['instruction'])
        prepared = task_memory_store.prepare(self.project, self.user)
        self.assertEqual([row['method_id'] for row in prepared['packet']['public_methods']], [program_id])
        self.assertEqual(task_memory_store.prepare(self.other, self.user)['packet']['public_methods'], [])

        new_run = self.make_run('G', instruction='先列举缓存未命中的条件。')
        replacement = rsi_governance.approve_and_activate(new_run.pk, self.admin, public_method_spec=self.method_spec)
        self.assertEqual(public_methods.catalogue(self.project.pk)[0]['id'], replacement['published_program_id'])
        restored = rsi_governance.rollback_activation(replacement['activation_id'], self.admin, restore_previous=True)
        self.assertEqual(restored['restored_activation_id'], result['activation_id'])
        self.assertEqual(public_methods.catalogue(self.project.pk)[0]['id'], restored['rollback_program_id'])
        self.assertEqual(public_methods.catalogue(self.project.pk)[0]['definition']['instruction'], run.candidate.content['instruction'])

        rolled_back = rsi_governance.rollback_activation(result['activation_id'], self.admin, reason='operator review')
        self.assertEqual(rolled_back['rollback_reason'], 'operator review')
        self.assertTrue(TaskMemoryProgram.objects.get(pk=rolled_back['rollback_program_id']).definition['retired'])
        self.assertEqual(task_memory_store.prepare(self.project, self.user)['packet']['public_methods'], [])
        self.assertEqual(task_memory_store.restore(prepared['frame_id'], self.user), prepared['packet'])

    def test_management_command_evaluates_approves_and_rolls_back(self):
        run = self.make_run('G')

        def command(*args):
            output = StringIO()
            call_command('govern_teaching_mechanism', *args, stdout=output)
            return json.loads(output.getvalue())

        self.assertTrue(command('--action', 'evaluate', '--run-id', str(run.pk))['passed'])
        self.assertFalse(TeachingMechanismActivation.objects.exists())
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'method.json'
            path.write_text(json.dumps(self.method_spec), encoding='utf-8')
            approval = command('--action', 'approve', '--run-id', str(run.pk), '--reviewer-id', str(self.admin.pk),
                               '--method-spec', str(path), '--scope', 'global')
        self.assertEqual(approval['status'], 'active')
        self.assertEqual(public_methods.catalogue()[0]['id'], approval['published_program_id'])
        rollback = command('--action', 'rollback', '--activation-id', str(approval['activation_id']),
                           '--reviewer-id', str(self.admin.pk), '--restore-previous')
        self.assertEqual(rollback['status'], 'rolled_back')
        self.assertEqual(public_methods.catalogue(), [])
