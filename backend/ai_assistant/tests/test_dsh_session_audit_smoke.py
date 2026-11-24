import hashlib
from datetime import timedelta
from io import StringIO
import json
from unittest.mock import patch
from uuid import UUID, uuid4

from asgiref.sync import async_to_sync
from django.core.management import call_command, CommandError
from django.contrib.auth import get_user_model
from django.utils import timezone
import pytest

from ai_assistant.models import AIChatMessage, Bot, Conversation, ConversationProject, ProjectLearningEvent
from users.models import AIUsageReservation, CourseStudentStatus, WeeklyAIQuotaConfig, WeeklyAIUsage


@pytest.mark.django_db
def test_legacy_arc_settles_its_result_with_the_review_draft(user, settings, django_capture_on_commit_callbacks):
    from django.test import override_settings
    from ai_engine.observability import runtime_observation
    from quizzes.models import ContentPipelineTask, KnowledgePoint
    from quizzes.services import adversarial_pipeline as pipeline
    from quizzes.tasks import run_adversarial_pipeline_task

    settings.UNIMIND_LEARNING_RUNTIME = 'ulr'
    settings.UNIMIND_DSH_ENABLED = False
    point = KnowledgePoint.objects.create(code='arc-settlement', name='合成考点')
    other = KnowledgePoint.objects.create(code='arc-outdated', name='旧消息中的考点')
    failed = ContentPipelineTask.objects.create(created_by=user, title='合成旧 ARC 出题', task_type='ai_generate',
        status='running', payload={'kp_ids': [point.pk], 'questions_per_kp': 1})
    with patch.object(run_adversarial_pipeline_task, 'delay') as queued, django_capture_on_commit_callbacks(execute=True):
        task_id = pipeline.run_adversarial_pipeline([point.pk], user, questions_per_kp=1)
    completed = ContentPipelineTask.objects.get(pk=task_id)
    assert completed.payload['requires_ulr'] is True
    envelope = queued.call_args.kwargs
    assert envelope['task_id'] == completed.pk
    outputs = {
        'pipeline.author': ('submit_questions', {'questions': [{'question': '合成题目', 'q_type': 'subjective',
            'subjective_type': 'short', 'options': None, 'answer': '合成答案', 'grading_points': ['评分点'],
            'difficulty_level': 'normal'}]}),
        'pipeline.reviewer': ('submit_review', {'score': 1, 'feedback': '合成评审',
            'dimensions': {'clarity': 1, 'coverage': 1, 'discrimination': 1}}),
        'pipeline.classifier': ('submit_classification', {'detected_difficulty': 'normal', 'difficulty_match': True,
            'difficulty_mismatch_reason': '', 'knowledge_tags': [point.code], 'question_type': 'subjective',
            'subjective_type': 'short', 'answer_correct': True, 'answer_accuracy_note': '', 'bloom_level': 'apply'}),
    }

    def model(messages, **kwargs):
        name, result = outputs[kwargs['operation']]
        assert runtime_observation.get()['runtime'] == 'ulr'
        assert name in {tool['function']['name'] for tool in kwargs['tools']}
        return {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [{
            'function': {'name': name, 'arguments': json.dumps(result)},
        }]}}]}

    delayed = {**envelope, 'kp_ids': [other.pk], 'questions_per_kp': 2, 'difficulty': 'hard'}
    with patch('ai_engine.service.AIEngine.call_provider', side_effect=model) as provider, \
            patch.object(pipeline, '_execute_pipeline', wraps=pipeline._execute_pipeline) as execute:
        with patch.object(ContentPipelineTask.objects, 'create', side_effect=RuntimeError('合成待审草稿写入失败')):
            run_adversarial_pipeline_task(failed.pk, [point.pk], 1)
        with override_settings(UNIMIND_LEARNING_RUNTIME='legacy', UNIMIND_ULR_PROTOTYPE=False):
            run_adversarial_pipeline_task(**delayed)
            run_adversarial_pipeline_task(**envelope)
        assert execute.call_count == 2
        assert execute.call_args.args[1:] == ([point], 1)
        assert execute.call_args.kwargs['difficulty'] == 'normal'
        assert [call.kwargs['operation'] for call in provider.call_args_list] == list(outputs) * 2
    failed.refresh_from_db()
    completed.refresh_from_db()
    assert failed.status == 'failed' and not failed.result and failed.error_message == '合成待审草稿写入失败'
    draft = ContentPipelineTask.objects.get(status='review')
    assert completed.status == 'completed' and draft.payload['source_task_id'] == completed.pk
    assert draft.result == completed.result and draft.result['questions'][0]['question'] == '合成题目'


@pytest.mark.django_db(transaction=True)
def test_ulr_reuses_legacy_bulk_delivery_and_settles_all_questions_together(admin_client, admin_user, user, settings):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import connection, connections, transaction
    from django.test import override_settings
    from ai_assistant.services.ulr_structured import teaching_enabled
    from ai_engine.observability import runtime_observation
    from quizzes.models import ContentPipelineTask, KnowledgePoint, Question
    from quizzes.services import bulk_pipeline
    from quizzes.tasks import run_bulk_pipeline_task

    settings.UNIMIND_LEARNING_RUNTIME = 'ulr'
    settings.UNIMIND_DSH_ENABLED = False
    settings.UNIMIND_DIRECTUS_ADMIN_MAP = {str(uuid4()): admin_user.pk, str(uuid4()): user.pk}
    subject = '合成批量出题'
    for index in range(2):
        KnowledgePoint.objects.create(name=f'合成考点 {index}', code=f'BULK-{index}', subject=subject)
    failed, resumed = [ContentPipelineTask.objects.create(created_by=user, title=subject, task_type='ai_generate',
        status='running', payload={'bulk_mode': True, 'subject': subject, 'total_target': 20,
            'difficulty_dist': {'normal': 1}, 'type_dist': {'objective': 1}}) for _ in range(2)]
    running, release = Event(), Event()
    hold = False
    modes = []
    saved_task = ContentPipelineTask.save

    def generate(points, **kwargs):
        modes.append((teaching_enabled('pipeline.author'), runtime_observation.get()['runtime']))
        if hold and not running.is_set():
            running.set()
            assert release.wait(timeout=10)
        point, = points
        return [{'question': point.name, 'kp_id': point.pk, 'q_type': 'objective', 'answer': 'A',
                 'options': ['A', 'B']}]

    def save_task(task, *args, **kwargs):
        if task.pk == failed.pk and task.status == 'completed':
            assert Question.objects.count() == 2
            raise RuntimeError('合成批量出题结算失败')
        return saved_task(task, *args, **kwargs)

    def deliver(task):
        run_bulk_pipeline_task(task.pk, subject, 20, {'normal': 1}, {'objective': 1})

    def deliver_in_worker():
        try:
            deliver(resumed)
        finally:
            connections.close_all()

    with patch.object(bulk_pipeline, '_author_generate', side_effect=generate) as author, \
            patch.object(bulk_pipeline, '_classifier_tag', return_value={}), \
            patch.object(ContentPipelineTask, 'save', autospec=True, side_effect=save_task):
        with transaction.atomic(), override_settings(UNIMIND_LEARNING_RUNTIME='legacy', UNIMIND_ULR_PROTOTYPE=False), \
                patch.object(bulk_pipeline, '_classifier_tag', side_effect=[{}, SystemExit('合成进程退出')]):
            with pytest.raises(SystemExit, match='合成进程退出'):
                deliver(resumed)
            assert Question.objects.count() == 1
            transaction.set_rollback(True)
        assert modes == [(False, 'legacy')] * 2

        deliver(failed)
        failed.refresh_from_db()
        assert failed.status == 'failed' and failed.error_message == '合成批量出题结算失败'
        assert not failed.result and not Question.objects.exists()

        with patch.object(bulk_pipeline, '_classifier_tag', side_effect=[{}, SystemExit('合成进程退出')]):
            with pytest.raises(SystemExit, match='合成进程退出'):
                deliver(resumed)
        resumed.refresh_from_db()
        assert resumed.status == 'running' and not resumed.result and not Question.objects.exists()
        assert resumed.payload['requires_ulr'] is True
        prior_calls = author.call_count

        with override_settings(UNIMIND_LEARNING_RUNTIME='legacy', UNIMIND_ULR_PROTOTYPE=False):
            assert not teaching_enabled('pipeline.author')
            if connection.vendor == 'postgresql':
                hold = True
                with ThreadPoolExecutor(max_workers=1) as worker:
                    execution = worker.submit(deliver_in_worker)
                    try:
                        assert running.wait(timeout=5)
                        deliver(resumed)
                        assert author.call_count == prior_calls + 1 and not Question.objects.exists()
                        ContentPipelineTask.objects.filter(pk=resumed.pk).update(updated_at=timezone.now() - timedelta(hours=1))
                        with patch.object(run_bulk_pipeline_task, 'delay') as queued:
                            response = admin_client.post(f'/api/quizzes/admin/pipeline-tasks/{resumed.pk}/retry/')
                        assert response.status_code == 200 and response.data['id'] == resumed.pk
                        queued.assert_not_called()
                    finally:
                        release.set()
                    execution.result(timeout=10)
            else:
                deliver(resumed)
            deliver(resumed)
            assert author.call_count == prior_calls + 2
            assert modes[2:] == [(True, 'ulr')] * (len(modes) - 2)
            assert not teaching_enabled('pipeline.author')

    resumed.refresh_from_db()
    assert resumed.status == 'completed' and resumed.result['questions_saved'] == 2
    assert Question.objects.count() == 2


