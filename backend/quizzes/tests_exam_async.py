from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APITestCase

from notifications.models import Notification
from quizzes.ai_workflow import run_exam_grading
from quizzes.models import ExamQuestionResult, KnowledgePoint, Question, QuizExam
from users.models import CourseStudentStatus, Institution, User


def grade_ok(question, answer):
    max_score = question.get_max_score()
    return {
        'score': max_score,
        'max_score': max_score,
        'feedback': '要点完整。',
        'analysis': '标准解析。',
        'error_analysis': {},
        'memorix_rating': 4,
        'normalized_score': 1.0,
        'is_correct': True,
    }


class ExamAsyncTests(APITestCase):
    def setUp(self):
        self.content_inst = Institution.objects.create(
            name='科晟内容', slug='exam-content', contact_name='C', contact_email='c@example.com',
        )
        self.other_inst = Institution.objects.create(
            name='其他机构', slug='exam-other', contact_name='O', contact_email='o@example.com',
        )
        self.settings_override = override_settings(
            UNIMIND_CONTENT_INSTITUTION_ID=str(self.content_inst.pk),
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        self.user = User.objects.create_user(
            username='exam-student', email='exam@example.com', password='Pass12345!',
        )
        CourseStudentStatus.objects.create(user=self.user, is_course_student=True)
        self.client.force_authenticate(user=self.user)

        self.kp = KnowledgePoint.objects.create(
            code='MB-EXAM-01', name='利率基础', level='kp', institution=self.content_inst,
        )
        self.objective = Question.objects.create(
            text='利率上升时，债券价格如何变化？',
            q_type='objective',
            options={'A': '上升', 'B': '下降', 'C': '不变', 'D': '无法判断'},
            correct_answer='B',
            knowledge_point=self.kp,
            institution=self.content_inst,
        )
        self.subjective = Question.objects.create(
            text='简述利率期限结构。',
            q_type='subjective',
            subjective_type='short',
            correct_answer='预期理论、流动性溢价理论与市场分割理论。',
            grading_points='三种理论各 3 分，结论 1 分。',
            knowledge_point=self.kp,
            institution=self.content_inst,
        )

    def submit(self):
        payload = {
            'answers': [
                {'question_id': self.objective.pk, 'answer': 'B'},
                {'question_id': self.subjective.pk, 'answer': '利率期限结构有三种理论。'},
            ],
        }
        with patch('quizzes.views_exam.dispatch_exam_grading') as dispatch, \
                self.captureOnCommitCallbacks(execute=True):
            response = self.client.post('/api/quizzes/submit-exam/', payload, format='json')
        return response, dispatch

    def test_submit_creates_pending_items_and_snapshots(self):
        response, dispatch = self.submit()
        self.assertEqual(response.status_code, 202, response.data)
        dispatch.assert_called_once()
        exam = QuizExam.objects.get(pk=response.data['exam_id'])
        self.assertEqual(exam.status, 'pending')
        self.assertEqual(exam.total_questions, 2)
        self.assertEqual(exam.results.count(), 2)
        self.assertEqual(set(exam.results.values_list('status', flat=True)), {'pending'})
        result = exam.results.get(question=self.subjective)
        self.assertEqual(result.user_answer, '利率期限结构有三种理论。')
        self.assertEqual(result.question_snapshot['correct_answer'], self.subjective.correct_answer)

        status_response = self.client.get(f'/api/quizzes/exams/{exam.pk}/status/')
        self.assertEqual(status_response.status_code, 200, status_response.data)
        self.assertEqual(status_response.data['status'], 'pending')
        self.assertEqual(status_response.data['graded_count'], 0)
        self.assertEqual(status_response.data['total_questions'], 2)

    def test_grading_completes_and_detail_survives_question_deletion(self):
        response, _ = self.submit()
        exam = QuizExam.objects.get(pk=response.data['exam_id'])

        with patch('quizzes.ai_workflow._grade_answer', side_effect=grade_ok), \
                patch('quizzes.ai_workflow._apply_memorix_status'), \
                patch('quizzes.ai_workflow._queue_experience_verification'), \
                patch('notifications.tasks_reminder.send_notification_email.delay') as email_delay, \
                self.captureOnCommitCallbacks(execute=True):
            run_exam_grading(self.user.pk, exam.pk)

        exam.refresh_from_db()
        self.assertEqual(exam.status, 'completed')
        self.assertEqual(exam.graded_count, 2)
        self.assertEqual(exam.failed_count, 0)
        self.assertEqual(exam.total_score, 20.0)
        self.assertIsNotNone(exam.notified_at)
        email_delay.assert_not_called()

        notification = Notification.objects.get(
            recipient=self.user, ntype='practice_result', link=f'/tests/results/{exam.pk}',
        )
        self.assertIn('练习批改完成', notification.title)

        self.subjective.delete()
        detail = self.client.get(f'/api/quizzes/exams/{exam.pk}/')
        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertEqual(detail.data['status'], 'completed')
        subjective_item = next(item for item in detail.data['results'] if item['position'] == 2)
        self.assertEqual(subjective_item['question_text'], '简述利率期限结构。')
        self.assertEqual(subjective_item['correct_answer'], self.subjective.correct_answer)
        self.assertEqual(subjective_item['user_answer'], '利率期限结构有三种理论。')

        history = self.client.get('/api/quizzes/exams/?limit=5')
        self.assertEqual(history.status_code, 200, history.data)
        self.assertEqual(history.data['items'][0]['id'], exam.pk)

    def test_partial_failure_skips_elo_and_retry_completes(self):
        response, _ = self.submit()
        exam = QuizExam.objects.get(pk=response.data['exam_id'])
        original_elo = self.user.elo_score

        def fail_second(question, answer):
            if question.pk == self.subjective.pk:
                raise RuntimeError('模型暂不可用')
            return grade_ok(question, answer)

        with patch('quizzes.ai_workflow._grade_answer', side_effect=fail_second), \
                patch('quizzes.ai_workflow._apply_memorix_status'), \
                patch('quizzes.ai_workflow._queue_experience_verification'), \
                self.captureOnCommitCallbacks(execute=True):
            run_exam_grading(self.user.pk, exam.pk)

        exam.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(exam.status, 'partial')
        self.assertEqual(exam.graded_count, 1)
        self.assertEqual(exam.failed_count, 1)
        self.assertEqual(self.user.elo_score, original_elo)
        failed = exam.results.get(status='failed')
        self.assertEqual(failed.question_id, self.subjective.pk)

        with patch('quizzes.views_exam.dispatch_exam_grading') as dispatch, \
                self.captureOnCommitCallbacks(execute=True):
            retry = self.client.post(f'/api/quizzes/exams/{exam.pk}/retry/', {}, format='json')
        self.assertEqual(retry.status_code, 202, retry.data)
        dispatch.assert_called_once()
        exam.refresh_from_db()
        self.assertEqual(exam.status, 'grading')
        self.assertEqual(exam.results.filter(status='pending').count(), 1)

        with patch('quizzes.ai_workflow._grade_answer', side_effect=grade_ok), \
                patch('quizzes.ai_workflow._apply_memorix_status'), \
                patch('quizzes.ai_workflow._queue_experience_verification'), \
                self.captureOnCommitCallbacks(execute=True):
            run_exam_grading(self.user.pk, exam.pk)

        exam.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(exam.status, 'completed')
        self.assertEqual(exam.results.count(), 2)
        self.assertEqual(exam.results.filter(status='graded').count(), 2)
        self.assertNotEqual(self.user.elo_score, original_elo)

    def test_content_scope_change_marks_items_failed(self):
        response, _ = self.submit()
        exam = QuizExam.objects.get(pk=response.data['exam_id'])

        with override_settings(UNIMIND_CONTENT_INSTITUTION_ID=str(self.other_inst.pk)), \
                patch('quizzes.ai_workflow._apply_memorix_status'), \
                patch('quizzes.ai_workflow._queue_experience_verification'), \
                self.captureOnCommitCallbacks(execute=True):
            run_exam_grading(self.user.pk, exam.pk)

        exam.refresh_from_db()
        self.assertEqual(exam.status, 'failed')
        self.assertEqual(exam.graded_count, 0)
        self.assertEqual(exam.failed_count, 2)
        self.assertTrue(all(
            '内容范围' in (item.error_metadata or {}).get('error', '')
            or '题目不存在' in (item.error_metadata or {}).get('error', '')
            for item in exam.results.all()
        ))

    def test_other_user_cannot_read_exam(self):
        response, _ = self.submit()
        exam = QuizExam.objects.get(pk=response.data['exam_id'])
        other = User.objects.create_user(
            username='other-student', email='other@example.com', password='Pass12345!',
        )
        CourseStudentStatus.objects.create(user=other, is_course_student=True)
        self.client.force_authenticate(user=other)
        self.assertEqual(self.client.get(f'/api/quizzes/exams/{exam.pk}/').status_code, 404)
        self.assertEqual(self.client.get(f'/api/quizzes/exams/{exam.pk}/status/').status_code, 404)

    def test_recent_practice_tool_returns_result_card(self):
        from ai_assistant.services.tool_executor import PlannerToolExecutor
        from ai_engine.tool_permissions import filter_tools

        response, _ = self.submit()
        exam = QuizExam.objects.get(pk=response.data['exam_id'])
        with patch('quizzes.ai_workflow._grade_answer', side_effect=grade_ok), \
                patch('quizzes.ai_workflow._apply_memorix_status'), \
                patch('quizzes.ai_workflow._queue_experience_verification'), \
                self.captureOnCommitCallbacks(execute=True):
            run_exam_grading(self.user.pk, exam.pk)

        executor = PlannerToolExecutor(self.user)
        result = executor._handle_get_recent_practice_result({})
        self.assertTrue(result['has_result'])
        self.assertEqual(result['exam_id'], exam.pk)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['href'], f'/tests/results/{exam.pk}')
        self.assertEqual(result['visual']['type'], 'practice_result')
        self.assertEqual(result['visual']['payload']['exam_id'], exam.pk)

        tools = [{'function': {'name': 'get_recent_practice_result'}}]
        self.assertEqual(len(filter_tools('planner', self.content_inst, tools, user=self.user)), 1)

    def test_recent_practice_tool_pending_does_not_fabricate_score(self):
        from ai_assistant.services.tool_executor import PlannerToolExecutor

        response, _ = self.submit()
        exam = QuizExam.objects.get(pk=response.data['exam_id'])
        executor = PlannerToolExecutor(self.user)
        result = executor._handle_get_recent_practice_result({})
        self.assertTrue(result['has_result'])
        self.assertEqual(result['status'], 'pending')
        self.assertEqual(result['graded_count'], 0)
        self.assertEqual(result['total_score'], 0)
        self.assertEqual(result['total_questions'], 2)
