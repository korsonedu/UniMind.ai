from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from time import monotonic, sleep
from unittest.mock import patch

import pytest
from django.db import connection, transaction
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from notifications.models import Notification
from quizzes.ai_workflow import run_exam_grading
from quizzes.models import ExamQuestionResult, KnowledgePoint, Question, QuizExam
from quizzes.services.exam_grading_state import GRADING_RECOVERY_DELAY
from users.models import CourseStudentStatus, Institution, User


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('submit_runtime', ['ulr', 'legacy'])
def test_ulr_exam_waits_for_the_question_edit_before_settlement(auth_client, user, settings, submit_runtime):
    if connection.vendor != 'postgresql':
        pytest.skip('Requires PostgreSQL row locks.')
    settings.UNIMIND_LEARNING_RUNTIME = submit_runtime
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    question = Question.objects.create(text='说明折现依据。', q_type='subjective', subjective_type='short',
                                       grading_points='按现金流风险说明。')
    with patch('quizzes.views_exam.dispatch_exam_grading'):
        submitted = auth_client.post('/api/quizzes/submit-exam/', {
            'answers': [{'question_id': question.pk, 'answer': '先判断现金流风险。'}],
        }, format='json')
    assert submitted.status_code == 202, submitted.data
    exam_id = submitted.data['exam_id']
    assert QuizExam.objects.get(pk=exam_id).requires_ulr == (submit_runtime == 'ulr')
    if submit_runtime == 'legacy':
        old_item = ExamQuestionResult.objects.get(exam_id=exam_id)
        old_item.question_snapshot.pop('rubric', None)
        old_item.save(update_fields=['question_snapshot'])
    settings.UNIMIND_LEARNING_RUNTIME = 'ulr'
    model_ready, finish_model = Event(), Event()
    grading_pid = None

    def model(row, answer, *, language):
        nonlocal grading_pid
        assert row.grading_points == question.grading_points
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_backend_pid()')
            grading_pid, = cursor.fetchone()
        model_ready.set()
        assert finish_model.wait(timeout=10)
        return grade_ok(row, answer, language=language)

    def grade():
        try:
            run_exam_grading(user.pk, exam_id)
        finally:
            connection.close()

    waited = False
    with patch('quizzes.ai_workflow._grade_answer', side_effect=model) as scorer, \
            patch('quizzes.ai_workflow._apply_memorix_status') as memorix, \
            patch('quizzes.ai_workflow._queue_experience_verification') as experience, \
            ThreadPoolExecutor(max_workers=1) as worker:
        future = worker.submit(grade)
        try:
            assert model_ready.wait(timeout=10)
            with transaction.atomic(), connection.cursor() as cursor:
                Question.objects.filter(pk=question.pk).update(grading_points='按投资期限说明。')
                finish_model.set()
                deadline = monotonic() + 5
                while not future.done() and monotonic() < deadline:
                    cursor.execute('SELECT pg_backend_pid() = ANY(pg_blocking_pids(%s))', [grading_pid])
                    waited, = cursor.fetchone()
                    if waited:
                        break
                    sleep(0.02)
        finally:
            finish_model.set()
        future.result(timeout=10)
        scorer.assert_called_once()

    exam = QuizExam.objects.get(pk=exam_id)
    item = exam.results.get()
    assert (exam.status, item.status, item.score) == ('failed', 'failed', 0)
    assert waited
    assert item.user_answer == '先判断现金流风险。'
    assert item.question_snapshot['grading_points'] == question.grading_points
    memorix.assert_not_called()
    experience.assert_not_called()