@pytest.mark.django_db(transaction=True)
def test_dsh_migration_gate_holds_failed_legacy_bulk_after_partial_publication(admin_client, admin_user, user, settings, tmp_path):
    from types import SimpleNamespace

    from django.db import connection, transaction
    from rest_framework.exceptions import ValidationError

    from backoffice import teaching
    from quizzes.models import ContentPipelineTask, KnowledgePoint, Question
    from quizzes.services import bulk_pipeline
    from quizzes.tasks import run_bulk_pipeline_task

    settings.UNIMIND_DSH_ENABLED = settings.UNIMIND_ULR_PROTOTYPE = False
    settings.UNIMIND_LEARNING_RUNTIME = 'legacy'
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    settings.UNIMIND_DIRECTUS_ADMIN_MAP = {str(uuid4()): admin_user.pk, str(uuid4()): user.pk}
    Bot.objects.create(is_xiaoyu=True, name='小宇')
    subject = '合成旧批量出题'
    for index in range(2):
        KnowledgePoint.objects.create(name=f'合成考点 {index}', code=f'PARTIAL-{index}', subject=subject)
    fields = {'created_by': admin_user, 'title': subject, 'task_type': 'ai_generate'}
    payload = {'bulk_mode': True, 'subject': subject, 'total_target': 20,
               'difficulty_dist': {'normal': 1}, 'type_dist': {'objective': 1}}
    task = ContentPipelineTask.objects.create(**fields, status='running', payload=payload)
    ContentPipelineTask.objects.create(**fields, status='failed', progress=2,
        payload={**payload, 'current_stage': 'select_kps'})

    def generate(points, **kwargs):
        point, = points
        return [{'question': point.name, 'kp_id': point.pk, 'q_type': 'objective', 'answer': 'A', 'options': ['A', 'B']}]

    with patch.object(bulk_pipeline, '_author_generate', side_effect=generate), \
            patch.object(bulk_pipeline, '_classifier_tag', side_effect=[{}, RuntimeError('合成下一批失败')]):
        run_bulk_pipeline_task(task.pk, subject, 20, {'normal': 1}, {'objective': 1})
    task.refresh_from_db()
    assert (task.status, task.payload['current_stage'], Question.objects.count()) == ('failed', 'generating', 1)

    settings.UNIMIND_LEARNING_RUNTIME = 'ulr'
    report = StringIO()
    with pytest.raises(CommandError, match='未完成的迁移项'):
        call_command('audit_dsh_sessions', state_dir=str(tmp_path), api_url='http://127.0.0.1:8000', require_migrated=True,
                     stdout=report)
    audit = json.loads(report.getvalue())
    assert audit['blockers'] == {'unsettled_legacy_question_pipelines': 1}
    assert audit['unsettled_question_pipeline_ids'] == [task.pk]
    with patch.object(run_bulk_pipeline_task, 'delay') as queue, patch('backoffice.tasks.run_teaching_task.delay') as teaching_queue:
        response = admin_client.post(f'/api/quizzes/admin/pipeline-tasks/{task.pk}/retry/')
        assert response.status_code == 409, response.data
        with transaction.atomic(), pytest.raises(ValidationError, match='可能已经入库'):
            teaching.retry(SimpleNamespace(user=admin_user), {'id': task.pk, 'request_id': str(uuid4())})
        queue.assert_not_called()
        teaching_queue.assert_not_called()
    task.refresh_from_db()
    assert task.status == 'failed' and ContentPipelineTask.objects.count() == 2 and Question.objects.count() == 1

    if connection.vendor == 'postgresql':
        question_ids = list(Question.objects.values_list('pk', flat=True))
        call_command('settle_legacy_bulk_task', task.pk, legacy_workers_stopped=True,
                     review_reference='synthetic-review-1', stdout=StringIO())
        with patch.object(run_bulk_pipeline_task, 'delay') as queue, \
                patch.object(bulk_pipeline, '_author_generate') as author:
            assert admin_client.post(f'/api/quizzes/admin/pipeline-tasks/{task.pk}/retry/').status_code == 200
            with transaction.atomic(), pytest.raises(ValidationError, match='已经结案'):
                teaching.retry(SimpleNamespace(user=admin_user), {'id': task.pk, 'request_id': str(uuid4())})
            run_bulk_pipeline_task(task.pk, subject, 20, {'normal': 1}, {'objective': 1})
            queue.assert_not_called()
            author.assert_not_called()
        assert list(Question.objects.values_list('pk', flat=True)) == question_ids
        assert ContentPipelineTask.objects.count() == 2


