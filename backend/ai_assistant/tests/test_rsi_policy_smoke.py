"""Synthetic ULR assignments and method evidence through the versioned S policy."""
import json
import math
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase, override_settings
from django.utils import timezone

from ai_assistant.models import (
    AIChatMessage, Bot, Conversation, ConversationProject, LearningStrategyUse, ProjectLearning,
    ProjectLearningEvent, ProjectLearningTask, TaskMemoryFrame, TeachingDecisionLog,
)
from ai_assistant.services import learning_diagnostics, rsi_evidence, rsi_policy, task_memory_store, teaching_sidecar
from ai_assistant.services.dsh_xiaoyu import complete_turn
from ai_assistant.services.learning_library import strategy_operation
from ai_assistant.services.learning_tasks import create_task, sync_task_result
from ai_assistant.services.memory_core import record_completed_reply
from ai_assistant.services.project_learning import completed_learning_turn, turn_project_context
from ai_assistant.services.public_methods import publish_method
from quizzes.models import ExamQuestionResult, QuizExam
from users.models import CourseStudentStatus, User, WeeklyAIQuotaConfig


@override_settings(UNIMIND_LEARNING_RUNTIME='ulr', UNIMIND_CONTENT_INSTITUTION_ID='global',
    UNIMIND_PRISM_MODE='off', UNIMIND_SDTM_TASK_MEMORY_MODE='off', USE_MEM0=False,
    UNIMIND_ULR_RECHECK_STRATEGY='immediate', UNIMIND_RSI_ONLINE_POLICY_MODE='off',
    UNIMIND_RSI_POLICY_PROJECTS=frozenset(), UNIMIND_RSI_EXPLORATION_RATE=0.0)
