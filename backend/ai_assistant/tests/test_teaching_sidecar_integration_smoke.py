"""Focused DSH-to-task sidecar checks; all learners and grades are synthetic."""
import uuid
from copy import deepcopy
from unittest.mock import patch

from django.test import override_settings
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.test import APITestCase

from ai_assistant.models import (AIChatMessage, Bot, Conversation, ConversationProject, LearningStrategyUse,
    LearningStrategyOutcome, ProjectLearning, ProjectLearningEvent)
from ai_assistant.services.dsh_service import build_context, execute_tool, memory_snapshot
from ai_assistant.services.learning_library import strategy_operation
from ai_assistant.services.learning_tasks import create_task, sync_task_result
from ai_assistant.services.project_learning import completed_learning_turn
from ai_assistant.services.teaching_sidecar import record_turn_completion
from quizzes.ai_workflow import run_exam_grading
from users.models import CourseStudentStatus, User


@override_settings(UNIMIND_CONTENT_INSTITUTION_ID='global', USE_MEM0=False,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class TeachingSidecarIntegrationSmoke(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='sidecar_integration_synthetic')
        CourseStudentStatus.objects.create(user=self.user, is_course_student=True)
        self.bot = Bot.objects.create(name='小宇', bot_type='planner')
        self.project = ConversationProject.objects.create(user=self.user, name='计算机原理')
        self.conversation = Conversation.objects.create(user=self.user, bot=self.bot, project=self.project,
            conversation_id=uuid.uuid4())
        ProjectLearning.objects.create(project=self.project, status='active', current_stage='start',
            plan={'goal': '解释缓存', 'stages': [{'id': 'start', 'title': '起点', 'knowledge_nodes': []}]})
        self.source = AIChatMessage.objects.create(user=self.user, bot=self.bot, role='user',
            conversation_id=self.conversation.conversation_id, content='我用日常例子解释缓存。')
        event = ProjectLearningEvent.objects.create(project=self.project, message=self.source, kind='progress',
            content={'strategy': '先比较运行过程，再检查类比失效的条件。', 'assistance': 'unknown'})
        self.strategy_id = strategy_operation(self.project, {'action': 'save', 'event_id': event.pk})['strategy_id']
        self.message = AIChatMessage.objects.create(user=self.user, bot=self.bot, role='user',
            conversation_id=self.conversation.conversation_id, content='请用这个方法继续。')
        self.context = {'message_id': self.message.pk, 'bot_id': self.bot.pk,
            'conversation_id': str(self.conversation.conversation_id)}
        self.arguments = {'stage_id': 'start', 'title': '缓存边界', 'instructions': '自己解释新场景。',
            'purpose': 'recheck', 'definition': {'prompt': '请解释缓存未命中时会发生什么。',
                'response_type': 'explanation', 'criteria': ['说明需要访问较慢存储', '说明缓存并非每次都更快']}}
        self.client.force_authenticate(self.user)

    def apply(self):
        build_context(self.user, self.message.content, chat_context=self.context)
        result = execute_tool(self.user, 'manage_learning_strategies', {'action': 'apply',
            'strategy_id': self.strategy_id, 'reason': '检查类比是否能迁移到运行过程。'},
            memory_snapshot(self.user)['version'], chat_context=self.context)
        self.assertNotIn('error', result, result)
        return LearningStrategyUse.objects.get(pk=result['use_id'])

    def test_trusted_dsh_freezes_versions_and_replays_the_same_method_decision(self):
        first = build_context(self.user, self.message.content, chat_context=self.context)
        self.message.refresh_from_db()
        frozen = deepcopy(self.message.metadata['rsi_sidecar'])
        use = self.apply()
        self.assertIsNotNone(use.method_version_id)
        self.assertTrue(use.decision)
        decision = deepcopy(use.decision)
        again = self.apply()
        self.assertEqual(again.pk, use.pk)
        self.assertEqual(again.decision, decision)
        self.project.instructions = '后续轮次再采用新的安排。'
        self.project.save(update_fields=['instructions'])
        second = build_context(self.user, self.message.content, chat_context=self.context)
        self.message.refresh_from_db()
        self.assertEqual(self.message.metadata['rsi_sidecar'], frozen)
        self.assertTrue(self.message.metadata['rsi_observations'])
        self.assertEqual(first['system_prompt'], second['system_prompt'])
        moved = ConversationProject.objects.create(user=self.user, name='另一个目标')
        self.conversation.project = moved
        self.conversation.save(update_fields=['project'])
        with self.assertRaises(PermissionDenied):
            build_context(self.user, self.message.content, chat_context=self.context)

    def test_explicit_use_follows_the_actual_submission_and_idempotent_assessment(self):
        use = self.apply()
        task = create_task(self.project, {**self.arguments, 'strategy_use_id': use.pk})
        self.assertEqual(task.strategy_use_id, use.pk)
        reply = AIChatMessage.objects.create(user=self.user, bot=self.bot, role='assistant',
            conversation_id=self.conversation.conversation_id, content='对比命中与未命中，再说明原因。',
            metadata={'learning_turn': completed_learning_turn(self.message.pk)})
        record_turn_completion(reply)
        use.refresh_from_db()
        self.assertTrue(use.exposure)
        with patch('quizzes.views_exam.dispatch_exam_grading'), self.captureOnCommitCallbacks(execute=True):
            submitted = self.client.post('/api/quizzes/submit-exam/', {'learning_task_id': str(task.pk),
                'submission_id': str(task.pk), 'assistance': 'unknown',
                'answers': [{'question_id': 0, 'answer': '未命中需要继续访问主存，因此有额外开销。'}]}, format='json')
        self.assertEqual(submitted.status_code, 202, submitted.data)
        with patch('quizzes.ai_workflow.AIService.grade_question', return_value={
            'score': 8, 'feedback': '说明了未命中的代价。', 'analysis': '依据公开标准。', 'memorix_rating': 4}), \
                self.captureOnCommitCallbacks(execute=True):
            run_exam_grading(self.user.pk, submitted.data['exam_id'])
        task.refresh_from_db()
        result = task.exam.results.get()
        sync_task_result(result)
        sync_task_result(result)
        outcome = LearningStrategyOutcome.objects.get(use=use, task=task, result=result)
        self.assertEqual(outcome.event.kind, 'assessment')
        self.assertEqual(outcome.snapshot['assistance'], 'unknown')
        self.assertEqual(outcome.snapshot['label_source'], 'model_rubric_grade')
        self.assertEqual(LearningStrategyOutcome.objects.count(), 1)
        self.assertFalse(use.reviews.exists())
        self.assertEqual(ProjectLearningEvent.objects.filter(kind='assessment').count(), 1)
        unlinked = create_task(self.project, self.arguments)
        self.assertIsNone(unlinked.strategy_use_id)

    def test_method_binding_rechecks_project_and_source_without_guessing(self):
        use = self.apply()
        other_project = ConversationProject.objects.create(user=self.user, name='不同目标')
        ProjectLearning.objects.create(project=other_project, status='active',
            plan={'stages': [{'id': 'start', 'title': '开始'}]})
        with self.assertRaises((NotFound, PermissionDenied, ValidationError)):
            create_task(other_project, {**self.arguments, 'strategy_use_id': use.pk})
        self.source.delete()
        with self.assertRaises((NotFound, PermissionDenied, ValidationError)):
            create_task(self.project, {**self.arguments, 'strategy_use_id': use.pk})
        self.assertEqual(LearningStrategyOutcome.objects.count(), 0)
