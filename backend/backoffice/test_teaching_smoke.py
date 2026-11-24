"""Isolated migration smoke; model and notification providers are never called."""
import json
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.exceptions import ValidationError
from django.http import Http404
from django.utils import timezone

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

    @override_settings(DEBUG=True, UNIMIND_ULR_PROTOTYPE=True, UNIMIND_DSH_TEACHING_ENABLED=False)
    def test_ulr_parse_discards_candidates_after_kp_moves(self):
        data = {'kind': 'parse', 'kp_ids': [self.kp.pk], 'raw_text': '合成题干。', 'request_id': str(uuid4())}
        launched = teaching.launch(self.request, data)

        def provider(*args, **kwargs):
            KnowledgePoint.objects.filter(pk=self.kp.pk).update(institution=self.other)
            question = {'question': data['raw_text'], 'q_type': 'subjective', 'subjective_type': 'short',
                        'options': None, 'answer': '', 'grading_points': None, 'difficulty_level': 'normal'}
            return {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [{
                'function': {'name': 'submit_questions', 'arguments': json.dumps({'questions': [question]})},
            }]}}]}

        with patch('ai_engine.service.AIEngine.call_provider', side_effect=provider) as call:
            run_teaching_task(launched['id'])
            run_teaching_task(launched['id'])
        call.assert_called_once()
        task = ContentPipelineTask.objects.get(pk=launched['id'])
        self.assertEqual(task.status, 'failed')
        self.assertFalse(task.result)
        self.assertFalse(Question.objects.exists())

    @override_settings(DEBUG=False, UNIMIND_LEARNING_RUNTIME='ulr')
    def test_ulr_requeues_a_lost_delivery_on_the_original_teaching_task(self):
        original = {'kind': 'parse', 'kp_ids': [self.kp.pk], 'raw_text': '合成旧任务资料'}
        task = self.task(status='pending', payload=original, request_id=str(uuid4()))
        request = {'id': task.pk, 'request_id': str(uuid4())}
        self.assertFalse(teaching.task_detail(self.request, request)['can_resume'])
        ContentPipelineTask.objects.filter(pk=task.pk).update(updated_at=timezone.now() - timedelta(minutes=6))
        self.assertTrue(teaching.task_detail(self.request, request)['can_resume'])
        self.assertFalse(teaching.task_detail(SimpleNamespace(user=self.admin2), request)['can_resume'])
        with self.assertRaises(ValidationError):
            teaching.retry(SimpleNamespace(user=self.admin2), request)

        with patch('backoffice.tasks.run_teaching_task.delay', side_effect=RuntimeError('synthetic broker outage')), \
                self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(teaching.retry(self.request, request)['id'], task.pk)
        self.assertTrue(teaching.task_detail(self.request, request)['can_resume'])
        with patch('backoffice.tasks.run_teaching_task.delay') as dispatch, self.captureOnCommitCallbacks(execute=True):
            resumed = teaching.retry(self.request, request)
            duplicate = teaching.retry(self.request, request)
        self.assertEqual((resumed['id'], duplicate['id']), (task.pk, task.pk))
        self.assertEqual(resumed['request_id'], task.request_id)
        self.assertTrue(resumed['payload']['requires_ulr'])
        self.assertFalse(teaching.task_detail(self.request, request)['can_resume'])
        dispatch.assert_called_once_with(task.pk)

        parsed = {'text': '原资料的候选题', 'correct_answer': '合成答案'}
        with patch('ai_engine.ai_service.AIService.parse_questions_from_text', return_value=[parsed]) as parse:
            run_teaching_task(task.pk)
            run_teaching_task(task.pk)
        parse.assert_called_once_with(original['raw_text'])
        task.refresh_from_db()
        self.assertEqual((task.status, task.payload), ('review', {**original, 'requires_ulr': True}))
        self.assertEqual(task.result['questions'][0]['question'], parsed['text'])
        self.assertEqual(ContentPipelineTask.objects.count(), 1)
        self.assertFalse(Question.objects.exists())

    @override_settings(DEBUG=False, UNIMIND_LEARNING_RUNTIME='ulr')
    def test_ulr_keeps_an_adopted_teaching_task_on_ulr_after_failure(self):
        original = {'kind': 'parse', 'kp_ids': [self.kp.pk], 'raw_text': '合成教研资料'}
        task = self.task(status='pending', payload=original)

        def interrupted(_):
            claimed = ContentPipelineTask.objects.get(pk=task.pk)
            self.assertEqual(claimed.status, 'running')
            self.assertTrue(claimed.payload.get('requires_ulr'))
            raise RuntimeError('synthetic interruption')

        with patch('ai_engine.ai_service.AIService.parse_questions_from_text', side_effect=interrupted) as parse:
            run_teaching_task(task.pk)
        parse.assert_called_once_with(original['raw_text'])
        task.refresh_from_db()
        self.assertEqual(task.status, 'failed')
        self.assertEqual(task.payload, {**original, 'requires_ulr': True})

        retry = {'id': task.pk, 'request_id': str(uuid4())}
        with override_settings(UNIMIND_LEARNING_RUNTIME='legacy', UNIMIND_DSH_TEACHING_ENABLED=True), \
                self.assertRaisesMessage(ValidationError, '需要 ULR'):
            teaching.retry(self.request, retry)
        with patch('backoffice.tasks.run_teaching_task.delay') as dispatch, self.captureOnCommitCallbacks(execute=True):
            restarted = teaching.retry(self.request, retry)
            self.assertEqual(restarted['id'], teaching.retry(self.request, retry)['id'])
        dispatch.assert_called_once_with(restarted['id'])
        parsed = {'text': '合成题目', 'correct_answer': '合成答案'}
        with patch('ai_engine.ai_service.AIService.parse_questions_from_text', return_value=[parsed]) as parse:
            run_teaching_task(restarted['id'])
            run_teaching_task(restarted['id'])
        parse.assert_called_once_with(original['raw_text'])
        recovered = ContentPipelineTask.objects.get(pk=restarted['id'])
        self.assertEqual(recovered.status, 'review')
        self.assertEqual(recovered.result['questions'][0]['question'], parsed['text'])
        self.assertFalse(Question.objects.exists())

    @override_settings(DEBUG=True, UNIMIND_ULR_PROTOTYPE=True, UNIMIND_DSH_TEACHING_ENABLED=False)
    def test_ulr_arc_stops_when_reviewer_uses_an_invalid_lookup(self):
        task = self.task(status='pending', payload={'kind': 'arc', 'kp_ids': [self.kp.pk], 'count': 1})
        question = {'question': '合成审题题目', 'q_type': 'subjective', 'subjective_type': 'short',
                    'options': None, 'answer': '参考答案', 'grading_points': ['要点'], 'difficulty_level': 'normal'}

        def provider(messages, *, operation, **kwargs):
            name, result = ('submit_questions', {'questions': [question]}) if operation == 'pipeline.author' else (
                'search_similar_questions', {'kp_code': self.kp.code, 'limit': 100})
            return {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [{
                'id': 'call', 'function': {'name': name, 'arguments': json.dumps(result)},
            }]}}]}

        with patch('ai_engine.service.AIEngine.call_provider', side_effect=provider) as call, \
             patch('ai_assistant.services.dsh_generation.generate') as dsh:
            run_teaching_task(task.pk)
        self.assertEqual(call.call_count, 2)
        dsh.assert_not_called()
        task.refresh_from_db()
        self.assertEqual(task.status, 'failed')
        self.assertFalse(task.result)
        self.assertFalse(Question.objects.exists())

    @override_settings(DEBUG=True, UNIMIND_ULR_PROTOTYPE=True, UNIMIND_DSH_TEACHING_ENABLED=False)
    def test_ulr_reviewer_replays_a_text_lookup_as_a_tool_call(self):
        from quizzes.services.adversarial_pipeline import _reviewer_evaluate

        review = {'score': 0.8, 'feedback': '知识点一致。',
                  'dimensions': {'discrimination': 0.8, 'clarity': 0.8, 'coverage': 0.8}}

        def provider(messages, **kwargs):
            if messages[-1]['role'] == 'user':
                text = ('<function_calls><invoke name="lookup_knowledge_point_definition">'
                        f'<parameter name="code">{self.kp.code}</parameter></invoke></function_calls>')
                return {'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': text}}]}
            request, receipt = messages[-2:]
            self.assertIsNone(request['content'])
            call, = request['tool_calls']
            self.assertEqual(receipt['tool_call_id'], call['id'])
            self.assertEqual(json.loads(receipt['content'])['code'], self.kp.code)
            return {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [{
                'id': 'review', 'function': {'name': 'submit_review', 'arguments': json.dumps(review)},
            }]}}]}

        with patch('ai_engine.service.AIEngine.call_provider', side_effect=provider) as call:
            self.assertEqual(_reviewer_evaluate({'question': '合成审题题目', 'kp_code': self.kp.code},
                                               institution=self.scope, strict_scope=True), review)
        self.assertEqual(call.call_count, 2)

    @override_settings(DEBUG=True, UNIMIND_ULR_PROTOTYPE=True, UNIMIND_DSH_TEACHING_ENABLED=False)
    def test_ulr_workbench_discards_a_reply_after_operator_is_disabled(self):
        bot = Bot.objects.create(name='Workbench', bot_type='exam_generator', institution=self.scope)
        conversation = Conversation.objects.create(user=self.admin, bot=bot, conversation_id=uuid4())
        task = self.task(status='pending', payload={'kind': 'chat', 'bot_id': bot.pk,
            'conversation_id': str(conversation.conversation_id), 'message': '给学员准备通知。'})

        def provider(messages, **kwargs):
            if messages[-2]['role'] != 'tool':
                return {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [{
                    'id': 'notice', 'type': 'function', 'function': {'name': 'send_notification',
                        'arguments': json.dumps({'student_id': self.learner.pk, 'content': '待审通知'})},
                }]}}]}
            draft = json.loads(messages[-2]['content'])
            self.assertTrue(draft['requires_confirmation'])
            self.assertNotIn('preview_token', draft['preview'])
            User.objects.filter(pk=self.admin.pk).update(is_active=False)
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': '合成答复'}}]}

        with patch('ai_engine.service.AIEngine.call_provider', side_effect=provider) as call, \
             patch('ai_assistant.services.dsh_generation.generate') as dsh:
            run_teaching_task(task.pk)
        self.assertEqual(call.call_count, 2)
        dsh.assert_not_called()
        task.refresh_from_db()
        self.assertEqual(task.status, 'failed')
        self.assertFalse(task.result)
        self.assertFalse(AIChatMessage.objects.filter(conversation_id=conversation.conversation_id).exists())
        self.assertFalse(ContentPipelineTask.objects.filter(payload__kind='notification').exists())

    @override_settings(DEBUG=True, UNIMIND_ULR_PROTOTYPE=True, UNIMIND_DSH_TEACHING_ENABLED=False)
    def test_ulr_bulk_discards_drafts_when_an_audited_point_moves(self):
        task = self.task(status='pending', payload={'kind': 'bulk', 'subject': self.kp.subject, 'count': 1,
            'difficulty_dist': {'normal': 1}, 'type_dist': {'subjective': 1}})
        draft = {'question': '合成审计题目', 'q_type': 'subjective', 'subjective_type': 'short', 'options': None,
                 'answer': '参考答案', 'grading_points': ['要点'], 'difficulty_level': 'normal'}
        audit = {'detected_difficulty': 'normal', 'difficulty_match': True, 'difficulty_mismatch_reason': '',
                 'knowledge_tags': [self.kp.code], 'question_type': 'subjective', 'subjective_type': 'short',
                 'answer_correct': True, 'answer_accuracy_note': '', 'bloom_level': 'apply'}

        def provider(messages, *, operation, **kwargs):
            if operation == 'pipeline.author':
                name, result = 'submit_questions', {'questions': [draft]}
            else:
                self.assertEqual(operation, 'pipeline.classifier')
                KnowledgePoint.objects.filter(pk=self.kp.pk).update(institution=self.other)
                name, result = 'submit_classification', audit
            return {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [{
                'function': {'name': name, 'arguments': json.dumps(result)},
            }]}}]}

        with patch('ai_engine.service.AIEngine.call_provider', side_effect=provider) as call:
            run_teaching_task(task.pk)
        self.assertEqual(call.call_count, 2)
        task.refresh_from_db()
        self.assertEqual(task.status, 'failed')
        self.assertFalse(task.result)
        self.assertFalse(Question.objects.exists())

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

    @override_settings(DEBUG=False, UNIMIND_LEARNING_RUNTIME='ulr')
    def test_ulr_confirms_saved_arc_parameters_and_dispatches_once(self):
        preview = {'kind': 'arc', 'kp_ids': [self.kp.pk], 'count': 2, 'difficulty': 'easy',
                   'types': ['subjective:short'], 'request_id': str(uuid4())}
        source = self.task(status='completed', payload={'kind': 'chat'},
            result={'confirmations': [{'type': 'arc', 'payload': preview}]})
        data = {**preview, 'source_task_id': source.pk}
        with patch('backoffice.tasks.run_teaching_task.delay') as dispatch, self.captureOnCommitCallbacks(execute=True):
            for invalid in (data, {**data, 'confirmed': True, 'count': 3},
                            {**data, 'confirmed': True, 'types': ['objective']}):
                with self.assertRaises(ValidationError):
                    teaching.launch(self.request, invalid)
            self.assertFalse(ContentPipelineTask.objects.filter(request_id=preview['request_id']).exists())
            first = teaching.launch(self.request, {**data, 'confirmed': True})
            second = teaching.launch(self.request, {**data, 'confirmed': True})
            self.assertEqual((first['id'], first['status']), (second['id'], 'pending'))
            dispatch.assert_not_called()
        dispatch.assert_called_once_with(first['id'])
        with patch('quizzes.services.adversarial_pipeline._execute_pipeline') as execute:
            run_teaching_task(first['id'])
            run_teaching_task(first['id'])
        execute.assert_called_once()
        self.assertEqual([kp.pk for kp in execute.call_args.args[1]], [self.kp.pk])
        self.assertEqual(execute.call_args.args[2], 2)
        self.assertEqual(execute.call_args.kwargs['difficulty'], 'easy')
        self.assertEqual(execute.call_args.kwargs['types'], ['subjective:short'])
        self.assertTrue(execute.call_args.kwargs['review_only'])

    @override_settings(DEBUG=False, UNIMIND_LEARNING_RUNTIME='ulr')
    def test_ulr_confirms_only_the_exact_notification_preview(self):
        from notifications.models import Notification

        preview = teaching.notification_preview(self.request,
            {'student_id': self.learner.pk, 'title': '原通知标题', 'content': '原通知正文'})
        confirmed = {**preview, 'confirmed': True}
        for bad in ({**confirmed, 'content': '改过的正文'},
                    {**confirmed, 'recipient': '改过的收件人显示名'},
                    {**confirmed, 'request_id': str(uuid4())},
                    {key: value for key, value in confirmed.items() if key != 'preview_token'}):
            with self.assertRaises(ValidationError):
                teaching.send_notification(self.request, bad)
        with self.assertRaises(ValidationError):
            teaching.send_notification(SimpleNamespace(user=self.admin2), confirmed)
        self.assertFalse(Notification.objects.exists())
        with patch('notifications.tasks_reminder.send_notification_email.delay') as email, \
                self.captureOnCommitCallbacks(execute=True):
            sent = teaching.send_notification(self.request, confirmed)
            self.assertEqual(teaching.send_notification(self.request, confirmed), sent)
            receipt = ContentPipelineTask.objects.get(request_id=preview['request_id'])
            teaching.delete_task(self.request, {'id': receipt.pk, 'confirmed': True})
            self.assertFalse(teaching.owned_tasks(self.request).filter(pk=receipt.pk).exists())
            self.assertEqual(teaching.send_notification(self.request, confirmed), sent)
            with self.assertRaises(ValidationError):
                teaching.send_notification(self.request, {**confirmed, 'title': '改过的标题'})
            self.assertEqual(Notification.objects.get().content, preview['content'])
            email.assert_not_called()
        email.assert_called_once_with(sent['id'])

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
