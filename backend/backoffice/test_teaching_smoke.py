"""Isolated migration smoke; model and notification providers are never called."""
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.exceptions import ValidationError
from django.http import Http404

from ai_assistant.models import AIChatMessage, Bot, Conversation
from quizzes.models import ContentPipelineTask, KnowledgePoint, Question
from users.models import User, Institution
from . import teaching
from .tasks import run_teaching_task
from .teaching_executor import TeachingExecutor


class TeachingSmoke(TestCase):
    def setUp(self):
        self.scope = Institution.objects.create(name='Korson smoke', slug='korson-smoke')
        self.other = Institution.objects.create(name='Other smoke', slug='other-smoke')
        self.admin = User.objects.create_superuser(username='teaching-admin', email='admin@example.test')
        self.admin2 = User.objects.create_superuser(username='teaching-admin-two', email='admin2@example.test')
        self.learner = User.objects.create_user(username='teaching-learner', institution=self.scope, institution_role='student', is_member=True)
        self.kp = KnowledgePoint.objects.create(name='Scoped knowledge', level='kp', institution=self.scope, subject='Smoke', code='smoke.1')
        self.foreign_kp = KnowledgePoint.objects.create(name='Foreign knowledge', level='kp', institution=self.other, subject='Smoke', code='smoke.2')
        self.request = SimpleNamespace(user=self.admin, auth='operator-one')
        self.setting = override_settings(UNIMIND_CONTENT_INSTITUTION_ID=str(self.scope.pk),
            UNIMIND_DIRECTUS_ADMIN_MAP={str(uuid4()): self.admin.pk, str(uuid4()): self.admin2.pk})
        self.setting.enable()
        self.addCleanup(self.setting.disable)
        self.candidate = {'kp_id': self.kp.pk, 'question': '<script>unsafe()</script> Plain question',
            'q_type': 'objective', 'options': {'A': 'One', 'B': 'Two', 'C': 'Three', 'D': 'Four'},
            'answer': 'A', 'difficulty_level': 'normal'}

    def task(self, **kwargs):
        return ContentPipelineTask.objects.create(created_by=self.admin, institution=self.scope, title='Smoke', **kwargs)

    def test_async_generation_and_confirmed_idempotent_save(self):
        data = {'kind': 'quick', 'kp_ids': [self.kp.pk], 'count': 1, 'request_id': str(uuid4())}
        with patch('backoffice.tasks.run_teaching_task.delay') as dispatch:
            with self.captureOnCommitCallbacks(execute=True):
                first = teaching.launch(self.request, data)
                second = teaching.launch(self.request, data)
            self.assertEqual(first['id'], second['id'])
            dispatch.assert_called_once_with(first['id'])
        with patch('quizzes.services.adversarial_pipeline._author_generate', return_value=[self.candidate]):
            run_teaching_task(first['id'])
            run_teaching_task(first['id'])
        self.assertFalse(Question.objects.exists())
        source = ContentPipelineTask.objects.get(pk=first['id'])
        self.assertEqual(source.status, 'review')
        data = {'id': source.pk, 'action': 'approve', 'question_indices': [0]}
        with self.assertRaises(ValidationError):
            teaching.review(self.request, data)
        data['confirmed'] = True
        teaching.review(self.request, data)
        teaching.review(self.request, data)
        self.assertEqual(Question.objects.filter(institution=self.scope).count(), 1)

    @override_settings(UNIMIND_DSH_TEACHING_ENABLED=True)
    def test_parse_candidates_require_scoped_kp_and_confirmation(self):
        data = {'kind': 'parse', 'kp_ids': [self.kp.pk], 'raw_text': '合成资料：久期是什么？答案：利率敏感度。', 'request_id': str(uuid4())}
        with override_settings(UNIMIND_DSH_TEACHING_ENABLED=False), self.assertRaises(ValidationError):
            teaching.launch(self.request, data)
        for bad in ({'kp_ids': [self.foreign_kp.pk]}, {'kp_ids': [self.kp.pk, self.foreign_kp.pk]}, {'raw_text': ' '}, {'raw_text': '题'*10001}):
            with self.assertRaises(ValidationError):
                teaching.launch(self.request, {**data, **bad})
        with patch('backoffice.tasks.run_teaching_task.delay') as dispatch:
            with self.captureOnCommitCallbacks(execute=True):
                first = teaching.launch(self.request, data)
                self.assertEqual(teaching.launch(self.request, data)['id'], first['id'])
            dispatch.assert_called_once_with(first['id'])
        parsed = {'text': '合成题目', 'q_type': 'subjective', 'subjective_type': 'short', 'options': {},
            'correct_answer': '合成答案', 'grading_points': ['合成要点'], 'analysis': '', 'difficulty_level': 'normal'}
        with patch('ai_engine.ai_service.AIService.parse_questions_from_text', return_value=[parsed]) as parse:
            run_teaching_task(first['id']); run_teaching_task(first['id'])
            parse.assert_called_once_with(data['raw_text'])
        task = ContentPipelineTask.objects.get(pk=first['id'])
        self.assertEqual(task.status, 'review')
        self.assertEqual(task.result['questions'][0]['kp_id'], self.kp.pk)
        self.assertFalse(Question.objects.exists())
        review = {'id': task.pk, 'action': 'approve', 'question_indices': [0]}
        with self.assertRaises(ValidationError):
            teaching.review(self.request, review)
        teaching.review(self.request, {**review, 'confirmed': True})
        teaching.review(self.request, {**review, 'confirmed': True})
        self.assertEqual(Question.objects.filter(institution=self.scope).count(), 1)
        failed = self.task(status='pending', payload={'kind': 'parse', 'kp_ids': [self.kp.pk], 'raw_text': '合成故障'})
        with patch('ai_engine.ai_service.AIService.parse_questions_from_text', side_effect=RuntimeError('fixture failure')):
            run_teaching_task(failed.pk)
        failed.refresh_from_db()
        self.assertEqual(failed.status, 'failed')
        self.assertIn('解析任务执行失败', failed.error_message)
        self.assertEqual(Question.objects.count(), 1)
        retry_source = self.task(status='failed', payload={'kind': 'parse', 'kp_ids': [self.kp.pk], 'raw_text': '重试资料'})
        with patch('backoffice.tasks.run_teaching_task.delay') as dispatch:
            with self.captureOnCommitCallbacks(execute=True):
                retried = teaching.retry(self.request, {'id': retry_source.pk, 'request_id': str(uuid4())})
            dispatch.assert_called_once_with(retried['id'])
        retried_task = ContentPipelineTask.objects.get(pk=retried['id'])
        self.assertEqual(retried_task.payload['raw_text'], '重试资料')
        self.assertEqual(retried_task.payload['kp_ids'], [self.kp.pk])

    def test_scope_and_history_are_bound_to_the_real_operator(self):
        with self.assertRaises(ValidationError):
            teaching.validate_kps([self.foreign_kp.pk])
        self.assertEqual(teaching.search_knowledge(self.request, {})['total'], 1)
        foreign_task = ContentPipelineTask.objects.create(created_by=self.admin, institution=self.other, title='Foreign')
        with self.assertRaises(Http404):
            teaching.task_detail(self.request, {'id': foreign_task.pk})
        bot = Bot.objects.create(name='Workbench', bot_type='exam_generator', system_prompt='Smoke')
        cid = uuid4()
        Conversation.objects.create(user=self.admin, bot=bot, conversation_id=cid)
        AIChatMessage.objects.create(user=self.admin, bot=bot, conversation_id=cid, role='assistant', content='Private draft', metadata={'questions': [self.candidate]})
        self.assertEqual(teaching.history(self.request, {'conversation_id': str(cid)})['items'][0]['content'], 'Private draft')
        source = AIChatMessage.objects.get(user=self.admin, conversation_id=cid)
        source.metadata = {'generated_questions': [self.candidate]}
        source.save(update_fields=['metadata'])
        restored = teaching.restore_draft(self.request, {'message_id': source.pk, 'request_id': str(uuid4())})
        restored_again = teaching.restore_draft(self.request, {'message_id': source.pk, 'request_id': str(uuid4())})
        self.assertEqual(restored['id'], restored_again['id'])
        self.assertEqual(restored['status'], 'review')
        with self.assertRaises(Http404):
            teaching.history(SimpleNamespace(user=self.admin2), {'conversation_id': str(cid)})
        task = self.task(status='completed', payload={'kind': 'chat', 'conversation_id': str(cid)})
        with self.assertRaises(Http404):
            teaching.task_detail(SimpleNamespace(user=self.admin2), {'id': task.pk})

    def test_notification_tools_only_preview(self):
        executor = TeachingExecutor(self.admin)
        with patch('notifications.models.Notification.objects.create') as sender:
            preview = executor._handle_send_notification({'student_id': self.learner.pk, 'title': 'Smoke', 'content': 'Preview only'})
            report_guard = executor._handle_save_questions_to_bank({})
            self.assertFalse(preview['sent'])
            self.assertIn('error', report_guard)
            self.assertEqual(len(executor.confirmations), 1)
            with self.assertRaises(ValidationError):
                teaching.send_notification(self.request, {'student_id': self.learner.pk, 'content': 'No confirmation'})
            sender.assert_not_called()

    def test_manually_enrolled_student_does_not_need_legacy_institution(self):
        from users.learning import set_course_student_status
        student = User.objects.create_user(username='new-course-student')
        set_course_student_status(student, True, actor=self.admin)
        self.assertEqual(teaching.student({'student_id': student.pk}).pk, student.pk)
        self.assertEqual(teaching.notification_preview(self.request,
            {'student_id': student.pk, 'title': 'Preview', 'content': 'Not sent'})['student_id'], student.pk)
        set_course_student_status(student, False, actor=self.admin)
        with self.assertRaises(Http404):
            teaching.student({'student_id': student.pk})
            sender.return_value = SimpleNamespace(pk=900)
            preview_data = {**preview['preview'], 'confirmed': True}
            first = teaching.send_notification(self.request, preview_data)
            second = teaching.send_notification(self.request, preview_data)
            self.assertEqual(first, second)
            sender.assert_called_once()

    def test_arc_and_bulk_reuse_services_without_saving(self):
        from quizzes.services.adversarial_pipeline import _execute_pipeline, _get_subject_knowledge_points, _get_reviewer_tool_executor
        from quizzes.services.bulk_pipeline import _execute_bulk_pipeline
        self.assertEqual([self.kp.pk], [row.pk for row in _get_subject_knowledge_points([self.kp], self.scope, strict_scope=True)])
        arc = self.task(status='running', payload={})
        with patch('quizzes.services.adversarial_pipeline._author_generate', return_value=[dict(self.candidate)]), \
             patch('quizzes.services.adversarial_pipeline._reviewer_evaluate', return_value={'score': 1, 'feedback': 'OK'}), \
             patch('quizzes.services.adversarial_pipeline._classifier_tag', return_value={}), \
             patch('quizzes.services.adversarial_pipeline._classifier_batch_report', return_value={}):
            _execute_pipeline(arc, [self.kp], 1, institution=self.scope, strict_scope=True, review_only=True)
        arc.refresh_from_db()
        self.assertEqual(arc.status, 'review')
        bulk = self.task(status='running', payload={})
        with patch('quizzes.services.bulk_pipeline._author_generate', return_value=[dict(self.candidate)]), \
             patch('quizzes.services.bulk_pipeline._classifier_tag', return_value={}):
            _execute_bulk_pipeline(bulk, 'Smoke', 1, {'normal': 1}, {'objective': 1}, institution=self.scope, strict_scope=True, review_only=True)
        bulk.refresh_from_db()
        self.assertEqual(bulk.status, 'review')
        self.assertEqual(bulk.result['questions_saved'], 0)
        self.assertFalse(Question.objects.exists())
