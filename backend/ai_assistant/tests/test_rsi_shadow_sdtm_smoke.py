"""Exercise the SDTM shadow and replay entry points with synthetic recorded evidence."""
from datetime import timedelta
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from ai_assistant.models import (
    AIChatMessage, Bot, Conversation, ConversationProject, LearningStrategyUse, ProjectLearning, ProjectLearningEvent,
    TaskMemoryFrame, TaskMemoryState, TeachingDecisionLog, TeachingResearchRun,
)
from ai_assistant.services import learning_diagnostics, task_memory_store, teaching_sidecar
from ai_assistant.services.learning_library import strategy_operation
from ai_assistant.services.learning_tasks import create_task, sync_task_result
from ai_assistant.services.project_learning import completed_learning_turn
from ai_assistant.services.rsi_dataset import build_s_replay_dataset, build_sdtm_shadow_packet
from ai_assistant.services.teaching_shadow import run_s_offline_replay, run_shadow
from quizzes.models import ExamQuestionResult, QuizExam
from users.models import CourseStudentStatus, User


@override_settings(UNIMIND_CONTENT_INSTITUTION_ID='global', UNIMIND_LEARNING_RUNTIME='ulr',
    UNIMIND_PRISM_MODE='off', UNIMIND_SDTM_TASK_MEMORY_MODE='active', UNIMIND_SDTM_STRUCTURED_DIAGNOSTICS=True,
    UNIMIND_SDTM_DIAGNOSTIC_PROJECTS=frozenset(), USE_MEM0=False)