def grade_ok(question, answer, *, language='zh-CN'):
    assert language == 'zh-CN'
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

    def test_partial_failure_and_retry_complete_without_elo(self):
        response, _ = self.submit()
        exam = QuizExam.objects.get(pk=response.data['exam_id'])
        original_elo = self.user.elo_score

        def fail_second(question, answer, *, language='zh-CN'):
            if question.pk == self.subjective.pk:
                raise RuntimeError('模型暂不可用')
            return grade_ok(question, answer, language=language)

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
        self.assertEqual(self.user.elo_score, original_elo)

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

    def test_ulr_handoff_checks_the_legacy_submission_before_model_use(self):
        rubric = [{'point': '说明期限结构', 'score': 10}]
        Question.objects.filter(pk=self.subjective.pk).update(rubric=rubric)
        unverified = Question.objects.create(text='比较两种利率。', q_type='subjective', subjective_type='short',
            grading_points='说明两种利率的区别。', rubric=rubric, institution=self.content_inst)
        with override_settings(DEBUG=False, UNIMIND_LEARNING_RUNTIME='legacy'), \
                patch('quizzes.views_exam.dispatch_exam_grading'), self.captureOnCommitCallbacks(execute=True):
            submitted = self.client.post('/api/quizzes/submit-exam/', {'answers': [
                {'question_id': self.objective.pk, 'answer': 'B'},
                {'question_id': self.subjective.pk, 'answer': '利率受期限影响。'},
                {'question_id': unverified.pk, 'answer': '比较期限和现金流。'},
            ]}, format='json')
        self.assertEqual(submitted.status_code, 202, submitted.data)
        exam = QuizExam.objects.get(pk=submitted.data['exam_id'])
        self.assertFalse(exam.requires_ulr)
        objective = exam.results.get(question=self.objective)
        self.assertNotIn('ulr_grading_version', objective.question_snapshot)
        self.assertEqual(exam.results.get(question=self.subjective).question_snapshot['rubric'], rubric)
        old_item = exam.results.get(question=unverified)
        old_item.question_snapshot.pop('rubric')
        old_item.save(update_fields=['question_snapshot'])
        Question.objects.filter(pk=self.objective.pk).update(correct_answer='A')

        with override_settings(DEBUG=False, UNIMIND_LEARNING_RUNTIME='ulr'), \
                patch('quizzes.ai_workflow._grade_answer', side_effect=grade_ok) as model, \
                patch('quizzes.ai_workflow._queue_experience_verification'), \
                self.captureOnCommitCallbacks(execute=True):
            run_exam_grading(self.user.pk, exam.pk)
        model.assert_called_once()
        self.assertEqual(model.call_args.args[0].pk, self.subjective.pk)
        exam.refresh_from_db()
        objective.refresh_from_db()
        old_item.refresh_from_db()
        self.assertEqual((exam.status, exam.total_score, exam.failed_count, exam.requires_ulr), ('partial', 10, 2, True))
        self.assertEqual((objective.status, objective.user_answer, objective.question_snapshot['correct_answer']),
                         ('failed', 'B', 'B'))
        self.assertEqual((old_item.status, old_item.user_answer), ('failed', '比较期限和现金流。'))

    @override_settings(UNIMIND_LEARNING_RUNTIME='ulr')
    def test_exam_grading_stops_after_learning_access_is_revoked(self):
        from users.models import UserAccessProfile

        profile = UserAccessProfile.objects.create(user=self.user)
        submitted, _ = self.submit()
        self.assertEqual(submitted.status_code, 202, submitted.data)
        exam = QuizExam.objects.get(pk=submitted.data['exam_id'])

        def revoke(question, answer, *, language):
            UserAccessProfile.objects.filter(pk=profile.pk).update(blocked_permissions=['quiz.exam'])
            return grade_ok(question, answer, language=language)

        with patch('quizzes.ai_workflow._grade_answer', side_effect=revoke) as model, \
                patch('quizzes.ai_workflow._apply_memorix_status') as memorix, \
                patch('quizzes.ai_workflow._queue_experience_verification') as experience, \
                self.captureOnCommitCallbacks(execute=True):
            run_exam_grading(self.user.pk, exam.pk)
        model.assert_called_once()
        memorix.assert_not_called()
        experience.assert_not_called()
        exam.refresh_from_db()
        self.assertEqual((exam.status, exam.total_score, exam.failed_count), ('failed', 0, 2))
        self.assertEqual(list(exam.results.order_by('position').values_list('user_answer', flat=True)),
                         ['B', '利率期限结构有三种理论。'])

    def test_ulr_handoff_keeps_incomplete_submission_ungraded(self):
        with override_settings(DEBUG=False, UNIMIND_LEARNING_RUNTIME='legacy'):
            submitted, _ = self.submit()
        self.assertEqual(submitted.status_code, 202, submitted.data)
        exam = QuizExam.objects.get(pk=submitted.data['exam_id'])
        self.assertFalse(exam.requires_ulr)
        exam.results.filter(question=self.objective).delete()

        with override_settings(DEBUG=False, UNIMIND_LEARNING_RUNTIME='ulr'), \
                patch('quizzes.ai_workflow._grade_answer', side_effect=grade_ok) as model, \
                patch('quizzes.ai_workflow._apply_memorix_status') as memorix, \
                patch('quizzes.ai_workflow._queue_experience_verification'), \
                self.captureOnCommitCallbacks(execute=True):
            run_exam_grading(self.user.pk, exam.pk)
            run_exam_grading(self.user.pk, exam.pk)
        model.assert_not_called()
        memorix.assert_not_called()
        exam.refresh_from_db()
        item = exam.results.get()
        self.assertEqual((exam.status, exam.total_questions, exam.graded_count, exam.failed_count), ('failed', 2, 0, 2))
        self.assertIn('原始作答记录不完整', exam.last_error)
        self.assertEqual((item.user_answer, item.status, exam.total_score), ('利率期限结构有三种理论。', 'failed', 0))
        detail = self.client.get(f'/api/quizzes/exams/{exam.pk}/').data
        self.assertEqual((detail['status'], detail['failed_count'], detail['pending_count']), ('failed', 2, 0))
        self.assertIn('原始作答记录不完整', detail['summary_text'])

    def test_lost_queue_delivery_and_interrupted_finalization_can_resume(self):
        response, _ = self.submit()
        exam_id = response.data['exam_id']
        detail_url = f'/api/quizzes/exams/{exam_id}/'
        expired = timezone.now() - GRADING_RECOVERY_DELAY - timedelta(seconds=1)
        QuizExam.objects.filter(pk=exam_id).update(grading_queued_at=expired)
        self.assertTrue(self.client.get(detail_url).data['can_resume'])
        with patch('quizzes.views_exam.dispatch_exam_grading') as dispatch, self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(f'{detail_url}retry/', {}, format='json').status_code, 202)
            self.assertEqual(self.client.post(f'{detail_url}retry/', {}, format='json').status_code, 200)
        dispatch.assert_called_once_with(self.user.pk, exam_id)

        with patch('quizzes.ai_workflow._grade_answer', side_effect=grade_ok), \
                patch('quizzes.ai_workflow._queue_experience_verification'), \
                patch('quizzes.ai_workflow._create_exam_notification', side_effect=RuntimeError('synthetic interruption')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic interruption'):
                run_exam_grading(self.user.pk, exam_id)
        exam = QuizExam.objects.get(pk=exam_id)
        self.assertEqual(exam.status, 'grading')
        self.assertIsNone(exam.notified_at)
        self.assertEqual(exam.results.filter(status='graded', attempts=1).count(), 2)
        QuizExam.objects.filter(pk=exam_id).update(started_at=expired)
        with patch('quizzes.views_exam.dispatch_exam_grading'):
            self.assertEqual(self.client.post(f'{detail_url}retry/', {}, format='json').status_code, 202)
        with patch('quizzes.ai_workflow._grade_answer') as model:
            run_exam_grading(self.user.pk, exam_id)
            run_exam_grading(self.user.pk, exam_id)
        model.assert_not_called()
        exam.refresh_from_db()
        self.assertEqual((exam.status, exam.total_score), ('completed', 20))
        self.assertEqual(Notification.objects.filter(recipient=self.user, ntype='practice_result',
                                                      link=f'/tests/results/{exam_id}').count(), 1)

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
