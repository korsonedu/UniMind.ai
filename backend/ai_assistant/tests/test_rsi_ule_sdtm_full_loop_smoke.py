"""Exercise the RSI loop with persisted synthetic learning turns and no model traffic."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.test import TransactionTestCase, override_settings
from django.utils import timezone as django_timezone
from rest_framework.test import APIClient

from ai_assistant.models import (
    AIChatMessage, Bot, Conversation, ConversationProject, LearningStrategyUse, ProjectLearning,
    ProjectLearningEvent, TaskMemoryFrame, TeachingDecisionLog, TeachingMechanismActivation,
    TeachingMechanismVersion, TeachingResearchRun,
)
from ai_assistant.services import (
    learning_diagnostics, task_memory_store, teaching_shadow, teaching_sidecar,
)
from ai_assistant.services.decision import rsi_governance, rsi_policy
from ai_assistant.services.state.rsi import rsi_dataset, rsi_evidence
from ai_assistant.services.dsh_xiaoyu import complete_turn
from ai_assistant.services.learning_library import strategy_operation
from ai_assistant.services.learning_tasks import create_task, sync_task_result
from ai_assistant.services.public_methods import publish_method
from ai_engine.service import AIEngine
from quizzes.models import ExamQuestionResult, KnowledgePoint, Question, QuizExam
from users.models import CourseStudentStatus, User, WeeklyAIQuotaConfig
from users.permissions import is_platform_admin


@override_settings(
    UNIMIND_LEARNING_RUNTIME='ulr', UNIMIND_CONTENT_INSTITUTION_ID='global', UNIMIND_PRISM_MODE='off',
    UNIMIND_SDTM_TASK_MEMORY_MODE='active', UNIMIND_SDTM_STRUCTURED_DIAGNOSTICS=True,
    UNIMIND_ULR_RECHECK_STRATEGY='immediate', UNIMIND_RSI_ONLINE_POLICY_MODE='active',
    UNIMIND_RSI_EXPLORATION_RATE=0.4, USE_MEM0=False,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class RSIULESDTMFullLoopSmoke(TransactionTestCase):
    start = datetime(2026, 11, 25, tzinfo=timezone.utc)

    def setUp(self):
        self.user = User.objects.create_user(username='rsi_loop_learner')
        CourseStudentStatus.objects.create(user=self.user, is_course_student=True)
        WeeklyAIQuotaConfig.objects.update_or_create(pk=1, defaults={'course_calls': 100})
        self.admin = User.objects.create_superuser(username='rsi_loop_admin')
        self.project = self.make_project('缓存')
        self.bot, _ = Bot.objects.get_or_create(is_xiaoyu=True, defaults={'name': '小宇', 'bot_type': 'planner'})
        self.room = self.make_room()
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.enterContext(self.settings(
            UNIMIND_DIRECTUS_ADMIN_MAP={str(uuid4()): self.admin.pk, str(uuid4()): self.admin.pk + 1},
            UNIMIND_RSI_POLICY_PROJECTS=frozenset({self.project.pk}),
            UNIMIND_SDTM_DIAGNOSTIC_PROJECTS=frozenset({self.project.pk}),
        ))
        self.enterContext(patch('ai_assistant.services.dsh_xiaoyu.extract_memories_async'))
        self.enterContext(patch.object(AIEngine, 'call_provider', side_effect=self.model_reply))

    def make_project(self, name):
        project = ConversationProject.objects.create(user=self.user, name=name)
        ProjectLearning.objects.create(project=project, planning_enabled=True, status='active', current_stage='start',
            plan={'goal': '解释缓存', 'stages': [{'id': 'start', 'title': '起点', 'knowledge_nodes': []}]})
        return project

    def make_room(self):
        return Conversation.objects.create(user=self.user, bot=self.bot, project=self.project,
            conversation_id=uuid4(), title='缓存学习')

    def at(self, minute):
        return patch.object(django_timezone, 'now', return_value=self.start + timedelta(minutes=minute))

    def message(self):
        return AIChatMessage.objects.create(user=self.user, bot=self.bot, conversation_id=self.room.conversation_id,
            role='user', content='比较命中与未命中。')

    @staticmethod
    def model_reply(*args, **kwargs):
        return {'choices': [{'finish_reason': 'stop', 'message': {'content': '请比较命中与未命中的条件。'}}]}

    def turn(self, room, *, task=None, message='继续学习目标。'):
        data = {'request_id': str(uuid4()), 'conversation_id': str(room.conversation_id), 'message': message}
        if task:
            data['learning_activity'] = {'task_id': str(task.pk)}
        request = SimpleNamespace(user=self.user, data=data, ui_language='zh-CN')
        result = complete_turn(request, self.bot, room.conversation_id, message, lambda event: None, ulr=True)
        json.dumps(result, allow_nan=False)
        self.assertEqual(result['engine'], 'ulr')
        return AIChatMessage.objects.get(pk=result['message_id'])

    def task(self, project, prompt, *, use=None, question=None, purpose='practice'):
        material = {'question_ids': [question.pk]} if question else {'definition': {
            'prompt': prompt, 'response_type': 'objective', 'options': {'A': '命中', 'B': '未命中'},
            'reference_answer': 'A', 'criteria': ['区分访问条件'],
        }}
        return create_task(project, {'stage_id': 'start', 'title': prompt, 'instructions': '独立作答。',
            'strategy_use_id': use.pk if use else None, 'purpose': purpose, **material})

    def grade(self, task, *, success=True, assistance='independent'):
        question_id = task.question_ids[0] if task.question_ids else None
        snapshot = task.question_snapshot[str(question_id or 0)]
        maximum = snapshot['max_score']
        score = maximum if success else 0
        task.exam = QuizExam.objects.create(user=self.user, status='completed', total_questions=1,
            graded_count=1, total_score=score, max_score=maximum)
        task.assistance = assistance
        task.save(update_fields=['exam', 'assistance'])
        result = ExamQuestionResult.objects.create(exam=task.exam, question_id=question_id,
            score=score, max_score=maximum, user_answer='A' if success else 'B',
            status='graded', graded_at=django_timezone.now(), question_snapshot=snapshot)
        sync_task_result(result)
        return result

    def question(self, point, prompt):
        return Question.objects.create(knowledge_point=point, text=prompt, q_type='objective',
            options=['命中', '未命中'], correct_answer='A')

    def present(self, reply, *, surface, card_type=''):
        response = self.client.post('/api/ai/learning/exposure/present/',
            {'message_id': reply.pk, 'surface': surface, 'card_type': card_type}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        json.dumps(response.data, allow_nan=False)
        return response.data

    def assert_logged_turn(self, reply, point):
        log = reply.committed_teaching_decisions.get(decision_point=point)
        self.assertTrue(math.isfinite(log.propensity) and 0 < log.propensity < 1)
        frame = TaskMemoryFrame.objects.get(pk=log.sdtm_frame_id, memory__project=self.project, memory__owner=self.user)
        self.assertEqual(log.sdtm_program_digest, frame.program.digest)
        self.assertEqual(log.exposure['status'], 'reply_completed')
        self.assertEqual(log.exposure['reply_id'], reply.pk)
        self.assertEqual(log.exposure['reply_hash'], teaching_sidecar.canonical_hash(reply.content))
        frozen = log.message.metadata['rsi_sidecar']
        self.assertEqual(frozen['project_id'], self.project.pk)
        self.assertEqual(log.mechanism_id, frozen['bundle']['S']['id'])
        for kind, module in (('G', 'ulr_runtime'), ('S', 'ulr_teaching'), ('M', 'task_memory_store')):
            version = TeachingMechanismVersion.objects.get(pk=frozen['bundle'][kind]['id'])
            self.assertEqual(version.digest, frozen['bundle'][kind]['digest'])
            path = f'ai_assistant/services/{module}.py'
            self.assertEqual(version.content['sources'][path], sha256(teaching_sidecar._source_bytes(path)).hexdigest())
        json.dumps([frozen, log.candidates, log.context_snapshot, log.exposure], allow_nan=False)
        return log

    def observe_method(self, minute, label, *, success=True, disclosed=False):
        tool = 'manage_learning_strategies'

        def use_strategy(messages, **kwargs):
            if messages[-1]['role'] == 'tool':
                return self.model_reply()
            self.assertIn(tool, {item['function']['name'] for item in kwargs['tools']})
            arguments = {'action': 'apply', 'strategy_id': self.strategy, 'reason': '比较两种访问条件。'}
            call = {'id': 'apply-method', 'type': 'function',
                    'function': {'name': tool, 'arguments': json.dumps(arguments)}}
            return {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [call]}}]}

        with self.at(minute), patch.object(AIEngine, 'call_provider', side_effect=use_strategy):
            reply = self.turn(self.room)
            log = self.assert_logged_turn(reply, 'method_ranking')
            use = LearningStrategyUse.objects.get(pk=reply.metadata['ulr_strategy_use_ids'][0])
            self.assertEqual(use.decision['decision_log_id'], log.pk)
        with self.at(minute + 1):
            first = self.present(reply, surface='chat_card')
            self.assertTrue(first['created'])
            self.assertEqual((first['updated_decisions'], first['updated_strategy_uses']), (1, 1))
        with self.at(minute + 2):
            again = self.present(reply, surface='chat_card')
            self.assertEqual(again, {**first, 'created': False, 'updated_decisions': 0, 'updated_strategy_uses': 0})
            log.refresh_from_db()
            use.refresh_from_db()
            for exposure in (log.exposure, use.exposure):
                self.assertEqual(exposure['status'], 'presented')
                self.assertEqual(exposure['presented_at'], first['presented_at'])
                self.assertEqual(exposure['adherence'], 'unverified')
            task = self.task(self.project, f'缓存客观题：{label}。', use=use)
            if disclosed:
                learning_diagnostics.certify_task(task, schema='cache-v1',
                    bindings={'instance': str(task.pk)}, decisions=['choice'])
                with patch.object(AIEngine, 'call_provider', return_value={'choices': [{
                    'finish_reason': 'stop', 'message': {'content': '这道题选 A。'},
                }]}):
                    answer = self.turn(self.room, task=task, message='这道题该选什么？')
                question = AIChatMessage.objects.get(pk=answer.metadata['learning_turn']['message_id'])
                learning_diagnostics.certify_text_delivery(task, question, answer,
                    span=(0, len(answer.content)), quote=answer.content, decisions=['choice'])
        with self.at(minute + 3):
            self.grade(task, success=success)
        return task

    def observe_recheck(self, minute, label):
        with self.at(minute):
            point = KnowledgePoint.objects.create(name=label)
            source = self.task(self.project, label, question=self.question(point, f'{label}的原题'))
            self.question(point, f'{label}的迁移题')
            result = self.grade(source, assistance='hint')
            room = self.make_room()
        with self.at(minute + 1):
            reply = self.turn(room, task=source, message='请复盘我的作答。')
            log = self.assert_logged_turn(reply, 'recheck_timing')
        for step in range(rsi_policy.RECHECK_DELAYS[log.selected_action]):
            with self.at(minute + 2 + step):
                reply = self.turn(room, task=source, message='继续复盘。')
        self.assertEqual(reply.metadata['ulr_teaching']['action'], 'offer_recheck')
        followup = source.followup_tasks.get()
        self.assertEqual(reply.metadata['ulr_teaching']['recheck_task_id'], str(followup.pk))
        with self.at(minute + 4):
            self.present(reply, surface='recheck_card', card_type='data_card')
        with self.at(minute + 5):
            self.grade(followup)
        return log, result

    def test_full_closed_loop_online_to_governance_and_rollback(self):
        assigned = []

        complete = teaching_sidecar.record_turn_completion

        def record_completion(reply):
            assigned.extend(reply.committed_teaching_decisions.values_list('pk', 'exposure__status'))
            complete(reply)

        self.enterContext(patch.object(teaching_sidecar, 'record_turn_completion', side_effect=record_completion))
        with self.at(0):
            baseline = task_memory_store.prepare(self.project, self.user)
            self.assertEqual(task_memory_store.restore(baseline['frame_id'], self.user), baseline['packet'])
            source = ProjectLearningEvent.objects.create(project=self.project, message=self.message(),
                kind='progress', content={'strategy': '比较访问条件。'})
            self.strategy = strategy_operation(self.project, {'action': 'save', 'event_id': source.pk})['strategy_id']
            publish_method({'key': 'practice-contrast', 'instruction': '比较两种访问条件。',
                'requires': {'purpose': 'practice'}, 'source': '合成测试'}, request_key='rsi-loop-seed')
            self.task(self.project, '待做的对照练习')
        pre = self.observe_method(1, '截止前', success=False)
        cutoff = self.start + timedelta(minutes=5)
        early = self.observe_method(6, '截止后解释', success=True)
        late = self.observe_method(11, '截止后验证', success=False)
        disclosed = self.observe_method(16, '同题答案已披露', disclosed=True)
        rechecks = [self.observe_recheck(minute, label) for minute, label in
                    ((21, '缓存容量'), (27, '访问延迟'), (33, '替换规则'))]
        logs = list(TeachingDecisionLog.objects.filter(project=self.project))
        self.assertCountEqual(assigned, [(log.pk, 'assigned') for log in logs])

        evidence = rsi_evidence.project_method_evidence(self.project)
        json.dumps(evidence, allow_nan=False)
        observed = {row['outcomes'][0]['task_id']: row for row in evidence}
        self.assertEqual(set(observed), {str(task.pk) for task in (pre, early, late, disclosed)})
        for task in (pre, early, late):
            row = observed[str(task.pk)]
            self.assertTrue(row['eligible_for_eval'])
            self.assertEqual(row['outcomes'][0]['label_source'], 'objective_answer_key')
            self.assertEqual(row['outcomes'][0]['status'], rsi_evidence.INDEPENDENT)
            self.assertFalse(row['causal_claim'])
        row = observed[str(disclosed.pk)]
        self.assertFalse(row['eligible_for_eval'])
        self.assertIn('same_instance_solution_disclosed', row['outcomes'][0]['reasons'])

        candidate_instruction = '先明确访问条件，再用独立的新题区分。'

        def shadow_model(system, material, schema, max_tokens):
            self.assertFalse({'anchors', 'expected_score', 'expected_independent_support'} & material.keys())
            if 'kind' in material:
                output = {'instruction': candidate_instruction}
            elif 'method' in schema['properties']:
                output = {'method': system.splitlines()[-1], 'covered_subskills': ['区分访问条件'],
                          'independent_check': '用独立新题检查。'}
            elif 'case' in material:
                output = {'score': 0.8 if material['method']['method'] == candidate_instruction else 0.5,
                          'independent_support': False, 'reason': '合成方法代理评分'}
            else:
                success = material['id'] == str(early.pk)
                output = {'score': float(success), 'independent_support': success, 'reason': '合成答卷评分'}
            return output, {'observed_model': 'synthetic-smoke'}

        packets = {}
        for kind in ('G', 'E'):
            packet = rsi_dataset.build_sdtm_shadow_packet(self.project, kind=kind, cutoff_at=cutoff,
                baseline_instruction='按标准核对作答。', development_goal='比较缓存访问条件。')
            self.assertEqual(packet['development']['failure'], '截止时已批改的观察结果共 1 条，其中失败 1 条。')
            self.assertEqual(packet['cases'], [{'id': str(task.pk), 'task_id': str(task.pk)} for task in (early, late)])
            json.dumps(packet, allow_nan=False)
            packets[kind] = packet
        with patch.object(teaching_shadow, '_call_model', side_effect=shadow_model) as model:
            g, e = [teaching_shadow.run_shadow(self.project, kind, packets[kind], live_model=True) for kind in ('G', 'E')]
            self.assertEqual(model.call_count, 14)
        for report in (g, e):
            self.assertEqual(report['model']['adapter'], 'ulr_native')
            self.assertEqual(report['scope']['split'], 'sdtm_temporal_holdout')
            self.assertFalse(report['activated'])
        self.assertEqual(e['anchor_validation'], 'objective_answer_key_verified')
        self.assertEqual(e['status'], 'evaluated_objective_anchors')

        s = teaching_shadow.run_s_offline_replay(self.project, decision_point='recheck_timing', cutoff_at=cutoff,
            target_policy={'immediate-v1': 0.5, 'delayed-v1': 0.5})
        self.assertEqual(s['status'], 'evaluated_offline_replay')
        self.assertFalse(s['causal_claim'])
        self.assertEqual([row['decision_id'] for row in s['rows']], [log.pk for log, _ in rechecks])
        self.assertEqual(s['n'], 3)
        self.assertTrue(all(math.isfinite(s[key]) for key in ('ips_estimate', 'snips_estimate', 'effective_sample_size')))
        self.assertAlmostEqual(s['snips_estimate'], 1.0)
        failed = teaching_shadow.run_s_offline_replay(self.project, decision_point='recheck_timing',
            cutoff_at=self.start + timedelta(minutes=40), target_policy={'action': 'immediate-v1'})
        self.assertFalse(TeachingMechanismActivation.objects.exists())
        json.dumps([g, e, s, failed], allow_nan=False)
        for report in (g, e, s):
            gate = rsi_governance.evaluate_gate(report['run_id'])
            self.assertTrue(gate['passed'], gate)
        gate = rsi_governance.evaluate_gate(failed['run_id'])
        self.assertFalse(gate['passed'])
        self.assertIn('insufficient_randomized_decisions', gate['failures'])

        self.assertTrue(is_platform_admin(self.admin))
        with self.at(40):
            target = self.task(self.project, '等待新方法的复测', purpose='recheck')
            other = self.make_project('非灰度项目')
            self.task(other, '同样符合条件的复测', purpose='recheck')
            g_activation = rsi_governance.approve_and_activate(g['run_id'], self.admin, scope='project_canary',
                public_method_spec={'key': 'cache-holdout', 'requires': {'purpose': 'recheck'}, 'source': '合成审核'})
            s_activation = rsi_governance.approve_and_activate(s['run_id'], self.admin, scope='project_canary')
        for activation in (g_activation, s_activation):
            self.assertEqual(activation['status'], 'canary_active')
            self.assertEqual(activation['project_id'], self.project.pk)
            self.assertEqual(activation['approved_by_id'], self.admin.pk)

        program_id = g_activation['published_program_id']
        original_log, result = rechecks[0]
        with self.at(41):
            prepared = task_memory_store.prepare(self.project, self.user)
            frame = TaskMemoryFrame.objects.get(pk=prepared['frame_id'])
            routes = prepared['packet']['public_methods']
            route = next(row for row in routes if row['method_id'] == program_id)
            self.assertEqual(route['instruction'], candidate_instruction)
            self.assertEqual(route['binding']['task_id'], str(target.pk))
            self.assertNotIn(program_id, [row['method_id'] for row in
                task_memory_store.prepare(other, self.user)['packet']['public_methods']])
            strategy, log = rsi_policy.select_recheck_timing(self.project, original_log.task, self.message(),
                source_result_id=result.pk, sdtm_frame_id=frame.pk, sdtm_program_digest=frame.program.digest)
        self.assertEqual(log.mechanism_id, s_activation['mechanism_id'])
        self.assertEqual(log.policy_version, f"{rsi_policy.RECHECK_VERSION}:activation-{s_activation['activation_id']}")
        self.assertEqual(log.context_snapshot['activation_id'], s_activation['activation_id'])
        self.assertEqual(strategy, log.selected_action)
        self.assertEqual(log.propensity, 0.5)

        with self.at(42):
            for activation in (g_activation, s_activation):
                rollback = rsi_governance.rollback_activation(activation['activation_id'], self.admin)
                self.assertEqual((rollback['status'], rollback['rolled_back_by_id']), ('rolled_back', self.admin.pk))
        with self.at(43):
            self.assertNotIn(program_id, [row['method_id'] for row in
                task_memory_store.prepare(self.project, self.user)['packet']['public_methods']])
            restored = task_memory_store.restore(frame.pk, self.user)
            self.assertEqual(restored, prepared['packet'])
            self.assertEqual(task_memory_store.digest(restored), frame.packet_digest)
            strategy, log = rsi_policy.select_recheck_timing(self.project, original_log.task, self.message(),
                source_result_id=result.pk)
        self.assertEqual(strategy, original_log.selected_action)
        self.assertEqual((log.mechanism_id, log.policy_version, log.candidates, log.propensity),
            (original_log.mechanism_id, rsi_policy.RECHECK_VERSION, original_log.candidates, original_log.propensity))
        self.assertNotIn('activation_id', log.context_snapshot)
        json.dumps([prepared['packet'], restored, g_activation, s_activation], allow_nan=False)

    @override_settings(UNIMIND_RSI_ONLINE_POLICY_MODE='off')
    def test_master_kill_switch_off_bypasses_active_s_rollout(self):
        mechanism = teaching_sidecar.register_mechanism('S', {'probabilities': {'delayed-v1': 1.0}}, owner=self.user)
        run = TeachingResearchRun.objects.create(owner=self.user, project=self.project, kind='S',
            candidate=mechanism, packet_hash=mechanism.digest, protocol={}, report={})
        activation = TeachingMechanismActivation.objects.create(project=self.project, kind='S', scope='project_canary',
            decision_point='recheck_timing', mechanism=mechanism, research_run=run, status='canary_active')
        self.assertEqual(rsi_governance.active_s_policy(self.project.pk, 'recheck_timing'), activation)
        with self.at(0):
            point = KnowledgePoint.objects.create(name='关闭开关的缓存题')
            task = self.task(self.project, '原题', question=self.question(point, '如何判断缓存命中？'))
            result = self.grade(task, assistance='hint')
        with self.at(1):
            task_memory_store.prepare(self.project, self.user)
            reply = self.turn(self.room, task=task, message='请复盘我的作答。')
        self.assertEqual(reply.metadata['ulr_teaching'], {'strategy': 'immediate-v1',
            'source_result_id': result.pk, 'remaining_turns': 0, 'action': 'no_question'})
        log = reply.committed_teaching_decisions.get(decision_point='recheck_timing')
        self.assertEqual(log.selection_mode, 'deterministic')
        self.assertEqual(log.policy_version, rsi_policy.RECHECK_VERSION)
        self.assertNotEqual(log.mechanism_id, mechanism.pk)
        self.assertIsNone(log.propensity)
        self.assertTrue(all(row['propensity'] is None for row in log.candidates))
        json.dumps([reply.metadata, log.candidates, log.exposure], allow_nan=False)