class RSIShadowSDTMSmoke(TestCase):
    def setUp(self):
        self.start = timezone.now() - timedelta(days=1)
        self.user = User.objects.create_user(username='rsi_shadow_sdtm')
        self.student = CourseStudentStatus.objects.create(user=self.user, is_course_student=True)
        self.bot = Bot.objects.create(name='小宇', bot_type='planner')
        self.project = ConversationProject.objects.create(user=self.user, name='计算机原理')
        self.room = Conversation.objects.create(user=self.user, bot=self.bot, project=self.project, conversation_id=uuid4())
        ProjectLearning.objects.create(project=self.project, status='active', current_stage='start',
            plan={'goal': '解释缓存', 'stages': [{'id': 'start', 'title': '起点', 'knowledge_nodes': []}]})
        with self.at(0):
            source = ProjectLearningEvent.objects.create(project=self.project, message=self.message(), kind='progress',
                content={'strategy': '比较两种访问条件。'})
            self.strategy = strategy_operation(self.project, {'action': 'save', 'event_id': source.pk})['strategy_id']

    def stamp(self, minute):
        return self.start + timedelta(minutes=minute)

    def at(self, minute):
        return patch('django.utils.timezone.now', return_value=self.stamp(minute))

    def message(self, *, role='user', metadata=None):
        return AIChatMessage.objects.create(user=self.user, bot=self.bot, conversation_id=self.room.conversation_id,
            role=role, content='比较两种访问条件。', metadata=metadata or {})

    def reply(self, message, teaching=None):
        reply = self.message(role='assistant',
            metadata={'learning_turn': completed_learning_turn(message.pk), 'ulr_teaching': teaching or {}})
        teaching_sidecar.record_turn_completion(reply)
        return reply

    def use(self, message):
        teaching_sidecar.freeze_turn(self.project, message, {})
        result = strategy_operation(self.project, {'action': 'apply', 'strategy_id': self.strategy,
            'reason': '比较两个情境。'}, message=message)
        return LearningStrategyUse.objects.get(pk=result['use_id'])

    def task(self, prompt, *, use=None, source=None):
        return create_task(self.project, {'stage_id': 'start', 'title': '缓存案例', 'instructions': '独立作答。',
            'purpose': 'recheck' if source else 'practice', 'source_task_id': source.pk if source else None,
            'strategy_use_id': use.pk if use else None, 'definition': {'prompt': prompt, 'response_type': 'objective',
                'options': {'A': '选项甲', 'B': '选项乙'}, 'reference_answer': 'A', 'criteria': ['使用独立作答']}})

    def grade(self, task, *, success):
        score = 10 if success else 0
        task.exam = QuizExam.objects.create(user=self.user, status='completed', total_questions=1,
            graded_count=1, total_score=score, max_score=10)
        task.assistance = 'independent'
        task.save(update_fields=['exam', 'assistance'])
        result = ExamQuestionResult.objects.create(exam=task.exam, score=score, max_score=10,
            user_answer='A' if success else 'B', question_snapshot=task.question_snapshot['0'],
            status='graded', graded_at=timezone.now())
        sync_task_result(result)

    def disclose(self, task):
        learning_diagnostics.certify_task(task, schema='cache-v1', bindings={'instance': str(task.pk)}, decisions=['choice'])
        message = self.message()
        reply = self.reply(message)
        learning_diagnostics.certify_text_delivery(task, message, reply, span=(0, len(reply.content)),
            quote=reply.content, decisions=['choice'])

    def observed_task(self, prompt, minute, *, success=False, disclosed=False, overlap=False, grade_at=None):
        with self.at(minute):
            message = self.message()
            use = self.use(message)
        with self.at(minute + 1):
            self.reply(message)
            task = self.task(prompt, use=use)
            if overlap:
                self.use(self.message())
            if disclosed:
                self.disclose(task)
        with self.at(grade_at if grade_at is not None else minute + 2):
            self.grade(task, success=success)
        return task

    def frame(self, minute, revision):
        memory, _ = TaskMemoryState.objects.get_or_create(owner=self.user, project=self.project)
        program = task_memory_store.publish_policy(.6, request_key='shadow-sdtm-smoke')
        return TaskMemoryFrame.objects.create(memory=memory, program=program, occurred_at=self.stamp(minute),
            revision=revision, source={}, packet_digest=teaching_sidecar.canonical_hash({}))

    def packet(self, kind='E'):
        return build_sdtm_shadow_packet(self.project, kind=kind, cutoff_at=self.stamp(10),
            baseline_instruction='按标准核对独立作答。', development_goal='评估缓存理解。')

    def test_temporal_holdout_uses_old_frame_and_excludes_ineligible_tasks(self):
        self.observed_task('截止前出现的独立问题。', 2)
        self.observed_task('刚好在截止时批改的问题。', 8, success=True)
        self.observed_task('跨越截止点的问题。', 9, grade_at=12)
        late = self.observed_task('截止后的第一道新问题。', 15, success=True)
        self.observed_task('截止后的第一道新问题。', 18)
        self.observed_task('已通过提示披露答案的问题。', 21, disclosed=True)
        self.observed_task('有多个方法先后介入的问题。', 24, overlap=True)
        last = self.observed_task('可用于留出的最后一道问题。', 27)
        frame = self.frame(10, 1)
        future = self.frame(11, 2)

        packet = self.packet()
        self.assertEqual(packet['provenance']['split_note'], f'sdtm_temporal_cutoff:{self.stamp(10).isoformat()}')
        self.assertIn(f'sdtm_frame_id={frame.pk} ', packet['protocol']['note'])
        self.assertIn(frame.program.digest, packet['protocol']['note'])
        self.assertNotIn(f'sdtm_frame_id={future.pk} ', packet['protocol']['note'])
        self.assertEqual(packet['development'], {'goal': '评估缓存理解。', 'failure': '截止时已批改的观察结果共 2 条，其中失败 1 条。'})
        self.assertEqual(packet['cases'], [{'id': str(task.pk), 'task_id': str(task.pk)} for task in (late, last)])
        self.assertEqual(packet['anchors'], [
            {'case_id': str(late.pk), 'source': 'objective_answer_key', 'expected_score': 1.0, 'expected_independent_support': True},
            {'case_id': str(last.pk), 'source': 'objective_answer_key', 'expected_score': 0.0, 'expected_independent_support': False}])
        self.assertEqual(self.packet('G')['anchors'], [])
        with self.assertRaises(ValidationError):
            build_sdtm_shadow_packet(self.project, kind='G', cutoff_at=self.stamp(30), baseline_instruction='使用题目标准。')
        self.student.is_course_student = False
        self.student.save(update_fields=['is_course_student'])
        with self.assertRaises(PermissionDenied):
            self.packet()

    @override_settings(DEBUG=True, UNIMIND_LEARNING_RUNTIME='legacy', UNIMIND_ULR_PROTOTYPE=True,
        UNIMIND_DSH_GENERATION_ENABLED=True, UNIMIND_DSH_FIXTURE_URL='http://127.0.0.1:9999')
    def test_live_e_attests_frozen_anchors_and_calls_native_provider(self):
        self.observed_task('留出测试中的独立作答。', 13, success=True)
        packet = self.packet()

        def provider(messages, *args, **kwargs):
            material = json.loads(messages[-1]['content'])
            for key in ('anchors', 'expected_score', 'expected_independent_support'):
                self.assertNotIn(f'"{key}"', json.dumps(material))
            self.assertEqual(kwargs['max_retries'], 0)
            content = {'instruction': '比较学习者作答与标准。'} if 'kind' in material else {
                'score': .75, 'independent_support': True, 'reason': 'mock'}
            return {'choices': [{'message': {'content': json.dumps(content)}, 'finish_reason': 'stop'}]}

        with patch('ai_engine.service.AIEngine.call_provider', side_effect=provider) as native:
            report = run_shadow(self.project, 'E', packet, live_model=True)
            self.assertEqual(native.call_count, 3)
            packet['anchors'][0]['expected_score'] = .5
            tampered = run_shadow(self.project, 'E', packet, live_model=True)
        self.assertEqual(report['anchor_validation'], 'objective_answer_key_verified')
        self.assertEqual(report['status'], 'evaluated_objective_anchors')
        self.assertEqual(report['scope']['split'], 'sdtm_temporal_holdout')
        self.assertEqual(report['model']['adapter'], 'ulr_native')
        self.assertFalse(any(report[key] for key in ('anchors_sent_to_models', 'activated', 'eligible', 'learning_effect_verified')))
        self.assertEqual(tampered['anchor_validation'], 'operator_supplied_not_attested')

    def decision(self, message, point, *, first, source=None, frame=None, randomized=True):
        actions = ('delayed-v1', 'immediate-v1') if point == 'recheck_timing' else (f'private:{self.strategy}', 'public:1')
        candidates = [{'action': action, 'propensity': propensity, 'kind': kind,
                       'method_id': method_id, 'method_digest': None, 'task_id': None}
                      for action, propensity, kind, method_id in zip(actions, (.25, .75), ('private', 'public'), (self.strategy, 1))]
        chosen = candidates[0 if first else 1]
        mode = 'stratified_random' if point == 'recheck_timing' else 'bounded_exploration'
        return TeachingDecisionLog.objects.create(owner=self.user, project=self.project, message=message, task=source,
            decision_point=point, selection_mode=mode if randomized else 'deterministic', candidates=candidates,
            selected_action=chosen['action'], propensity=chosen['propensity'] if randomized else None,
            sdtm_frame_id=frame.pk if frame else None, sdtm_program_digest=frame.program.digest if frame else '',
            policy_version='smoke-s1', exposure={'status': 'assigned'})

    def recheck(self, minute, *, first, randomized=True, disclosed=False, frame=None):
        with self.at(minute):
            source = self.task(f'复测的原始题目 {minute}。')
            message = self.message()
            log = self.decision(message, 'recheck_timing', first=first, source=source, frame=frame, randomized=randomized)
            task = self.task(f'复测需要使用的新题 {minute}。', source=source)
        with self.at(minute + 1):
            # A delayed decision may only be linked by the follow-up task.
            reply = self.reply(message, {} if first else {'recheck_task_id': str(task.pk)})
            if first and not disclosed:
                teaching_sidecar.record_exposure_presentation(self.user, message_id=reply.pk, surface='recheck_card')
            if disclosed:
                self.disclose(task)
        with self.at(minute + 2):
            self.grade(task, success=first)
        return log

    def method(self, minute, *, first, grades, disclosed=False):
        with self.at(minute):
            message = self.message()
            log = self.decision(message, 'method_ranking', first=first)
            use = self.use(message)
        with self.at(minute + 1):
            self.reply(message)
            tasks = [self.task(f'使用方法的独立应用题 {minute} {index}。', use=use) for index in range(len(grades))]
            if disclosed:
                self.disclose(tasks[0])
        with self.at(minute + 2):
            for task, success in zip(tasks, grades):
                self.grade(task, success=success)
        return log

    def test_recheck_replay_uses_logged_propensities_and_excludes_bad_support(self):
        self.recheck(4, first=False)
        frame = self.frame(10, 1)
        first = self.recheck(11, first=True, frame=frame)
        second = self.recheck(15, first=False)
        self.recheck(19, first=False, randomized=False)
        self.recheck(23, first=False, disclosed=True)
        point = 'recheck_timing'
        dataset = build_s_replay_dataset(self.project, decision_point=point, cutoff_at=self.stamp(10))
        self.assertEqual([row['decision_id'] for row in dataset['rows']], [first.pk, second.pk])
        self.assertEqual(dataset['sdtm_frame_id'], frame.pk)
        self.assertEqual(dataset['rows'][0]['sdtm_frame_id'], frame.pk)
        self.assertTrue(dataset['rows'][0]['presented'])
        self.assertFalse(dataset['rows'][1]['presented'])
        self.assertEqual(dataset['excluded_counts']['disclosed'], 1)
        self.assertEqual(dataset['excluded_counts']['not_randomized'], 1)

        report = run_s_offline_replay(self.project, decision_point=point, cutoff_at=self.stamp(10),
            target_policy={'delayed-v1': 2, 'immediate-v1': 2})
        self.assert_replay(report, ips=1, snips=.75, mean=.5)
        row = TeachingResearchRun.objects.get(pk=report['run_id'])
        self.assertEqual(row.kind, 'S')
        self.assertEqual(row.baseline.parent_id, row.candidate.parent_id)
        self.assertEqual(row.candidate.owner_id, self.user.pk)
        self.assertEqual(row.packet_hash, report['packet_hash'])
        self.assertEqual(row.report['rows'], dataset['rows'])

        zero = run_s_offline_replay(self.project, decision_point=point, cutoff_at=self.stamp(10),
            target_policy={'action': 'unsupported'})
        self.assertEqual((zero['status'], zero['ips_estimate'], zero['snips_estimate'], zero['effective_sample_size']),
            ('insufficient_randomized_support', 0, None, 0))
        json.dumps(zero, allow_nan=False)
        filtered = run_s_offline_replay(self.project, decision_point=point, cutoff_at=self.stamp(10),
            target_policy={'action': first.selected_action}, min_propensity=.9)
        self.assertEqual((filtered['status'], filtered['n'], filtered['estimator_rows_excluded'], filtered['ips_estimate']),
            ('insufficient_randomized_support', 0, 2, None))

    def assert_replay(self, report, *, ips, snips, mean):
        self.assertEqual(report['status'], 'evaluated_offline_replay')
        self.assertEqual(report['n'], 2)
        self.assertAlmostEqual(report['ips_estimate'], ips)
        self.assertAlmostEqual(report['snips_estimate'], snips)
        self.assertAlmostEqual(report['effective_sample_size'], 1.6)
        self.assertEqual(report['baseline_mean_reward'], mean)
        self.assertFalse(any(report[key] for key in ('causal_claim', 'activated', 'eligible', 'learning_effect_verified')))
        json.dumps(report, allow_nan=False)

    def test_method_replay_averages_independent_outcomes_per_assignment(self):
        first = self.method(11, first=True, grades=[True, False])
        second = self.method(15, first=False, grades=[False])
        self.method(19, first=True, grades=[True], disclosed=True)
        report = run_s_offline_replay(self.project, decision_point='method_ranking',
            target_policy={first.selected_action: .5, second.selected_action: .5})
        self.assertEqual([row['reward'] for row in report['rows']], [.5, 0])
        self.assertEqual(report['excluded_counts']['disclosed'], 1)
        self.assert_replay(report, ips=.5, snips=.375, mean=.25)

    def test_command_writes_private_s_report_with_no_overwrite(self):
        log = self.recheck(11, first=True)
        with TemporaryDirectory() as directory:
            target = Path(directory) / 's.json'
            policy = Path(directory) / 'policy.json'
            policy.write_text(json.dumps({'action': log.selected_action}))
            args = ('--project', str(self.project.pk), '--kind', 'S', '--from-sdtm', '--decision-point', 'recheck_timing',
                    '--target-policy', str(policy), '--cutoff', self.stamp(10).isoformat(), '--output', str(target))
            call_command('research_teaching_mechanisms', *args, stdout=StringIO())
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            saved = target.read_bytes()
            self.assertEqual(json.loads(saved)['status'], 'evaluated_offline_replay')
            with self.assertRaises(CommandError):
                call_command('research_teaching_mechanisms', *args, stdout=StringIO())
            self.assertEqual(target.read_bytes(), saved)
            self.assertEqual(TeachingResearchRun.objects.filter(kind='S').count(), 1)
