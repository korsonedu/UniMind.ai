from unittest.mock import patch
from django.test import override_settings
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase
from users.models import User, Institution, CourseStudentStatus
from quizzes.models import Question, KnowledgePoint, QuizExam, UserQuestionStatus
from quizzes.ai_workflow import run_exam_grading
from ai_assistant.models import (ConversationProject, ProjectLearning, ProjectLearningTask,
    ProjectLearningEvent, LearningResourceVersion)
from ai_assistant.services.function_sample import sample_content, seed_content, setup_sample
from ai_assistant.services.learning_tasks import task_data


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
                   UNIMIND_CONTENT_INSTITUTION_ID='global', USE_MEM0=False)
class FunctionSampleSmoke(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='function_sample_synthetic')
        CourseStudentStatus.objects.create(user=self.user, is_course_student=True)
        self.project = ConversationProject.objects.create(user=self.user, name='函数基础')
        self.client.force_authenticate(self.user)

    def test_seed_is_partitioned_idempotent_and_does_not_replace_modified_questions(self):
        foreign = Institution.objects.create(name='其他内容分区', slug='function-other', contact_name='测试', contact_email='other@example.invalid')
        node = sample_content()['nodes'][0]
        foreign_point = KnowledgePoint.objects.create(code=node['code'], institution=foreign, name='其他分区原内容')
        untouched = Question.objects.create(knowledge_point=foreign_point, institution=foreign, text=node['questions'][0]['text'], correct_answer='D')
        self.assertEqual(seed_content()['created_questions'], 12)
        self.assertEqual(seed_content()['created_questions'], 0)
        self.assertEqual(KnowledgePoint.objects.filter(institution__isnull=True).count(), 4)
        self.assertEqual(Question.objects.filter(institution__isnull=True, q_type='objective').count(), 12)
        untouched.refresh_from_db();self.assertEqual(untouched.correct_answer, 'D')
        row = Question.objects.filter(institution__isnull=True).first()
        row.correct_answer = 'D';row.save(update_fields=['correct_answer'])
        with self.assertRaises(ValidationError): seed_content()
        row.refresh_from_db();self.assertEqual(row.correct_answer, 'D')

    def test_setup_requires_seed_and_fresh_project_and_keeps_original_snapshots(self):
        with self.assertRaises(ValidationError): setup_sample(self.project)
        self.assertFalse(Question.objects.exists())
        seed_content()
        result = setup_sample(self.project)
        self.assertEqual(len(result['tasks']), 12)
        self.assertEqual(len(result['project']['plan']['stages']), 4)
        self.assertEqual(result['project']['status'], 'active')
        self.assertEqual(len({item['payload']['questions'][0]['id'] for item in result['tasks']}), 12)
        self.assertTrue(all(len(item['payload']['questions']) == 1 and item['mode'] == 'apply' for item in result['tasks']))
        self.assertTrue(all('correct_answer' not in item['payload']['questions'][0] for item in result['tasks']))
        self.assertIn('先阅读讲解和示例', result['tasks'][1]['instructions'])
        source = result['project']['resources'][0]
        self.assertEqual(source['source_kind'], 'unimind_original')
        self.assertTrue(source['not_web_read'])
        snapshot = LearningResourceVersion.objects.get(resource__user=self.user).snapshot
        self.assertEqual(len(snapshot['references']), 2)
        self.assertEqual(snapshot['source_kind'], 'unimind_original')
        for node in result['project']['knowledge']['nodes']:
            self.assertIn(node['citation']['quote'], source['excerpt'])
            self.assertEqual(node['citation']['source_kind'], 'unimind_original')
        with self.assertRaises(ValidationError): setup_sample(self.project)
        self.assertEqual(ProjectLearningTask.objects.filter(project=self.project).count(), 12)
        occupied = ConversationProject.objects.create(user=self.user, name='已有安排')
        ProjectLearning.objects.create(project=occupied, status='active', plan={'goal':'已有目标'})
        with self.assertRaises(ValidationError): setup_sample(occupied)
        self.assertEqual(ProjectLearning.objects.get(project=occupied).plan, {'goal':'已有目标'})
        named_goal = ConversationProject.objects.create(user=self.user, name='CPA', instructions='通过CPA考试')
        with self.assertRaises(ValidationError): setup_sample(named_goal)
        self.assertFalse(ProjectLearningTask.objects.filter(project=named_goal).exists())

    def test_sample_submission_runs_real_objective_key_grading_and_review(self):
        seed_content()
        result = setup_sample(self.project)
        payload = result['tasks'][0]
        task = ProjectLearningTask.objects.get(pk=payload['id'])
        question = Question.objects.get(pk=task.question_ids[0])
        response = self.client.post('/api/quizzes/submit-exam/', {'learning_task_id': str(task.pk), 'submission_id':str(task.pk),
            'assistance':'independent','answers':[{'question_id':question.pk,'answer':question.correct_answer}]}, format='json')
        self.assertEqual(response.status_code, 202, response.data)
        with patch('quizzes.ai_workflow.AIService.grade_question', side_effect=AssertionError('linked objective sample must not call a model')):
            run_exam_grading(self.user.pk, response.data['exam_id'])
        exam = QuizExam.objects.get(pk=response.data['exam_id'])
        self.assertEqual(exam.status, 'completed')
        answer = exam.results.get()
        self.assertEqual(answer.score, answer.max_score)
        self.assertEqual(answer.analysis, question.ai_answer)
        task.refresh_from_db();view = task_data(task)
        self.assertEqual(view['status'], 'completed')
        self.assertTrue(UserQuestionStatus.objects.filter(user=self.user, question=question, reps__gt=0).exists())
        evidence = ProjectLearningEvent.objects.get(project=self.project, kind='assessment')
        self.assertEqual(evidence.content['label_source'], 'objective_answer_key')
        self.assertEqual(evidence.content['outcome'], 'success')
