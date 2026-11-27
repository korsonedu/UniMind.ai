"""RSI provenance and native ULR observation with synthetic learning data."""
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.db import IntegrityError
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from ai_assistant.models import (
    AIChatMessage, Bot, Conversation, ConversationProject, LearningStrategy, LearningStrategyUse,
    ProjectLearning, ProjectLearningEvent, TeachingMechanismVersion,
)
from ai_assistant.services import teaching_sidecar, ulr_runtime
from ai_assistant.services.dsh_xiaoyu import complete_turn
from ai_assistant.services.learning_tasks import create_task
from ai_assistant.services.memory_core import record_completed_reply
from ai_assistant.services.project_learning import completed_learning_turn
from ai_assistant.services.ulr_tool_program import PRACTICE_NAME
from ai_engine.service import AICallError, AIEngine
from quizzes.models import KnowledgePoint, Question
from users.models import AIUsageReservation, CourseStudentStatus, User, WeeklyAIQuotaConfig


@override_settings(DEBUG=False, UNIMIND_LEARNING_RUNTIME='legacy', UNIMIND_ULR_PROTOTYPE=True,
    UNIMIND_PRISM_MODE='off', UNIMIND_SDTM_TASK_MEMORY_MODE='off', UNIMIND_SDTM_STRUCTURED_DIAGNOSTICS=False,
    UNIMIND_DSH_GENERATION_ENABLED=True, UNIMIND_DSH_GRADING_ENABLED=False, UNIMIND_DSH_XIAOYU_ENABLED=True,
    UNIMIND_ULR_RECHECK_STRATEGY='immediate', UNIMIND_RSI_ONLINE_POLICY_MODE='off', UNIMIND_RSI_EXPLORATION_RATE=0.0)
class RuntimeBundleSmoke(TestCase):
    def test_mechanisms_hash_native_sources_and_route_changes(self):
        baseline = teaching_sidecar.current_bundle()
        native = {
            'G': ('ulr_runtime', 'ulr_tool_program', 'ulr_capabilities', 'public_methods'),
            'S': ('ulr_teaching', 'public_methods', 'method_adoption', 'decision/rsi_policy', 'state/rsi/rsi_evidence'),
            'E': ('ulr_grading', 'ulr_structured', 'learning_diagnostics'),
            'M': ('teaching_sidecar', 'teaching_shadow', 'state/rsi/rsi_dataset', 'decision/rsi_governance'),
        }
        sdtm = ('task_memory_store', 'task_memory_projection', 'learning_continuity', 'fact_evidence',
                'prism_kernel', 'prism_memory', 'prism_feedback', 'memory_core', 'prism_outcomes')
        expected_routes = {
            'UNIMIND_DSH_GENERATION_ENABLED': True, 'UNIMIND_DSH_GRADING_ENABLED': False,
            'UNIMIND_DSH_XIAOYU_ENABLED': True, 'ulr_enabled': False, 'ulr_recheck_strategy': 'immediate',
            'prism_mode': 'off', 'sdtm_task_memory_mode': 'off', 'sdtm_structured_diagnostics': False,
            'rsi_online_policy_mode': 'off', 'rsi_exploration_rate': 0.0,
        }
        for kind, modules in native.items():
            content = TeachingMechanismVersion.objects.get(pk=baseline[kind]['id']).content
            self.assertEqual(content['schema'], 'rsi-sidecar-6ab-v1')
            self.assertEqual(content['routes'], expected_routes)
            self.assertFalse(content['candidate_activation'])
            self.assertFalse(content['provider_weights_pinned'])
            self.assert_source_hashes(content, modules)
        self.assertNotIn('ai_assistant/services/task_memory_store.py', content['sources'])
        for change, route, value in (
            ('UNIMIND_LEARNING_RUNTIME', 'ulr_enabled', 'ulr'),
            ('UNIMIND_ULR_RECHECK_STRATEGY', 'ulr_recheck_strategy', 'delayed'),
            ('UNIMIND_PRISM_MODE', 'prism_mode', 'shadow'),
            ('UNIMIND_SDTM_TASK_MEMORY_MODE', 'sdtm_task_memory_mode', 'active'),
            ('UNIMIND_SDTM_STRUCTURED_DIAGNOSTICS', 'sdtm_structured_diagnostics', True),
            ('UNIMIND_RSI_ONLINE_POLICY_MODE', 'rsi_online_policy_mode', 'shadow'),
            ('UNIMIND_RSI_EXPLORATION_RATE', 'rsi_exploration_rate', 0.4),
        ):
            with self.subTest(setting=change), override_settings(**{change: value}):
                current = teaching_sidecar.current_bundle()
                for kind in baseline:
                    self.assertNotEqual(baseline[kind]['digest'], current[kind]['digest'])
                memory = TeachingMechanismVersion.objects.get(pk=current['M']['id']).content
                self.assertEqual(memory['routes'][route], True if route == 'ulr_enabled' else value)
                if route in ('prism_mode', 'sdtm_task_memory_mode'):
                    self.assert_source_hashes(memory, sdtm)
                    self.assertEqual(memory['role'], f'sdtm_{value}')
        self.assertEqual(teaching_sidecar.current_bundle(), baseline)

    def assert_source_hashes(self, content, modules):
        for module in modules:
            path = f'ai_assistant/services/{module}.py'
            self.assertEqual(content['sources'][path], hashlib.sha256(teaching_sidecar._source_bytes(path)).hexdigest())