@pytest.mark.django_db(transaction=True)
def test_ulr_requeues_a_lost_bulk_delivery_on_the_original_task(admin_client, admin_user, user, settings):
    from quizzes.models import ContentPipelineTask, KnowledgePoint, Question
    from quizzes.services import adversarial_pipeline, bulk_pipeline
    from quizzes.tasks import QUESTION_PIPELINE_QUEUE_ERROR, run_adversarial_pipeline_task, run_bulk_pipeline_task
    from users.models import Institution

    settings.UNIMIND_LEARNING_RUNTIME = 'ulr'
    settings.UNIMIND_DSH_ENABLED = False
    settings.UNIMIND_DIRECTUS_ADMIN_MAP = {str(uuid4()): admin_user.pk, str(uuid4()): user.pk}
    point = KnowledgePoint.objects.create(name='合成考点', code='BULK-RECOVER', subject='合成学科')
    body = {'subject': point.subject, 'total_target': 1, 'difficulty_dist': {'normal': 1},
            'type_dist': {'objective': 1}, 'kp_code': point.code}
    with patch.object(run_bulk_pipeline_task, 'delay') as queued:
        launched = admin_client.post('/api/quizzes/admin/bulk-pipeline/', body, format='json')
        assert launched.status_code == 201, launched.data
        task = ContentPipelineTask.objects.get(pk=launched.data['task_id'])
        url = f'/api/quizzes/admin/pipeline-tasks/{task.pk}/retry/'
        assert admin_client.post(url).status_code == 200 and queued.call_count == 1
        ContentPipelineTask.objects.filter(pk=task.pk).update(updated_at=timezone.now() - timedelta(hours=1))
        queued.side_effect = OSError('合成队列故障')
        assert admin_client.post(url).status_code == 202
        task.refresh_from_db()
        assert task.error_message == QUESTION_PIPELINE_QUEUE_ERROR
        queued.side_effect = None
        resumed = admin_client.post(url)
        assert resumed.status_code == 202 and resumed.data['id'] == task.pk
        assert admin_client.post(url).status_code == 200
        envelope = queued.call_args.kwargs
        assert queued.call_count == 3 and all(call.kwargs == envelope for call in queued.call_args_list)
    other_scope = Institution.objects.create(name='旧消息中的机构', slug='old-bulk-scope')
    other = KnowledgePoint.objects.create(name='旧消息中的考点', code='BULK-OUTDATED',
        subject='旧消息中的学科', institution=other_scope)
    delayed = {**envelope, 'subject': other.subject, 'kp_code': other.code, 'institution_id': other_scope.pk,
               'institution_only': True, 'total_target': 2}
    with patch.object(adversarial_pipeline, '_execute_pipeline') as wrong_pipeline:
        run_adversarial_pipeline_task(task.pk, [other.pk], 2)
        wrong_pipeline.assert_not_called()
    with patch.object(bulk_pipeline, '_author_generate', return_value=[{'question': '合成恢复题', 'kp_id': point.pk}]) as author, \
            patch.object(bulk_pipeline, '_classifier_tag', return_value={}):
        run_bulk_pipeline_task(**delayed)
        run_bulk_pipeline_task(**envelope)
        author.assert_called_once_with([point], q_per_kp=1, difficulty='normal', types=['objective'])
    task.refresh_from_db()
    assert ContentPipelineTask.objects.count() == 1 and task.status == 'completed' and not task.error_message
    assert Question.objects.get().knowledge_point_id == point.pk and task.result['questions_saved'] == 1

    previous = {'status': 'running', 'progress': 30,
        'payload': {**body, 'bulk_mode': True, 'current_stage': 'generating'}}
    partial = ContentPipelineTask.objects.create(created_by=user, title='旧批量出题', task_type='ai_generate', **previous)
    with patch.object(bulk_pipeline, '_author_generate', side_effect=AssertionError('Unexpected redelivery')) as author:
        run_bulk_pipeline_task(**{**envelope, 'task_id': partial.pk})
        author.assert_not_called()
    partial.refresh_from_db()
    assert {field: getattr(partial, field) for field in previous} == previous
    assert not partial.result and Question.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_legacy_arc_approval_commits_selected_questions_with_task_state(admin_client, admin_user, user, settings):
    from django.db import connection, connections
    from quizzes.models import ContentPipelineTask, KnowledgePoint, Question

    settings.UNIMIND_LEARNING_RUNTIME = 'ulr'
    settings.UNIMIND_DSH_ENABLED = False
    settings.UNIMIND_DIRECTUS_ADMIN_MAP = {str(uuid4()): admin_user.pk, str(uuid4()): user.pk}
    point = KnowledgePoint.objects.create(name='合成待审考点')
    draft = ContentPipelineTask.objects.create(created_by=admin_user, title='合成旧 ARC 待审', status='review',
        result={'questions': [{'kp_id': point.pk, 'question': '解释折现率。', 'q_type': 'subjective'}]})
    url = f'/api/quizzes/admin/pipeline-review/{draft.pk}/'
    data = {'action': 'approve', 'question_indices': [0, 0]}
    with patch.object(ContentPipelineTask, 'save', side_effect=RuntimeError('合成审核写回失败')):
        with pytest.raises(RuntimeError, match='合成审核写回失败'):
            admin_client.post(url, data, format='json')
    draft.refresh_from_db()
    assert draft.status == 'review' and not Question.objects.exists()

    if connection.vendor == 'postgresql':
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from rest_framework.test import APIClient

        ready = Barrier(2)

        def approve():
            client = APIClient()
            client.force_authenticate(user=admin_user)
            try:
                ready.wait(timeout=5)
                return client.post(url, data, format='json')
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            requests = [executor.submit(approve) for _ in range(2)]
            response, repeated = sorted((task.result(timeout=15) for task in requests), key=lambda item: item.status_code)
    else:
        response = admin_client.post(url, data, format='json')
        repeated = admin_client.post(url, data, format='json')
    assert response.status_code == 200 and response.data['questions_created'] == 1
    assert repeated.status_code == 404
    draft.refresh_from_db()
    assert draft.status == 'completed' and Question.objects.get().knowledge_point_id == point.pk


