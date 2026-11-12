from unittest.mock import patch

from django.test import override_settings
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APITestCase

from ai_assistant.models import (ConversationProject, LearningKnowledgeMap, LearningKnowledgeVersion,
    ProjectLearning, ProjectLearningEvent, ProjectLearningTask)
from ai_assistant.services.learning_tasks import create_task, task_data
from quizzes.ai_workflow import run_exam_grading
from quizzes.models import Question, QuizExam, UserQuestionStatus
from users.models import User


@override_settings(UNIMIND_CONTENT_INSTITUTION_ID='global', USE_MEM0=False,
                   CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class LearningTasksSmoke(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='task_smoke')
        self.project = ConversationProject.objects.create(user=self.user, name='函数')
        mapping = LearningKnowledgeMap.objects.create(user=self.user, title='函数')
        self.version = LearningKnowledgeVersion.objects.create(knowledge_map=mapping, revision=1,
                                                               snapshot={'nodes': [{'id': 'domain'}]})
        self.state = ProjectLearning.objects.create(project=self.project, status='active', plan={
            'knowledge_path': {'version_id': self.version.pk},
            'stages': [{'id': 'start', 'knowledge_nodes': ['domain']}]})
        self.question = Question.objects.create(text='函数输入是什么？', options=['自变量', '装饰'],
                                                correct_answer='A', q_type='objective')
        self.arguments = {'version_id': self.version.pk, 'node_id': 'domain', 'stage_id': 'start',
            'title': '认识输入', 'instructions': '选择输入对应的名称。', 'question_ids': [self.question.pk], 'mode': 'apply'}
        self.client.force_authenticate(self.user)
        for target in ('users.feature_access.has_learning_feature', 'quizzes.ai_workflow.has_learning_feature',
                       'ai_assistant.services.learning_tasks.has_learning_feature'):
            allowed = patch(target, return_value=True)
            allowed.start()
            self.addCleanup(allowed.stop)
        self.task = create_task(self.project, self.arguments)

    def submit(self, **changes):
        body = {'submission_id': str(self.task.pk), 'learning_task_id': str(self.task.pk),
                'assistance': 'independent', 'answers': [{'question_id': self.question.pk, 'answer': 'A'}]}
        body.update(changes)
        with patch('quizzes.views_exam.dispatch_exam_grading'), self.captureOnCommitCallbacks(execute=True):
            return self.client.post('/api/quizzes/submit-exam/', body, format='json')

    def test_submit_grade_recovery_once_and_no_answer_leak(self):
        response = self.submit()
        self.assertEqual(response.status_code, 202, response.data)
        self.assertEqual(self.submit().data['exam_id'], response.data['exam_id'])
        self.assertEqual(self.submit(assistance='hint').status_code, 400)
        self.assertEqual(QuizExam.objects.count(), 1)
        ready = task_data(self.task)
        self.assertNotIn('correct_answer', str(ready))
        with patch('quizzes.ai_workflow.AIService.grade_question', side_effect=AssertionError('任务客观题不应调用模型')) as model, \
                patch('quizzes.ai_workflow._queue_experience_verification'), self.captureOnCommitCallbacks(execute=True):
            run_exam_grading(self.user.pk, response.data['exam_id'])
            run_exam_grading(self.user.pk, response.data['exam_id'])
            model.assert_not_called()
        self.task.refresh_from_db()
        data = task_data(self.task)
        task_data(self.task)
        self.assertEqual(data['status'], 'completed')
        self.assertIsNotNone(data['review_due_at'])
        self.assertNotIn('results', data['summary'])
        self.assertNotIn('correct_answer', str(data))
        event = ProjectLearningEvent.objects.get(kind='assessment')
        self.assertEqual(event.content['label_source'], 'objective_answer_key')
        self.assertEqual(event.content['outcome'], 'success')
        self.assertEqual(UserQuestionStatus.objects.get(user=self.user, question=self.question).reps, 1)
        self.assertEqual(self.submit(learning_task_id=None).status_code, 400)

    def test_snapshot_scope_ownership_and_active_plan(self):
        with patch('ai_assistant.services.learning_tasks.has_learning_feature', return_value=False):
            self.assertEqual(task_data(self.task)['status'], 'unavailable')
            self.assertEqual(task_data(self.task)['payload']['questions'], [])
            with self.assertRaises(PermissionDenied):
                create_task(self.project, self.arguments)
        self.question.correct_answer = 'B'
        self.question.save(update_fields=['correct_answer'])
        self.assertEqual(self.submit().status_code, 400)
        self.assertFalse(QuizExam.objects.exists())
        self.state.status = 'paused'
        self.state.save(update_fields=['status'])
        with self.assertRaises(ValidationError):
            create_task(self.project, self.arguments)
        other = User.objects.create_user(username='task_other')
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get(f'/api/ai/projects/{self.project.pk}/learning/tasks/{self.task.pk}/').status_code, 404)
        with override_settings(UNIMIND_CONTENT_INSTITUTION_ID=123):
            unavailable = task_data(self.task)
            self.assertEqual(unavailable['status'], 'unavailable')
            self.assertEqual(unavailable['payload']['questions'], [])
        self.client.force_authenticate(self.user)
        self.user.delete()
        self.assertFalse(ProjectLearningTask.objects.exists())

    def test_partial_grading_retry_keeps_completed_results_once(self):
        from quizzes.ai_workflow import _grade_answer
        another = Question.objects.create(text='函数的输出是什么？', options=['输入', '函数值'], correct_answer='B')
        self.task = create_task(self.project, {**self.arguments, 'question_ids': [self.question.pk, another.pk]})
        response = self.submit(answers=[{'question_id': self.question.pk, 'answer': 'A'}, {'question_id': another.pk, 'answer': 'B'}])
        exam_id = response.data['exam_id']
        def fail_second(question, answer, **kwargs):
            if question.pk == another.pk:
                raise RuntimeError('synthetic transient failure')
            return _grade_answer(question, answer, **kwargs)
        with patch('quizzes.ai_workflow._grade_answer', side_effect=fail_second), patch('quizzes.ai_workflow._queue_experience_verification'), self.captureOnCommitCallbacks(execute=True):
            run_exam_grading(self.user.pk, exam_id)
        self.task.refresh_from_db()
        self.assertEqual(task_data(self.task)['status'], 'partial')
        self.assertEqual(ProjectLearningEvent.objects.filter(kind='assessment').count(), 1)
        with patch('quizzes.views_exam.dispatch_exam_grading'), self.captureOnCommitCallbacks(execute=True):
            retried = self.client.post(f'/api/quizzes/exams/{exam_id}/retry/', {}, format='json')
        self.assertEqual(retried.status_code, 202)
        with patch('quizzes.ai_workflow._queue_experience_verification'), self.captureOnCommitCallbacks(execute=True):
            run_exam_grading(self.user.pk, exam_id)
        self.task.refresh_from_db()
        self.assertEqual(task_data(self.task)['status'], 'completed')
        self.assertEqual(ProjectLearningEvent.objects.filter(kind='assessment').count(), 2)
        self.assertEqual(list(UserQuestionStatus.objects.filter(user=self.user).values_list('reps', flat=True)), [1, 1])