@override_settings(UNIMIND_LEARNING_RUNTIME='ulr', UNIMIND_CONTENT_INSTITUTION_ID='global',
    UNIMIND_PRISM_MODE='off', UNIMIND_SDTM_TASK_MEMORY_MODE='off', USE_MEM0=False,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class ULRObservationSmoke(TransactionTestCase):
    plan_arguments = {'revision': 0, 'plan': {'goal': '解释缓存', 'deadline': None, 'weekly_minutes': 30, 'stages': [{
        'id': 'start', 'title': '解释缓存', 'outcome': '解释容量与速度', 'task': '比较两个情境',
        'prerequisites': [], 'sources': []}]}, 'next_action': '自己解释', 'reason': '用户要求规划',
        'major_change': False, 'require_confirmation': True}

    def setUp(self):
        self.user = User.objects.create_user(username='rsi_ulr_synthetic')
        CourseStudentStatus.objects.create(user=self.user, is_course_student=True)
        WeeklyAIQuotaConfig.objects.update_or_create(pk=1, defaults={'course_calls': 20})
        self.bot, _ = Bot.objects.get_or_create(is_xiaoyu=True, defaults={'name': '小宇', 'bot_type': 'planner'})
        self.project = ConversationProject.objects.create(user=self.user, name='合成学习项目')
        self.state = ProjectLearning.objects.create(project=self.project, planning_enabled=True)
        self.room = Conversation.objects.create(user=self.user, bot=self.bot, project=self.project,
            conversation_id=uuid4(), title='学习')
        self.request_id = uuid4()
        self.enterContext(patch('ai_assistant.services.dsh_xiaoyu.extract_memories_async'))

    def ask(self, message, **extra):
        request = SimpleNamespace(user=self.user, ui_language='zh-CN', data={
            'request_id': str(self.request_id), 'conversation_id': str(self.room.conversation_id),
            'message': message, **extra})
        return complete_turn(request, self.bot, self.room.conversation_id, message, lambda event: None, ulr=True)

    def trigger(self):
        return AIChatMessage.objects.get(user=self.user, role='user', metadata__runtime_request_id=str(self.request_id))

    @staticmethod
    def answer():
        return {'choices': [{'finish_reason': 'stop', 'message': {'content': '先比较两个情境。'}}]}

    @staticmethod
    def tool_call(name, arguments):
        return {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [{
            'id': name, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(arguments)},
        }]}}]}

    def test_retry_reuses_the_freeze_and_commit_records_only_the_saved_plan(self):
        name = 'plan_learning_project'
        args = self.plan_arguments
        freezes = []

        def provider(messages, **kwargs):
            if messages[-1]['role'] == 'user':
                freezes.append(self.trigger().metadata['rsi_sidecar'])
                return self.tool_call(name, args)
            if len(freezes) == 1:
                raise AICallError('Synthetic provider failure', status_code=422)
            return self.answer()

        with patch.object(AIEngine, 'call_provider', side_effect=provider) as model, \
                patch.object(teaching_sidecar, 'current_bundle', wraps=teaching_sidecar.current_bundle) as bundle:
            with self.assertRaises(ulr_runtime.ULRTurnUnavailable):
                self.ask('请制定一份学习计划，等我确认。')
            self.assertFalse(AIChatMessage.objects.filter(user=self.user).exists())
            client = APIClient()
            client.force_authenticate(self.user)
            recovery = client.get(f'/api/ai/chat-requests/{self.request_id}/').data
            self.assertEqual(recovery['status'], 'failed')
            self.assertNotIn('rsi_sidecar', recovery['response'])
            reply = self.ask('请制定一份学习计划，等我确认。')
            self.assertEqual(self.ask('请制定一份学习计划，等我确认。'), reply)
            self.assertEqual(model.call_count, 4)
            bundle.assert_called_once()
        self.assertEqual(freezes, [self.trigger().metadata['rsi_sidecar']] * 2)
        entry, = self.trigger().metadata['rsi_observations']
        self.assertEqual((entry['tool'], entry['channel'], entry['arguments_hash']),
                         (name, 'ulr_project_commit', teaching_sidecar.canonical_hash(args)))
        self.assertRegex(entry['result_hash'], r'^[0-9a-f]{64}$')
        self.assertTrue(reply['metadata']['ulr_plan']['pending_plan'])

    def test_direct_practice_program_and_its_reads_are_hashed(self):
        point = KnowledgePoint.objects.create(name='缓存命中')
        Question.objects.create(knowledge_point=point, text='合成题目', options=['甲', '乙'], correct_answer='A')
        run_program = ulr_runtime.run_program

        def run(arguments, *args, **kwargs):
            self.assertEqual(self.trigger().metadata['rsi_sidecar']['project_id'], self.project.pk)
            result = run_program(arguments, *args, **kwargs)
            program_entry.update(arguments_hash=teaching_sidecar.canonical_hash(arguments),
                                 result_hash=teaching_sidecar.canonical_hash(result))
            return result

        program_entry = {'tool': PRACTICE_NAME, 'channel': 'ulr_program'}
        with patch.object(ulr_runtime, 'run_program', side_effect=run), patch.object(AIEngine, 'call_provider') as model:
            response = self.ask('请给我1道「缓存命中」知识点的练习题。只要练习卡。')
        model.assert_not_called()
        entries = self.trigger().metadata['rsi_observations']
        self.assertIn(program_entry, entries)
        self.assertEqual({row['tool'] for row in entries}, {PRACTICE_NAME, 'search_knowledge_tree', 'get_practice_questions'})
        self.assertEqual(response['metadata']['dsh_cards'][0]['type'], 'practice_quiz')

    def test_task_turn_freezes_before_teaching_and_exposes_only_confirmed_uses(self):
        self.state.status = 'active'
        self.state.current_stage = 'start'
        self.state.plan = {'stages': [{'id': 'start', 'title': '解释缓存', 'knowledge_nodes': []}]}
        self.state.save()
        point = KnowledgePoint.objects.create(name='缓存')
        question = Question.objects.create(knowledge_point=point, text='合成题目', options=['甲', '乙'], correct_answer='A')
        task = create_task(self.project, {'stage_id': 'start', 'title': '解释缓存', 'instructions': '先独立作答。',
                                         'question_ids': [question.pk]})
        uses = []

        def provider(messages, **kwargs):
            trigger = self.trigger()
            self.assertEqual(trigger.metadata['rsi_sidecar']['project_id'], self.project.pk)
            for method in ('先比较速度', '先比较容量'):
                event = ProjectLearningEvent.objects.create(project=self.project, message=trigger,
                    kind='progress', content={'strategy': method})
                strategy = LearningStrategy.objects.create(user=self.user, source_event=event)
                use = LearningStrategyUse.objects.create(strategy=strategy, project=self.project, message=trigger)
                teaching_sidecar.record_strategy_use(use, created=True)
                uses.append(use)
            return self.answer()

        with patch.object(AIEngine, 'call_provider', side_effect=provider):
            result = self.ask('请给我一个提示。', learning_activity={'task_id': str(task.pk)})
        self.assertEqual(result['metadata']['ulr_teaching']['action'], 'respond_to_hint_request')
        reply = AIChatMessage.objects.get(pk=result['message_id'])
        confirmed, unconfirmed = uses
        receipt = AIUsageReservation.objects.get(user=self.user, request_id=self.request_id)
        receipt.response['metadata']['ulr_strategy_use_ids'] = [confirmed.pk]
        receipt.save(update_fields=['response'])
        record_completed_reply(reply)
        confirmed.refresh_from_db()
        unconfirmed.refresh_from_db()
        self.assertEqual(confirmed.exposure['reply_id'], reply.pk)
        self.assertEqual(confirmed.exposure['status'], 'reply_completed')
        self.assertEqual(confirmed.exposure['adherence'], 'unverified')
        self.assertEqual(confirmed.exposure['engine'], 'ulr')
        self.assertEqual(confirmed.exposure['ulr_teaching_action'], 'respond_to_hint_request')
        self.assertEqual(unconfirmed.exposure['status'], 'assigned')

    def test_observation_failure_does_not_undo_the_completed_turn(self):
        def provider(messages, **kwargs):
            if messages[-1]['role'] == 'user':
                return self.tool_call('plan_learning_project', self.plan_arguments)
            return self.answer()

        def broken_observer(*args, **kwargs):
            ProjectLearningEvent.objects.create(project=self.project, kind='synthetic_observation')
            raise IntegrityError('Synthetic observation failure')

        with patch.object(AIEngine, 'call_provider', side_effect=provider), \
                patch.object(teaching_sidecar, 'record_tool_result', side_effect=broken_observer) as tool_observer, \
                patch.object(teaching_sidecar, 'record_turn_completion', side_effect=broken_observer) as turn_observer, \
                self.assertLogs(teaching_sidecar.logger, level='WARNING'):
            result = self.ask('请制定一份学习计划，等我确认。')
        tool_observer.assert_called_once()
        self.assertEqual(tool_observer.call_args.kwargs['channel'], 'ulr_project_commit')
        turn_observer.assert_called_once()
        reply = AIChatMessage.objects.get(pk=result['message_id'])
        self.assertTrue(reply.metadata['learning_turn']['completed'])
        self.assertEqual(AIUsageReservation.objects.get(user=self.user, request_id=self.request_id).status, 'succeeded')
        self.state.refresh_from_db()
        self.assertEqual(self.state.pending_plan['plan'], self.plan_arguments['plan'])
        self.assertFalse(ProjectLearningEvent.objects.filter(kind='synthetic_observation').exists())

    def test_completed_historical_turn_is_never_backfilled(self):
        question = AIChatMessage.objects.create(user=self.user, bot=self.bot, conversation_id=self.room.conversation_id,
            role='user', content='历史提问。')
        AIChatMessage.objects.create(user=self.user, bot=self.bot, conversation_id=self.room.conversation_id,
            role='assistant', content='历史答复。', metadata={'learning_turn': completed_learning_turn(question.pk)})
        with patch.object(teaching_sidecar, 'current_bundle') as bundle:
            self.assertIsNone(teaching_sidecar.freeze_turn(self.project, question, {}))
        bundle.assert_not_called()
        question.refresh_from_db()
        self.assertNotIn('rsi_sidecar', question.metadata)