@pytest.mark.django_db(transaction=True)
def test_dsh_migration_gate_checks_receipts_created_during_rollback(auth_client, user, tmp_path, settings):
    from ai_assistant.views import _reserve_chat_request
    from users.learning import confirm_ai_call

    settings.UNIMIND_LEARNING_RUNTIME = 'ulr'
    settings.UNIMIND_DSH_ENABLED = False
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    WeeklyAIQuotaConfig.objects.update_or_create(pk=1, defaults={'course_calls': 20})
    bot = Bot.objects.create(is_xiaoyu=True, name='小宇')
    conversation = Conversation.objects.create(user=user, bot=bot, conversation_id=uuid4())
    scope = {'user': user, 'bot': bot, 'conversation_id': conversation.conversation_id}
    body = {'bot_id': bot.pk, 'conversation_id': str(conversation.conversation_id),
            'request_id': str(uuid4()), 'message': '合成回退问题'}
    prompt = AIChatMessage.objects.create(**scope, role='user', content=body['message'],
                                          metadata={'runtime_request_id': body['request_id']})
    cards = [{'type': 'data_card', 'payload': {'title': '合成回退出处'}}]
    metadata = {'engine': 'dsh', 'dsh_handoff': True, 'dsh_cards': cards,
                'learning_turn': {'message_id': prompt.pk, 'completed': True}}
    answer = AIChatMessage.objects.create(**scope, role='assistant', content='合成回退答复', metadata=metadata)
    payload = {'done': True, 'engine': 'dsh', 'message_id': answer.pk, 'full_content': answer.content,
               'request_id': body['request_id'], 'user_message': {'type': 'user_message', 'message_id': prompt.pk,
                   'metadata': prompt.metadata}, 'metadata': metadata}

    def audit(blockers):
        with StringIO() as output:
            options = {'state_dir': str(tmp_path), 'api_url': 'http://localhost:8000',
                       'require_migrated': True, 'stdout': output}
            if blockers:
                with pytest.raises(CommandError, match='未完成的迁移项'):
                    call_command('audit_dsh_sessions', **options)
            else:
                call_command('audit_dsh_sessions', **options)
            return json.loads(output.getvalue())

    assert audit(True)['blockers'] == {'missing_site_receipt': 1}
    receipt = confirm_ai_call(_reserve_chat_request(user, body, bot, conversation_id=conversation.conversation_id),
                              response=payload)
    assert audit(False)['handoff_receipts_verified'] == 1
    url = f'/api/ai/chat-requests/{receipt.request_id}/'

    async def consume(response):
        return [json.loads(frame[6:]) async for frame in response.streaming_content if frame.startswith(b'data: ')]

    charges = WeeklyAIUsage.objects.get(user=user).ai_calls
    with patch('ai_assistant.services.ulr_runtime.run_turn') as new_turn:
        assert auth_client.get(url).data['response'] == payload
        assert auth_client.post('/api/ai/chat/', body, format='json').data == {'status': 'completed', **payload}
        assert async_to_sync(consume)(auth_client.post('/api/ai/chat/stream/', body, format='json')) == [payload]
        new_turn.assert_not_called()
    assert WeeklyAIUsage.objects.get(user=user).ai_calls == charges
    AIUsageReservation.objects.filter(pk=receipt.pk).update(response={**payload, 'metadata': {**metadata, 'dsh_cards': []}})
    assert audit(True)['blockers'] == {'invalid_site_receipt': 1}
    AIUsageReservation.objects.filter(pk=receipt.pk).update(response=payload)
    assert auth_client.post('/api/ai/delete-conversation/', {'conversation_id': body['conversation_id']}, format='json').status_code == 200
    assert auth_client.get(url).data['status'] == 'unknown'
    assert audit(False)['blockers'] == {}


@pytest.mark.django_db
def test_dsh_inventory_separates_recoverable_unverified_and_deleted_histories(user, tmp_path, settings):
    api_url = 'http://127.0.0.1:8000'
    digest = hashlib.sha256(json.dumps([api_url, user.pk]).encode()).hexdigest()
    owner = tmp_path / digest
    owner.mkdir()
    (tmp_path / ('0' * 64)).mkdir()
    messages = [{'role': 'user', 'content': 'PRIVATE_SYNTHETIC_QUESTION'}, {'role': 'assistant', 'content': 'Synthetic reply'}]

    def write(session_id, rows):
        directory = owner / session_id
        directory.mkdir()
        (directory / 'transcript.json').write_text(json.dumps({'id': session_id, 'messages': rows}))

    def reserve(session_id, **data):
        AIUsageReservation.objects.create(user=user, request_id=uuid4(), attempt_id=uuid4(), week=timezone.now().date(),
            fingerprint='a' * 64, status='succeeded', response={'engine': 'dsh', 'session_id': session_id, **data})

    bot = Bot.objects.create(is_xiaoyu=True, name='小宇', bot_type='planner')
    for file_matches in (True, False, None):
        session_id, conversation_id = uuid4().hex, uuid4()
        Conversation.objects.create(user=user, bot=bot, conversation_id=conversation_id)
        prompt = AIChatMessage.objects.create(user=user, bot=bot, role='user', conversation_id=conversation_id, content=messages[0]['content'])
        answer = AIChatMessage.objects.create(user=user, bot=bot, role='assistant', conversation_id=conversation_id, content=messages[1]['content'],
            metadata={'engine': 'dsh', 'dsh_session_id': session_id, 'learning_turn': {'message_id': prompt.pk}})
        reserve(session_id, done=True, message_id=answer.pk, user_message={'message_id': prompt.pk},
                full_content=answer.content, metadata=answer.metadata)
        if file_matches is not None:
            write(session_id, messages if file_matches else [messages[0], {**messages[1], 'content': 'Different reply'}])
        if file_matches:
            legacy_conversation_id = conversation_id

    import_ids = []
    for has_file in (True, False):
        session_id = uuid4().hex
        import_ids.append(UUID(hex=session_id))
        extended = messages * 2
        for history in (extended, messages):
            reserve(session_id, finish_reason='completed', session={'id': session_id, 'messages': history}, content=messages[-1]['content'])
        if has_file:
            write(session_id, extended)

    write(uuid4().hex, messages)
    write(uuid4().hex, [])
    deleted = uuid4().hex
    write(deleted, messages)
    reserve(deleted, deleted=True)
    invalid = owner / uuid4().hex
    invalid.mkdir()
    (invalid / 'transcript.json').write_text('malformed')
    files = {p: p.read_bytes() for p in owner.glob('*/transcript.json')}
    before = list(AIUsageReservation.objects.filter(user=user).values_list('response', flat=True))
    output = StringIO()
    call_command('audit_dsh_sessions', state_dir=str(tmp_path), api_url=api_url, stdout=output)
    assert json.loads(output.getvalue()) == {'site_matched': 1, 'site_history_only': 1, 'conflict': 1, 'native_matched': 1,
        'native_ledger_only': 1, 'native_file_only': 1, 'empty_native_session': 1, 'deleted_with_file': 1,
        'unreadable_file': 1, 'unmatched_owners': 1}
    assert 'PRIVATE_SYNTHETIC_QUESTION' not in output.getvalue()
    assert all(path.read_bytes() == data for path, data in files.items())
    assert list(AIUsageReservation.objects.filter(user=user).values_list('response', flat=True)) == before

    args = {'state_dir': str(tmp_path), 'api_url': api_url, 'import_verified': True}
    settings.UNIMIND_DSH_ENABLED = True
    with pytest.raises(CommandError):
        call_command('audit_dsh_sessions', **args)
    settings.UNIMIND_DSH_ENABLED = False
    for pass_name in ('imported', 'already_imported'):
        output = StringIO()
        call_command('audit_dsh_sessions', stdout=output, **args)
        assert json.loads(output.getvalue())[pass_name] == 2
        assert Conversation.objects.count() == 5
    for conversation_id in import_ids:
        assert list(AIChatMessage.objects.filter(user=user, conversation_id=conversation_id)
                    .values('role', 'content')) == messages * 2
    assert all(path.read_bytes() == data for path, data in files.items())

    project = ConversationProject.objects.create(user=user, name='迁移验证项目')
    deleted_conversations = Conversation.objects.filter(conversation_id__in=[import_ids[0], legacy_conversation_id])
    deleted_conversations.update(project=project)
    continuation = AIChatMessage.objects.create(user=user, bot=bot, conversation_id=import_ids[0], role='assistant',
        content='继续讨论。', metadata={'engine': 'ulr'})
    request = AIUsageReservation.objects.create(user=user, request_id=uuid4(), attempt_id=uuid4(), week=timezone.now().date(),
        status='succeeded', response={'engine': 'ulr', 'message_id': continuation.pk})
    project.delete()
    request.refresh_from_db()
    assert request.response == {'engine': 'ulr', 'deleted': True}
    output = StringIO()
    call_command('audit_dsh_sessions', stdout=output, **args)
    after_delete = json.loads(output.getvalue())
    assert after_delete['deleted_with_file'] == 3 and after_delete['already_imported'] == 1
    assert 'imported' not in after_delete
    assert not deleted_conversations.exists()


