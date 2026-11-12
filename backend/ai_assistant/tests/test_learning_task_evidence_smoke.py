"""Focused integration checks for formal result provenance, repetitions and label sources."""
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4
from django.test import TestCase, override_settings
from django.utils import timezone
from types import SimpleNamespace
from ai_assistant.models import AIChatMessage, Bot, Conversation, ConversationProject, LearningKnowledgeMap, LearningKnowledgeVersion, ProjectLearning
from ai_assistant.services.learning_tasks import create_task, sync_task_result
from ai_assistant.services.learning_task_evidence import formal_observations
from ai_assistant.services.bayesian_evaluation import evaluate_records
from quizzes.models import Question, QuizExam, ExamQuestionResult
from quizzes.services.practice_results import question_snapshot
from users.models import User


@override_settings(UNIMIND_CONTENT_INSTITUTION_ID='global')
class FormalEvidenceSmoke(TestCase):
    def test_verified_scores_repetitions_help_and_separate_holdout_labels(self):
        with patch('users.feature_access.has_learning_feature', return_value=True), patch('ai_assistant.services.learning_tasks.has_learning_feature', return_value=True), patch('ai_assistant.services.learning_task_evidence.has_learning_feature', return_value=True):
            user = User.objects.create_user(username='formal_evidence_synthetic')
            project = ConversationProject.objects.create(user=user, name='函数')
            mapping = LearningKnowledgeMap.objects.create(user=user, title='函数')
            version = LearningKnowledgeVersion.objects.create(knowledge_map=mapping, revision=1, snapshot={'nodes': [{'id': 'n'}]})
            ProjectLearning.objects.create(project=project, planning_enabled=True, status='active', plan={'knowledge_path': {'version_id': version.pk}, 'stages': [{'id': 's', 'knowledge_nodes': ['n']}]})
            questions = [Question.objects.create(text=f'第{i}个函数的值是多少？', options=['1', '2'], correct_answer='A') for i in range(2)]
            def record(question, assistance):
                task = create_task(project, {'version_id': version.pk, 'node_id': 'n', 'stage_id': 's', 'title': '求值', 'instructions': '求函数值', 'question_ids': [question.pk], 'mode': 'apply'})
                exam = QuizExam.objects.create(user=user, status='completed', total_questions=1)
                task.exam, task.assistance = exam, assistance
                task.save()
                result = ExamQuestionResult.objects.create(exam=exam, question=question, position=1, user_answer='A', score=10, max_score=10, status='graded', is_correct=True, question_snapshot=question_snapshot(question), graded_at=timezone.now())
                sync_task_result(result)
                return task, result
            task, result = record(questions[0], 'independent')
            from ai_assistant.services.project_learning import tool_operation
            bot = Bot.objects.create(name='小宇', bot_type='planner')
            conversation = Conversation.objects.create(user=user, project=project, bot=bot, conversation_id=uuid4())
            message = AIChatMessage.objects.create(user=user, role='user', bot=bot, conversation_id=conversation.conversation_id, content='复盘这道题')
            executor = SimpleNamespace(user=user, learning_context={'message_id': message.pk, 'conversation_id': str(conversation.conversation_id), 'bot_id': bot.pk})
            review = tool_operation(executor, 'manage_learning_tasks', {'action': 'read', 'task_id': str(task.pk)})
            self.assertEqual(review['results'][0]['user_answer'], 'A')
            result.status = 'pending'; result.save(update_fields=['status'])
            pending = tool_operation(executor, 'manage_learning_tasks', {'action': 'read', 'task_id': str(task.pk)})
            self.assertEqual(pending['results'], [])
            result.status = 'graded'; result.save(update_fields=['status'])
            record(questions[0], 'independent')
            record(questions[1], 'guided')
            rows, provenance = formal_observations(project, version.pk)
            self.assertEqual(len(rows), 2)
            self.assertEqual(provenance['repeated_questions'], 1)
            cutoff = task.created_at - timedelta(seconds=1)
            report = evaluate_records(rows, cutoff, 'synthetic')
            self.assertEqual(report['counts']['holdout'], 1)
            self.assertEqual(report['counts']['unscored_holdout'], 1)
            self.assertEqual(report['label_source'], 'objective_answer_key')
            self.assertEqual(report['metrics_by_label_source']['objective_answer_key']['bep']['n'], 1)
            self.assertNotIn('user_answer', str(report))
            # Multiple question results in one task remain separate observations.
            another = {**rows[0], 'event_id': rows[0]['event_id'] + 100, 'result_id': rows[0]['result_id'] + 100, 'question_hash': 'another-question'}
            multi = evaluate_records([rows[0], another], cutoff, 'synthetic')
            self.assertEqual(multi['counts']['holdout'], 2)
            result.user_answer = 'B'
            result.save(update_fields=['user_answer'])
            rows, provenance = formal_observations(project, version.pk)
            self.assertEqual(provenance['excluded_provenance'], 1)
            self.assertNotIn(result.pk, [row['result_id'] for row in rows])