class RSIPolicySmoke(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='rsi_policy_synthetic')
        CourseStudentStatus.objects.create(user=self.user, is_course_student=True)
        self.bot = Bot.objects.create(name='小宇', bot_type='planner', is_xiaoyu=True)
        self.project = ConversationProject.objects.create(user=self.user, name='解释缓存')
        self.room = Conversation.objects.create(user=self.user, bot=self.bot, project=self.project,
            conversation_id=uuid4(), title='学习')
        ProjectLearning.objects.create(project=self.project, planning_enabled=True, status='active',
            current_stage='start', plan={'stages': [{'id': 'start', 'title': '起点', 'knowledge_nodes': []}]})

    def message(self, content='请继续。', *, role='user', metadata=None):
        return AIChatMessage.objects.create(user=self.user, bot=self.bot, role=role, content=content,
            conversation_id=self.room.conversation_id, metadata=metadata or {})

    def reply(self, question):
        reply = self.message('先解释条件，再比较。', role='assistant',
            metadata={'learning_turn': completed_learning_turn(question.pk)})
        record_completed_reply(reply)
        return reply

    def recheck_turn(self, request_id, task):
        request = SimpleNamespace(user=self.user, ui_language='zh-CN', data={
            'request_id': str(request_id), 'conversation_id': str(self.room.conversation_id), 'message': '做完了。'})
        with patch('ai_assistant.services.ulr_runtime.run_turn', return_value=('看评阅。', [], str(task.pk), None, None, {})), \
                patch('ai_assistant.services.ulr_teaching.selected_task', return_value=task), \
                patch('ai_assistant.services.ulr_teaching.supports_objective_evidence', return_value=True), \
                patch('ai_assistant.services.ulr_teaching.verified_task_events', return_value={'events': [
                    (SimpleNamespace(content={'assistance': 'hint', 'outcome': 'success', 'result_id': 713}), task, None)]}), \
                patch('ai_assistant.services.ulr_teaching.create_recheck', return_value=None), \
                patch('ai_assistant.services.dsh_xiaoyu.extract_memories_async'):
            return complete_turn(request, self.bot, self.room.conversation_id, '做完了。', lambda event: None, ulr=True)

    def practice(self):
        WeeklyAIQuotaConfig.objects.update_or_create(pk=1, defaults={'course_calls': 20})
        return ProjectLearningTask.objects.create(project=self.project, stage_id='start', title='原题',
            instructions='自己解释。', question_ids=[], question_snapshot={}, mode='apply')

    def test_off_preserves_the_exact_ulr_metadata_shape(self):
        self.assertEqual(rsi_policy.policy_mode(self.project.pk), 'off')
        result = self.recheck_turn(uuid4(), self.practice())
        self.assertEqual(result['metadata']['ulr_teaching'], {
            'strategy': 'immediate-v1', 'source_result_id': 713, 'remaining_turns': 0, 'action': 'no_question'})
        log = TeachingDecisionLog.objects.get()
        self.assertEqual(log.selection_mode, 'deterministic')
        self.assertIsNone(log.propensity)
        self.assertTrue(all(row['propensity'] is None for row in log.candidates))

    @override_settings(UNIMIND_RSI_ONLINE_POLICY_MODE='active', UNIMIND_RSI_EXPLORATION_RATE=0.4)
    def test_active_recheck_retries_and_completes_with_sdtm_and_s_lineage(self):
        task = self.practice()
        readout = task_memory_store.prepare(self.project, self.user)
        frame = TaskMemoryFrame.objects.get(pk=readout['frame_id'])
        request_id = uuid4()
        with self.settings(UNIMIND_RSI_POLICY_PROJECTS=frozenset({self.project.pk})):
            result = self.recheck_turn(request_id, task)
            self.assertEqual(self.recheck_turn(request_id, task), result)
            log = TeachingDecisionLog.objects.get()
            self.assertEqual(rsi_policy.select_recheck_timing(self.project, task, log.message, source_result_id=713),
                (log.selected_action, log))
        draw = int(sha256(f'recheck:{self.project.pk}:713:recheck-timing-s1'.encode()).hexdigest(), 16) / (1 << 256)
        selected = 'delayed-v1' if draw < 0.4 else 'immediate-v1'
        self.assertEqual(log.selected_action, selected)
        self.assertEqual(log.selection_mode, 'stratified_random')
        self.assertEqual(log.candidates, [
            {'action': 'delayed-v1', 'delay_turns': 2, 'propensity': 0.4},
            {'action': 'immediate-v1', 'delay_turns': 0, 'propensity': 0.6}])
        self.assertTrue(math.isfinite(log.propensity) and 0 < log.propensity <= 1)
        self.assertEqual(result['metadata']['ulr_teaching']['decision_id'], log.pk)
        self.assertEqual(result['metadata']['ulr_teaching']['propensity'], log.propensity)
        self.assertEqual((log.mechanism.kind, log.sdtm_frame_id, log.sdtm_program_digest),
            ('S', frame.pk, frame.program.digest))
        self.assertEqual(log.answer_id, result['message_id'])
        self.assertEqual(log.exposure, {'status': 'reply_completed', 'reply_id': log.answer_id,
            'reply_hash': teaching_sidecar.canonical_hash(log.answer.content),
            'completed_at': log.answer.metadata['learning_turn']['completed_at'],
            'saved_at': log.answer.timestamp.isoformat(), 'presentation': 'unknown', 'adherence': 'unverified'})
        continued = self.message()
        strategy, assignment = rsi_policy.select_recheck_timing(self.project, task, continued,
            source_result_id=713, prior_decision=result['metadata']['ulr_teaching'])
        self.assertEqual(strategy, selected)
        self.assertIsNone(assignment)
        self.assertFalse(continued.teaching_decisions.exists())

    @override_settings(UNIMIND_RSI_ONLINE_POLICY_MODE='shadow', UNIMIND_RSI_EXPLORATION_RATE=0.4)
    def test_shadow_keeps_the_baseline_and_logs_the_alternative(self):
        task = self.practice()
        with self.settings(UNIMIND_RSI_POLICY_PROJECTS=frozenset({self.project.pk})), \
                patch('ai_assistant.services.rsi_policy._draw', return_value=0):
            result = self.recheck_turn(uuid4(), task)
        log = TeachingDecisionLog.objects.get()
        self.assertEqual(result['metadata']['ulr_teaching']['strategy'], 'immediate-v1')
        self.assertEqual(log.selection_mode, 'shadow_only')
        self.assertEqual(log.context_snapshot['shadow_recommendation'], 'delayed-v1')
        self.assertIsNone(log.propensity)

    @override_settings(UNIMIND_RSI_ONLINE_POLICY_MODE='active', UNIMIND_RSI_EXPLORATION_RATE=0.4)
    def test_non_whitelisted_project_uses_original_order_and_never_draws(self):
        task, message = self.practice(), self.message()
        public = [{'method_id': 2}, {'method_id': 1}]
        with patch('ai_assistant.services.rsi_policy._draw', side_effect=AssertionError('unapproved draw')):
            recheck, log = rsi_policy.select_recheck_timing(self.project, task, message, source_result_id=713)
            ranked = rsi_policy.rank_method_candidates(self.project, message, public_methods=public)
        self.assertEqual(recheck, 'immediate-v1')
        self.assertEqual(ranked['public_methods'], public)
        self.assertEqual(log.selection_mode, 'deterministic')
        self.assertFalse(message.teaching_decisions.exclude(propensity=None).exists())

    def task(self, prompt, use=None):
        return create_task(self.project, {'stage_id': 'start', 'title': '缓存边界', 'instructions': '自己解释。',
            'purpose': 'recheck', 'strategy_use_id': use.pk if use else None,
            'definition': {'prompt': prompt, 'response_type': 'explanation', 'criteria': ['说明访问过程']}})

    def private_use(self, strategy_id, message):
        result = strategy_operation(self.project, {'action': 'apply', 'strategy_id': strategy_id,
            'reason': '比较缓存命中与未命中。'}, message=message)
        return LearningStrategyUse.objects.get(pk=result['use_id'])

    def grade(self, task, *, success=False):
        maximum = task.question_snapshot['0']['max_score']
        score = maximum if success else 0
        exam = QuizExam.objects.create(user=self.user, status='completed', total_questions=1, graded_count=1,
            total_score=score, max_score=maximum)
        task.exam, task.assistance = exam, 'independent'
        task.save(update_fields=['exam', 'assistance'])
        sync_task_result(ExamQuestionResult.objects.create(exam=exam, score=score, max_score=maximum,
            user_answer='自己的解释', status='graded', graded_at=timezone.now(), question_snapshot=task.question_snapshot['0']))

    @override_settings(UNIMIND_SDTM_TASK_MEMORY_MODE='active', UNIMIND_SDTM_STRUCTURED_DIAGNOSTICS=True)
    def test_method_ranking_flows_through_actual_candidates_and_both_evidence_ledgers(self):
        event = ProjectLearningEvent.objects.create(project=self.project, message=self.message(), kind='progress',
            content={'strategy': '按是否命中划分情境。'})
        strategy_id = strategy_operation(self.project, {'action': 'save', 'event_id': event.pk})['strategy_id']
        method = publish_method({'key': 'compare', 'instruction': '比较两个情境。', 'requires': {'purpose': 'recheck'},
            'source': '合成测试'}, request_key='rsi-policy')
        with self.settings(UNIMIND_SDTM_DIAGNOSTIC_PROJECTS=frozenset({self.project.pk})):
            for case, prompt in [
                ('eligible', '请解释缓存未命中的过程。'), ('repeat', '请解释缓存未命中的过程。'),
                ('disclosed', '请说明读取路径。'), ('unconfirmed', '请解释命中时的访问过程。'),
            ]:
                trigger = self.message()
                teaching_sidecar.freeze_turn(self.project, trigger, {})
                use = self.private_use(strategy_id, trigger)
                self.reply(trigger)
                task = self.task(prompt, use)
                if case == 'disclosed':
                    learning_diagnostics.certify_task(task, schema='cache-v1', bindings={'instance': str(task.pk)},
                        decisions=['miss'])
                    question = self.message('未命中会访问哪里？')
                    reply = self.reply(question)
                    learning_diagnostics.certify_text_delivery(task, question, reply, span=(0, len(reply.content)),
                        quote=reply.content, decisions=['miss'])
                self.grade(task, success=case == 'eligible')
                if case == 'unconfirmed':
                    trigger.metadata['runtime_request_id'] = str(uuid4())
                    trigger.save(update_fields=['metadata'])
            target = self.task('请解释缓存命中的代价。')
            with self.settings(UNIMIND_RSI_ONLINE_POLICY_MODE='active', UNIMIND_RSI_EXPLORATION_RATE=0.4,
                    UNIMIND_RSI_POLICY_PROJECTS=frozenset({self.project.pk})):
                for index, kind in enumerate(('private', 'public')):
                    question = self.message()
                    claims = {'message_id': question.pk, 'bot_id': self.bot.pk,
                        'conversation_id': str(self.room.conversation_id)}
                    with patch('ai_assistant.services.rsi_policy._draw', return_value=index):
                        context = json.loads(turn_project_context(self.user, claims).split('\n', 2)[2])
                    question.refresh_from_db()
                    log = question.teaching_decisions.get()
                    self.assertEqual(log.selection_mode, 'bounded_exploration')
                    self.assertEqual(log.sdtm_frame_id, context['memory_read']['frame_id'])
                    self.assertEqual(log.sdtm_program_digest, context['memory_read']['program_digest'])
                    self.assertEqual(context['method_candidate_order'], [item['action'] for item in log.candidates])
                    candidates = {item['kind']: item for item in log.candidates}
                    self.assertEqual(len(candidates), len(context['public_methods']) + len(context['private_strategies']))
                    self.assertEqual(candidates['private']['posterior_mean'], 2 / 3)
                    self.assertEqual(candidates['public']['posterior_mean'], 1 / 2)
                    self.assertEqual(candidates['private']['propensity'], 0.8)
                    self.assertEqual(candidates['public']['propensity'], 0.2)
                    self.assertEqual(log.selected_action, candidates[kind]['action'])
                    with patch('ai_assistant.services.rsi_policy._draw', side_effect=AssertionError('unexpected redraw')):
                        ranked = rsi_policy.rank_method_candidates(self.project, question,
                            public_methods=context['public_methods'], private_strategies=context['private_strategies'])
                    self.assertEqual(ranked['method_candidate_order'], context['method_candidate_order'])
                    if kind == 'private':
                        use = self.private_use(strategy_id, question)
                        self.assertEqual(use.decision['decision_log_id'], log.pk)
                        self.assertEqual(use.decision['model_visible_candidate_set'], log.candidates)
                    else:
                        strategy_operation(self.project, {'action': 'apply_public', 'task_id': target.pk,
                            'public_method_id': method.pk, 'method_digest': method.digest, 'reason': '比较两个条件。'},
                            message=question)
                    self.reply(question)
                    row = next(row for row in rsi_evidence.project_method_evidence(self.project)
                        if row['question_id'] == question.pk)
                    self.assertEqual(row['selection'], {'selection_kind': 'bounded_exploration',
                        'propensity': candidates[kind]['propensity'], 'model_visible_candidate_set': log.candidates})