@pytest.mark.django_db
def test_dsh_migration_gate_checks_import_content_and_ledger(user, tmp_path, settings):
    settings.UNIMIND_DSH_ENABLED = False
    api_url = 'http://127.0.0.1:8000'
    bot = Bot.objects.create(is_xiaoyu=True, name='小宇', bot_type='planner')
    conversation_id = uuid4()
    session_id = conversation_id.hex
    cards = [{'type': 'data_card', 'payload': {'title': 'SYNTHETIC_SOURCE'}}]
    rows = [{'role': 'user', 'content': 'SYNTHETIC_PROMPT'},
            {'role': 'assistant', 'content': 'SYNTHETIC_ANSWER', 'cards': cards}]
    reservation = AIUsageReservation.objects.create(user=user, request_id=uuid4(), attempt_id=uuid4(),
        week=timezone.now().date(), status='succeeded', response={
            'engine': 'dsh', 'session_id': session_id, 'finish_reason': 'completed',
            'session': {'id': session_id, 'messages': rows}, 'content': rows[1]['content'],
        })
    options = {'state_dir': str(tmp_path), 'api_url': api_url}

    def audit(blockers):
        output = StringIO()
        if blockers:
            with pytest.raises(CommandError, match='未完成的迁移项'):
                call_command('audit_dsh_sessions', **options, require_migrated=True, stdout=output)
        else:
            call_command('audit_dsh_sessions', **options, require_migrated=True, stdout=output)
        report = json.loads(output.getvalue())
        assert report['migrated'] is (not blockers) and report['blockers'] == blockers
        assert 'SYNTHETIC_' not in output.getvalue()

    audit({'pending_import': 1})
    assert not Conversation.objects.exists()
    call_command('audit_dsh_sessions', **options, import_verified=True, stdout=StringIO())
    messages = AIChatMessage.objects.filter(user=user, bot=bot, conversation_id=conversation_id)
    AIChatMessage.objects.create(user=user, bot=bot, conversation_id=conversation_id, role='assistant',
                                 content='原会话已经续聊。', metadata={'engine': 'ulr'})
    audit({})
    answer_id, metadata = messages.filter(metadata__engine='dsh_import').values_list('pk', 'metadata').get()
    stray = AIChatMessage.objects.create(user=user, bot=bot, conversation_id=uuid4(), role='assistant',
                                         content='复制到其他会话的答复', metadata=metadata)
    audit({'invalid_imported_link': 1})
    assert AIChatMessage.objects.filter(pk=stray.pk).exists()
    stray.delete()
    messages.filter(pk=answer_id).update(metadata={**metadata, 'dsh_cards': []})
    audit({'import_conflict': 1})
    retry = StringIO()
    call_command('audit_dsh_sessions', **options, import_verified=True, stdout=retry)
    assert json.loads(retry.getvalue())['import_conflict'] == 1
    assert messages.count() == 3 and messages.get(pk=answer_id).metadata['dsh_cards'] == []
    messages.filter(pk=answer_id).update(metadata=metadata)
    receipt = reservation.response
    reservation.response = {'engine': 'dsh', 'session_id': session_id, 'deleted': True}
    reservation.save(update_fields=['response'])
    audit({'deleted_with_imported_history': 1})
    reservation.response = receipt
    reservation.save(update_fields=['response'])
    reservation.delete()
    audit({'import_without_source': 1})


@pytest.mark.django_db
def test_dsh_migration_gate_verifies_the_exact_source_snapshot(user, tmp_path, settings, monkeypatch):
    import gzip
    from shutil import copytree
    from django.db import connection
    from django.test import override_settings

    settings.UNIMIND_DSH_ENABLED = False
    settings.UNIMIND_LEARNING_RUNTIME = 'ulr'
    Bot.objects.create(is_xiaoyu=True, name='小宇')
    api_url, session_id = 'http://127.0.0.1:8000', uuid4().hex
    owner = hashlib.sha256(json.dumps([api_url, user.pk]).encode()).hexdigest()
    source = tmp_path / 'source'
    directory = source / owner / session_id
    directory.mkdir(parents=True)
    messages = [{'role': 'user', 'content': 'SYNTHETIC_QUESTION'}, {'role': 'assistant', 'content': 'SYNTHETIC_REPLY'}]
    transcript = {'id': session_id, 'messages': messages}
    (directory / 'transcript.json').write_text(json.dumps(transcript))
    source_receipt = AIUsageReservation.objects.create(user=user, request_id=uuid4(), attempt_id=uuid4(), week=timezone.now().date(),
        status='succeeded', response={'engine': 'dsh', 'session_id': session_id, 'finish_reason': 'completed',
                                      'session': transcript, 'content': messages[-1]['content']})
    deleted_id = uuid4().hex
    (source / owner / deleted_id).mkdir()
    AIUsageReservation.objects.create(user=user, request_id=uuid4(), attempt_id=uuid4(), week=timezone.now().date(),
        status='succeeded', response={'engine': 'dsh', 'session_id': deleted_id, 'deleted': True})

    def audit(root, *, blocked=False, **flags):
        output = StringIO()
        options = {'state_dir': str(root), 'api_url': api_url, 'stdout': output, **flags}
        if blocked:
            with pytest.raises(CommandError, match='未完成的迁移项'):
                call_command('audit_dsh_sessions', **options)
        else:
            call_command('audit_dsh_sessions', **options)
        assert 'SYNTHETIC_' not in output.getvalue() and session_id not in output.getvalue()
        return json.loads(output.getvalue())

    backup = tmp_path / 'paired.sql.gz'
    backup.write_bytes(gzip.compress(b'SELECT 1;', mtime=0))
    inventory = audit(source, state_fingerprint=True, database_backup=str(backup))
    assert (inventory['state_owners'], inventory['state_transcripts']) == (1, 1)
    assert inventory['database_fingerprint'] == hashlib.sha256(backup.read_bytes()).hexdigest()
    assert not Conversation.objects.exists()
    restored = copytree(source, tmp_path / 'restored')
    audit(restored, import_verified=True)
    with pytest.raises(CommandError, match='配对恢复验收需要'):
        audit(restored, require_paired_restore=True, expected_state_fingerprint=inventory['state_fingerprint'])
    gate = {'require_migrated': True, 'expected_state_fingerprint': inventory['state_fingerprint'],
            'database_backup': str(backup), 'expected_database_fingerprint': inventory['database_fingerprint']}
    report = audit(restored, blocked=True, **gate)
    assert report['snapshot_pair_verified'] and not report['database_restore_verified']
    assert report['blockers'] == {'database_restore_fingerprint_mismatch': 1}
    if connection.vendor == 'postgresql':
        from django.db.backends.postgresql.psycopg_any import sql

        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('unimind.restore_sha256', %s, true)", [inventory['database_fingerprint']])
            cursor.execute('SELECT current_database()')
            database, = cursor.fetchone()
            assert not audit(restored, blocked=True, **gate)['database_restore_verified']
            cursor.execute(sql.SQL('ALTER DATABASE {} SET unimind.restore_sha256 TO {}').format(
                sql.Identifier(database), sql.Literal(inventory['database_fingerprint'])))
    else:
        monkeypatch.setattr('ai_assistant.management.commands.audit_dsh_sessions.restored_database_fingerprint',
                            lambda: inventory['database_fingerprint'])
    report = audit(restored, **gate)
    assert report['migrated'] and report['snapshot_pair_verified'] and report['database_restore_verified']
    assert report['target_runtime'] == 'ulr'
    with override_settings(UNIMIND_LEARNING_RUNTIME='legacy', DEBUG=True, UNIMIND_ULR_PROTOTYPE=True,
                           UNIMIND_DSH_GENERATION_ENABLED=True):
        report = audit(restored, blocked=True, **gate)
        assert report['blockers'] == {'target_runtime_not_ulr': 1}
        assert report['target_runtime'] == 'legacy'
        assert report['snapshot_pair_verified'] and report['database_restore_verified']
    AIUsageReservation.objects.filter(pk=source_receipt.pk).update(response={**source_receipt.response, 'request_id': str(uuid4())})
    assert audit(restored, blocked=True, **gate)['blockers'] == {'conflict': 1}
    AIUsageReservation.objects.filter(pk=source_receipt.pk).update(response=source_receipt.response)
    swapped = tmp_path / 'other.sql.gz'
    swapped.write_bytes(gzip.compress(b'SELECT 2;', mtime=0))
    report = audit(restored, blocked=True, **{**gate, 'database_backup': str(swapped)})
    assert report['blockers'] == {'database_fingerprint_mismatch': 1}
    assert report['state_fingerprint_verified'] and not report['snapshot_pair_verified']
    empty = tmp_path / 'empty'
    empty.mkdir()
    inventory_only = audit(empty, require_migrated=True)
    assert inventory_only['migrated'] and 'paired_migration_verified' not in inventory_only
    report = audit(empty, blocked=True, **gate)
    assert report['blockers'] == {'state_fingerprint_mismatch': 1} and not report['state_fingerprint_verified']
    changed = restored / owner / session_id / 'transcript.json'
    changed.write_text(json.dumps(transcript, indent=2))
    assert audit(restored, blocked=True, **gate)['blockers'] == {'state_fingerprint_mismatch': 1}
    assert Conversation.objects.count() == 1 and AIChatMessage.objects.count() == 2


