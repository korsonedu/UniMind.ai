"""Focused version and evidence boundaries; synthetic learners and grades only."""
import uuid
from copy import deepcopy
from unittest.mock import patch
from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from ai_assistant.models import (AIChatMessage, Bot, Conversation, ConversationProject, LearningStrategy,
    LearningStrategyUse, LearningStrategyOutcome, ProjectLearning, ProjectLearningEvent, TeachingMechanismVersion)
from ai_assistant.services.learning_tasks import create_task, sync_task_result
from ai_assistant.services.project_learning import completed_learning_turn
from ai_assistant.services.teaching_sidecar import (current_bundle, freeze_turn, observe,
    record_strategy_use, record_turn_completion, register_mechanism, validate_strategy_use)
from quizzes.models import QuizExam, ExamQuestionResult
from users.models import User, CourseStudentStatus


@override_settings(UNIMIND_CONTENT_INSTITUTION_ID='global', USE_MEM0=False)
class TeachingSidecarSmoke(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='rsi_core_synthetic')
        self.other = User.objects.create_user(username='rsi_core_other')
        CourseStudentStatus.objects.create(user=self.user, is_course_student=True)
        self.bot = Bot.objects.create(name='小宇', bot_type='planner')
        self.project = ConversationProject.objects.create(user=self.user, name='合成学习目标')
        self.conversation = Conversation.objects.create(user=self.user, bot=self.bot, project=self.project,
            conversation_id=uuid.uuid4())
        ProjectLearning.objects.create(project=self.project, status='active', current_stage='start',
            plan={'stages': [{'id': 'start', 'title': '开始'}]})
        self.source = AIChatMessage.objects.create(user=self.user, bot=self.bot, role='user',
            conversation_id=self.conversation.conversation_id, content='这是合成起点表现。')
        event = ProjectLearningEvent.objects.create(project=self.project, message=self.source,
            kind='progress', content={'strategy': '先比较两个情境，再独立解释差异。'})
        self.strategy = LearningStrategy.objects.create(user=self.user, source_event=event)
        self.message = AIChatMessage.objects.create(user=self.user, bot=self.bot, role='user',
            conversation_id=self.conversation.conversation_id, content='请继续。')
        freeze_turn(self.project, self.message, {'project_id': self.project.pk, 'context': '合成状态'})
        self.use = LearningStrategyUse.objects.create(strategy=self.strategy, project=self.project,
            message=self.message, reason='比较条件相近。')
        record_strategy_use(self.use, created=True)
        self.use.refresh_from_db()

    def result(self, assistance='independent', criteria=None):
        task = create_task(self.project, {'stage_id': 'start', 'title': '独立解释', 'instructions': '解释新情境。',
            'strategy_use_id': self.use.pk, 'purpose': 'recheck', 'definition': {
                'prompt': '解释这个合成案例中两个条件的差异。', 'response_type': 'explanation', 'criteria': criteria or ['指出条件差异']}})
        exam = QuizExam.objects.create(user=self.user, status='completed')
        task.exam, task.assistance = exam, assistance
        task.save(update_fields=['exam', 'assistance'])
        result = ExamQuestionResult.objects.create(exam=exam, position=1, user_answer='合成作答。', score=8,
            max_score=10, status='graded', graded_at=timezone.now(), question_snapshot=task.question_snapshot['0'])
        return task, result

    def reply(self):
        reply = AIChatMessage.objects.create(user=self.user, bot=self.bot, role='assistant',
            conversation_id=self.message.conversation_id, content='请解释一个新情境。',
            metadata={'learning_turn': completed_learning_turn(self.message.pk)})
        record_turn_completion(reply)
        self.use.refresh_from_db()

    def test_versions_freeze_and_private_candidates_never_become_active(self):
        frozen = deepcopy(self.message.metadata['rsi_sidecar'])
        bundle = current_bundle()
        candidate = register_mechanism('G', {'instruction': '只在影子研究使用'}, owner=self.user,
            parent=TeachingMechanismVersion.objects.get(pk=bundle['G']['id']))
        self.assertEqual(current_bundle(), bundle)
        with self.assertRaises(PermissionDenied):
            register_mechanism('G', candidate.content)
        with self.assertRaises(PermissionDenied):
            register_mechanism('G', candidate.content, owner=self.other, parent=candidate)
        with patch('ai_assistant.services.teaching_sidecar.current_bundle', side_effect=AssertionError('No refreeze')):
            self.assertEqual(freeze_turn(self.project, self.message, {'changed': True}), frozen)
        self.assertEqual(self.use.decision['selection_kind'], 'model_directed_nonrandom')
        self.assertIsNone(self.use.decision['propensity'])
        self.assertIsNone(self.use.method_version.generator_id)

    def test_later_independent_report_does_not_rewrite_grades_or_claim_method_effect(self):
        self.reply()
        task, result = self.result()
        sync_task_result(result)
        sync_task_result(result)
        outcome = LearningStrategyOutcome.objects.get(use=self.use)
        self.assertEqual(outcome.snapshot['status'], 'independent_reported_observation')
        self.assertFalse(outcome.snapshot['causal_claim'])
        self.assertFalse(outcome.snapshot['independent_label_verified'])
        self.assertEqual(outcome.snapshot['label_source'], 'model_rubric_grade')
        self.assertEqual(self.use.exposure['adherence'], 'unverified')
        self.assertFalse(self.use.reviews.exists())
        result.refresh_from_db()
        self.assertEqual(result.score, 8)
        self.assertEqual(outcome.task_id, task.pk)

    def test_early_submission_unknown_help_and_source_revocation(self):
        task, result = self.result('unknown')
        self.reply()
        sync_task_result(result)
        outcome = LearningStrategyOutcome.objects.get(use=self.use)
        self.assertEqual(outcome.snapshot['status'], 'uncertain')
        self.assertIn('no_completed_prior_teaching', outcome.snapshot['reasons'])
        self.assertIn('assistance_not_independent', outcome.snapshot['reasons'])
        self.source.delete()
        with self.assertRaises(ValidationError):
            validate_strategy_use(self.project, self.use.pk)
        self.project.delete()
        self.assertFalse(LearningStrategyOutcome.objects.exists())

    def test_observation_savepoint_and_no_retroactive_turn_instrumentation(self):
        def broken_observer():
            ProjectLearningEvent.objects.create(project=self.project, kind='observation')
            raise ValidationError('Synthetic failure')
        with transaction.atomic(), self.assertLogs('ai_assistant.services.teaching_sidecar', level='WARNING'):
            ProjectLearningEvent.objects.create(project=self.project, kind='committed_work')
            self.assertIsNone(observe(broken_observer))
            self.assertTrue(ProjectLearningEvent.objects.filter(kind='committed_work').exists())
        self.assertFalse(ProjectLearningEvent.objects.filter(kind='observation').exists())
        AIChatMessage.objects.create(user=self.user, bot=self.bot, role='assistant',
            conversation_id=self.source.conversation_id, content='旧轮次。',
            metadata={'learning_turn': completed_learning_turn(self.source.pk)})
        self.assertIsNone(freeze_turn(self.project, self.source, {}))
        self.source.refresh_from_db()
        self.assertNotIn('rsi_sidecar', self.source.metadata)

    def test_repeated_prompt_and_intervening_method_are_not_independent(self):
        self.reply()
        _, first = self.result()
        sync_task_result(first)
        later = AIChatMessage.objects.create(user=self.user, bot=self.bot, role='user',
            conversation_id=self.message.conversation_id, content='后来又尝试了另一种讲解。')
        LearningStrategyUse.objects.create(strategy=self.strategy, project=self.project,
            message=later, reason='交叠的后续方法。')
        _, result = self.result(criteria=['换了标准仍是同一题干'])
        sync_task_result(result)
        outcome = LearningStrategyOutcome.objects.get(result=result)
        self.assertEqual(outcome.snapshot['status'], 'uncertain')
        self.assertIn('repeated_question', outcome.snapshot['reasons'])
        self.assertIn('overlapping_methods', outcome.snapshot['reasons'])

    def test_changed_method_source_cannot_add_a_verified_observation(self):
        self.reply()
        _, result = self.result()
        self.source.content = '原始依据已被修改。'
        self.source.save(update_fields=['content'])
        with self.assertLogs('ai_assistant.services.teaching_sidecar', level='WARNING'):
            sync_task_result(result)
        self.assertFalse(LearningStrategyOutcome.objects.exists())
        self.assertEqual(ProjectLearningEvent.objects.filter(kind='assessment').count(), 1)