@pytest.mark.django_db
def test_import_does_not_choose_between_two_owners_for_one_ledger_session(user, tmp_path, settings):
    settings.UNIMIND_DSH_ENABLED = False
    Bot.objects.create(is_xiaoyu=True, name='小宇')
    other = get_user_model().objects.create_user(username='second-synthetic-owner')
    session_id = uuid4().hex
    response = {'engine': 'dsh', 'session_id': session_id, 'finish_reason': 'completed', 'content': 'SYNTHETIC_REPLY',
                'session': {'id': session_id, 'messages': [{'role': 'user', 'content': 'SYNTHETIC_QUESTION'},
                                                           {'role': 'assistant', 'content': 'SYNTHETIC_REPLY'}]}}
    for owner in (user, other):
        AIUsageReservation.objects.create(user=owner, request_id=uuid4(), attempt_id=uuid4(),
            week=timezone.now().date(), status='succeeded', response=response)
    options = {'state_dir': str(tmp_path), 'api_url': 'http://127.0.0.1:8000'}
    for user_id in (None, user.pk):
        output = StringIO()
        call_command('audit_dsh_sessions', **options, user_id=user_id, import_verified=True, stdout=output)
        assert json.loads(output.getvalue()) == (
            {'cross_owner_session': 1, 'unmatched_owners': 0} if user_id is None else {'cross_owner_session': 1})
        assert not Conversation.objects.exists() and not AIChatMessage.objects.exists()
    output = StringIO()
    with pytest.raises(CommandError, match='未完成的迁移项'):
        call_command('audit_dsh_sessions', **options, require_migrated=True, stdout=output)
    assert json.loads(output.getvalue())['blockers'] == {'cross_owner_session': 1}
    assert 'SYNTHETIC_' not in output.getvalue() and session_id not in output.getvalue()
    AIUsageReservation.objects.filter(user=other).delete()
    call_command('audit_dsh_sessions', **options, import_verified=True, stdout=StringIO())
    assert Conversation.objects.get(conversation_id=UUID(hex=session_id)).user_id == user.pk
    call_command('audit_dsh_sessions', **options, require_migrated=True, stdout=StringIO())


@pytest.mark.django_db
def test_dsh_migration_gate_checks_pending_exam_inputs_before_cutover(
        auth_client, user, tmp_path, settings, django_capture_on_commit_callbacks):
    from django.test import override_settings

    from ai_assistant.models import ProjectLearning, ProjectLearningTask
    from ai_assistant.services.learning_tasks import create_task
    from quizzes.models import Question, QuizExam

    settings.UNIMIND_DSH_ENABLED = False
    settings.UNIMIND_LEARNING_RUNTIME = 'ulr'
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    Bot.objects.create(is_xiaoyu=True, name='小宇')
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    question = Question.objects.create(text='CUTOVER_BANK_PROMPT', options=['甲', '乙'], correct_answer='A')
    project = ConversationProject.objects.create(user=user, name='合成迁移项目')
    ProjectLearning.objects.create(project=project, status='active', plan={'stages': [{'id': 'start'}]})
    task = create_task(project, {'title': '原开放任务', 'stage_id': 'start', 'instructions': '独立作答', 'definition': {
        'response_type': 'reasoning', 'prompt': 'CUTOVER_TASK_PROMPT', 'criteria': ['说明原理'],
    }})
    with override_settings(DEBUG=False, UNIMIND_LEARNING_RUNTIME='legacy'), \
            patch('quizzes.views_exam.dispatch_exam_grading'), django_capture_on_commit_callbacks(execute=True):
        bank = auth_client.post('/api/quizzes/submit-exam/', {'answers': [
            {'question_id': question.pk, 'answer': 'A'},
        ]}, format='json')
        personal = auth_client.post('/api/quizzes/submit-exam/', {'learning_task_id': str(task.pk),
            'submission_id': str(task.pk), 'answers': [{'question_id': 0, 'answer': 'CUTOVER_SAVED_ANSWER'}]}, format='json')
    assert bank.status_code == personal.status_code == 202, (bank.data, personal.data)
    exam_ids = [bank.data['exam_id'], personal.data['exam_id']]
    QuizExam.objects.filter(pk=exam_ids[1]).update(status='grading', started_at=None)
    options = {'state_dir': str(tmp_path), 'api_url': 'http://127.0.0.1:8000', 'require_migrated': True}
    call_command('audit_dsh_sessions', stdout=StringIO(), **options)

    Question.objects.filter(pk=question.pk).update(correct_answer='B')
    ProjectLearningTask.objects.filter(pk=task.pk).update(definition={**task.definition, 'criteria': ['改版标准']})
    report = StringIO()
    with patch('quizzes.ai_workflow._grade_answer') as model, pytest.raises(CommandError, match='未完成的迁移项'):
        call_command('audit_dsh_sessions', stdout=report, **options)
    model.assert_not_called()
    audit = json.loads(report.getvalue())
    assert audit['blockers'] == {'queued_exam_grading_not_ready': 2}
    assert audit['blocked_queued_exam_ids'] == exam_ids
    assert 'CUTOVER_' not in report.getvalue()
    assert list(QuizExam.objects.filter(pk__in=exam_ids).order_by('pk').values_list('status', 'requires_ulr')) == [
        ('pending', False), ('grading', False),
    ]
    Question.objects.filter(pk=question.pk).update(correct_answer=question.correct_answer)
    ProjectLearningTask.objects.filter(pk=task.pk).update(definition=task.definition)
    call_command('audit_dsh_sessions', stdout=StringIO(), **options)

    QuizExam.objects.get(pk=exam_ids[0]).results.all().delete()
    report = StringIO()
    with pytest.raises(CommandError, match='未完成的迁移项'):
        call_command('audit_dsh_sessions', stdout=report, **options)
    audit = json.loads(report.getvalue())
    assert audit['blockers'] == {'queued_exam_grading_not_ready': 1}
    assert audit['blocked_queued_exam_ids'] == exam_ids[:1]
    assert QuizExam.objects.get(pk=exam_ids[0]).status == 'pending'
    assert 'CUTOVER_' not in report.getvalue()


@pytest.mark.django_db
def test_dsh_migration_gate_requires_a_recoverable_receipt_for_each_product_turn(
        auth_client, user, tmp_path, settings, django_capture_on_commit_callbacks):
    settings.UNIMIND_DSH_ENABLED = False
    bot = Bot.objects.create(is_xiaoyu=True, name='小宇', bot_type='planner')
    conversation_id, request_id = uuid4(), uuid4()
    session_id = uuid4().hex
    Conversation.objects.create(user=user, bot=bot, conversation_id=conversation_id)
    source = {'user': user, 'bot': bot, 'conversation_id': conversation_id}
    course_context = {'course_id': 17, 'video_seconds': 60}
    prompt_metadata = {'runtime_request_id': str(request_id), 'course_context': course_context}
    prompt = AIChatMessage.objects.create(**source, role='user', content='合成迁移问题',
        metadata=prompt_metadata)
    cards = [{'type': 'data_card', 'payload': {'title': 'SYNTHETIC_RECOVERY_CARD'}}]
    metadata = {'engine': 'dsh', 'dsh_session_id': session_id, 'dsh_cards': cards, 'course_context': course_context,
        'learning_turn': {'message_id': prompt.pk}}
    answer = AIChatMessage.objects.create(**source, role='assistant', content='合成迁移答复', metadata=metadata)
    payload = {'engine': 'dsh', 'done': True, 'session_id': session_id, 'full_content': answer.content,
        'message_id': answer.pk, 'user_message': {'message_id': prompt.pk}, 'metadata': metadata}
    options = {'state_dir': str(tmp_path), 'api_url': 'http://127.0.0.1:8000', 'require_migrated': True}

    def audit(expected):
        output = StringIO()
        if expected:
            with pytest.raises(CommandError, match='未完成的迁移项'):
                call_command('audit_dsh_sessions', stdout=output, **options)
        else:
            call_command('audit_dsh_sessions', stdout=output, **options)
        report = json.loads(output.getvalue())
        assert report['blockers'] == expected
        assert 'SYNTHETIC_RECOVERY_CARD' not in output.getvalue()
        return report

    audit({'missing_site_receipt': 1})
    receipt = AIUsageReservation.objects.create(user=user, request_id=request_id, conversation_id=conversation_id,
        attempt_id=uuid4(), week=timezone.now().date(), fingerprint='a' * 64, status='succeeded', response=payload)
    audit({})
    AIUsageReservation.objects.filter(pk=receipt.pk).update(response={**payload, 'metadata': {**metadata, 'dsh_cards': []}})
    audit({'invalid_site_receipt': 1})
    for corrupted in (
        {**payload, 'request_id': str(uuid4())},
        {**payload, 'metadata': {**metadata, 'course_context': {'course_id': 18, 'video_seconds': 60}}},
        {**payload, 'user_message': {**payload['user_message'], 'type': 'text_delta'}},
        {**payload, 'user_message': {**payload['user_message'], 'metadata': {**prompt_metadata, 'runtime_request_id': str(uuid4())}}},
        {**payload, 'user_message': {**payload['user_message'], 'metadata': {**prompt_metadata, 'course_context': {'course_id': 18}}}},
    ):
        AIUsageReservation.objects.filter(pk=receipt.pk).update(response=corrupted)
        audit({'invalid_site_receipt': 1})
    video = {'video_key': 'bilibili:BV1ULRSmoke:p1', 'video_seconds': 60}
    video_prompt = {**prompt_metadata, 'external_video_context': video}
    video_answer = {**metadata, 'external_video_context': video}
    AIChatMessage.objects.filter(pk=prompt.pk).update(metadata=video_prompt)
    AIChatMessage.objects.filter(pk=answer.pk).update(metadata=video_answer)
    video_payload = {**payload, 'metadata': video_answer,
        'user_message': {**payload['user_message'], 'metadata': video_prompt}}
    AIUsageReservation.objects.filter(pk=receipt.pk).update(response=video_payload)
    audit({})
    wrong_part = {**video, 'video_key': 'bilibili:BV1ULRSmoke:p2'}
    for altered in (
        {**video_payload, 'metadata': {**video_answer, 'external_video_context': wrong_part}},
        {**video_payload, 'user_message': payload['user_message']},
        {**video_payload, 'user_message': {**video_payload['user_message'],
            'metadata': {**video_prompt, 'external_video_context': wrong_part}}},
    ):
        AIUsageReservation.objects.filter(pk=receipt.pk).update(response=altered)
        audit({'invalid_site_receipt': 1})
    AIChatMessage.objects.filter(pk=prompt.pk).update(metadata=prompt_metadata)
    AIChatMessage.objects.filter(pk=answer.pk).update(metadata=metadata)
    AIUsageReservation.objects.filter(pk=receipt.pk).update(response=payload, request_id=uuid4())
    audit({'invalid_site_receipt': 1})
    AIUsageReservation.objects.filter(pk=receipt.pk).update(request_id=request_id, fingerprint='')
    audit({'invalid_site_receipt': 1})
    AIUsageReservation.objects.filter(pk=receipt.pk).update(fingerprint='a' * 64)
    duplicate = AIUsageReservation.objects.create(user=user, request_id=uuid4(), attempt_id=uuid4(),
        week=timezone.now().date(), fingerprint='a' * 64, status='succeeded', response=payload)
    audit({'invalid_site_receipt': 1, 'duplicate_site_receipt': 1})
    duplicate.delete()
    audit({})
    from users.learning import AI_RESERVATION_TTL, CHAT_RESERVATION_TTL
    for conversation, ttl in ((conversation_id, CHAT_RESERVATION_TTL), (None, AI_RESERVATION_TTL)):
        pending = AIUsageReservation.objects.create(user=user, request_id=uuid4(), attempt_id=uuid4(),
            conversation_id=conversation, week=timezone.now().date(), status='pending')
        audit({'active_chat_requests': 1})
        AIUsageReservation.objects.filter(pk=pending.pk).update(updated_at=timezone.now() - ttl - timedelta(seconds=1))
        audit({})
        pending.refresh_from_db()
        assert pending.status == 'pending'
    from backoffice.tasks import TEACHING_JOB_TIMEOUT, expire_stale_teaching_tasks
    from quizzes.models import ContentPipelineTask

    job = ContentPipelineTask.objects.create(created_by=user, title='合成教研任务', task_type='other',
        status='pending', payload={'kind': 'chat'})
    audit({})
    ContentPipelineTask.objects.filter(pk=job.pk).update(status='running', started_at=timezone.now())
    assert audit({'active_unpinned_teaching_tasks': 1})['active_teaching_task_ids'] == [job.pk]
    ContentPipelineTask.objects.filter(pk=job.pk).update(payload={'kind': 'chat', 'requires_ulr': True})
    audit({})
    ContentPipelineTask.objects.filter(pk=job.pk).update(payload={'kind': 'chat', 'requires_ulr': None})
    assert audit({'active_unpinned_teaching_tasks': 1})['active_teaching_task_ids'] == [job.pk]
    ContentPipelineTask.objects.filter(pk=job.pk).update(
        payload={'kind': 'chat'}, started_at=timezone.now() - TEACHING_JOB_TIMEOUT - timedelta(seconds=1))
    audit({})
    job.refresh_from_db()
    assert job.status == 'running'
    job_row = ContentPipelineTask.objects.filter(pk=job.pk)
    job_row.update(started_at=None, updated_at=timezone.now())
    assert audit({'active_unpinned_teaching_tasks': 1})['active_teaching_task_ids'] == [job.pk]
    assert expire_stale_teaching_tasks(job_row) == 0
    job_row.update(updated_at=timezone.now() - TEACHING_JOB_TIMEOUT - timedelta(seconds=1))
    audit({})
    job.refresh_from_db()
    assert job.status == 'running'
    assert expire_stale_teaching_tasks(job_row) == 1
    job.refresh_from_db()
    assert job.status == 'failed' and job.finished_at is not None

    arc = ContentPipelineTask.objects.create(created_by=user, title='合成旧 ARC 出题', task_type='ai_generate',
        status='running', started_at=timezone.now(), payload={'kp_ids': [1], 'questions_per_kp': 3})
    bulk = ContentPipelineTask.objects.create(created_by=user, title='合成旧批量出题', task_type='ai_generate',
        status='running', started_at=timezone.now() - timedelta(days=1),
        payload={'bulk_mode': True, 'total_target': 500, 'subject': '合成学科'})
    report = audit({'unsettled_legacy_question_pipelines': 2})
    assert report['unsettled_question_pipeline_ids'] == [arc.pk, bulk.pk]
    assert ContentPipelineTask.objects.filter(pk__in=[arc.pk, bulk.pk], status='running').count() == 2
    ContentPipelineTask.objects.filter(pk=arc.pk).update(status='completed')
    assert audit({'unsettled_legacy_question_pipelines': 1})['unsettled_question_pipeline_ids'] == [bulk.pk]
    ContentPipelineTask.objects.filter(pk=bulk.pk).update(payload={**bulk.payload, 'requires_ulr': True})
    audit({})
    ContentPipelineTask.objects.filter(pk=bulk.pk).update(status='failed')
    audit({})

    from notifications.models import Notification
    from quizzes.ai_workflow import run_exam_grading
    from quizzes.models import ExamQuestionResult, QuizExam

    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    settings.UNIMIND_LEARNING_RUNTIME = 'ulr'
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    queued = QuizExam.objects.create(user=user, status='pending', grading_queued_at=timezone.now(), total_questions=1)
    ExamQuestionResult.objects.create(exam=queued, status='graded', attempts=1, user_answer='A', score=4, max_score=5)
    QuizExam.objects.create(user=user, status='grading', started_at=timezone.now(), requires_ulr=True)
    audit({})
    exam = QuizExam.objects.create(user=user, status='grading', started_at=timezone.now(), total_questions=1)
    graded = ExamQuestionResult.objects.create(exam=exam, status='graded', attempts=1, user_answer='A', score=4, max_score=5)
    assert audit({'unsettled_unpinned_exam_grading': 1})['unsettled_exam_ids'] == [exam.pk]
    QuizExam.objects.filter(pk=exam.pk).update(started_at=timezone.now() - timedelta(days=1))
    audit({'unsettled_unpinned_exam_grading': 1})
    exam.refresh_from_db()
    assert exam.status == 'grading' and exam.started_at and not exam.requires_ulr
    with patch('quizzes.views_exam.dispatch_exam_grading') as dispatch, django_capture_on_commit_callbacks(execute=True):
        response = auth_client.post(f'/api/quizzes/exams/{exam.pk}/retry/', {}, format='json')
    assert response.status_code == 202, response.data
    dispatch.assert_called_once_with(user.pk, exam.pk)
    audit({})
    with patch('quizzes.ai_workflow._grade_answer') as model:
        run_exam_grading(user.pk, exam.pk)
        run_exam_grading(user.pk, exam.pk)
    model.assert_not_called()
    exam.refresh_from_db()
    graded.refresh_from_db()
    assert (exam.status, exam.requires_ulr, exam.total_score) == ('completed', True, 4)
    assert (graded.user_answer, graded.score, graded.attempts) == ('A', 4, 1)
    assert Notification.objects.filter(recipient=user, ntype='practice_result', link=f'/tests/results/{exam.pk}').count() == 1
    audit({})

    from knowledge_builder.models import KnowledgeTreeBuild

    KnowledgeTreeBuild.objects.create(subject='合成待处理旧构建', status='PENDING')
    KnowledgeTreeBuild.objects.create(subject='合成运行中构建', status='RUNNING', requires_ulr=True)
    audit({})
    build = KnowledgeTreeBuild.objects.create(subject='合成旧执行进程', status='RUNNING')
    KnowledgeTreeBuild.objects.filter(pk=build.pk).update(updated_at=timezone.now() - timedelta(days=1))
    assert audit({'running_unpinned_knowledge_builds': 1})['running_knowledge_build_ids'] == [str(build.pk)]
    build.refresh_from_db()
    assert build.status == 'RUNNING' and not build.requires_ulr
    KnowledgeTreeBuild.objects.filter(pk=build.pk).update(status='COMPLETED')
    audit({})
    project = ConversationProject.objects.create(user=user, name='合成知识块项目')
    ProjectLearningEvent.objects.create(project=project, kind='block_prepare', content={'status': 'pending'})
    ProjectLearningEvent.objects.create(project=project, kind='block_prepare', content={'status': 'running', 'requires_ulr': True})
    legacy = ProjectLearningEvent.objects.create(project=project, kind='block_prepare',
        content={'status': 'running', 'started_at': int((timezone.now() - timedelta(days=1)).timestamp())})
    report = audit({'running_unpinned_block_assessments': 1})
    assert report['unsettled_block_preparation_ids'] == [legacy.pk]
    legacy.refresh_from_db()
    assert legacy.content['status'] == 'running'
    ProjectLearningEvent.objects.filter(pk=legacy.pk).update(content={'status': 'completed'})
    audit({})
    owner = hashlib.sha256(json.dumps([options['api_url'], user.pk]).encode()).hexdigest()
    (tmp_path / owner).write_text('SYNTHETIC_RECOVERY_CARD')
    audit({'unreadable_owner': 1})
