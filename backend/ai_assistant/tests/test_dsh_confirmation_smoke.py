"""Student-confirmed business writes; no model/provider calls."""
import json
from datetime import date
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync
import pytest
from rest_framework.test import APIClient
from rest_framework.exceptions import PermissionDenied, ValidationError
from ai_assistant.services.dsh_service import build_context, execute_tool
from quizzes.models import Question, KnowledgePoint, UserKnowledgeState, UserQuestionStatus
from faq_system.models import Question as FAQQuestion
from users.models import CourseStudentStatus, Institution, WeeklyAIQuotaConfig


def enable(settings, user, tmp_path):
    settings.UNIMIND_DSH_ENABLED = settings.UNIMIND_DSH_SITE_ENABLED = True
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    settings.UNIMIND_DSH_STATE_DIR = str(tmp_path)
    CourseStudentStatus.objects.create(user=user, is_course_student=True)


@pytest.mark.django_db
def test_diagnostic_requires_student_and_grades_once(auth_client, user, settings, tmp_path):
    enable(settings, user, tmp_path)
    kp = KnowledgePoint.objects.create(name='合成诊断考点', level='kp')
    question = Question.objects.create(knowledge_point=kp, text='合成诊断题', q_type='objective', options=['选项甲', '选项乙'], correct_answer='B')
    private = Institution.objects.create(name='Private', slug='private-confirmation')
    Question.objects.create(institution=private, text='PRIVATE_QUESTION', q_type='objective', correct_answer='A')
    context = build_context(user, '做一次诊断测试')
    draft = execute_tool(user, 'run_diagnostic', {'mode': 'generate'}, context['memory']['version'])
    card = draft['visual']['payload']
    assert card['questions'][0]['id'] == question.pk
    assert 'PRIVATE_QUESTION' not in json.dumps(draft)
    assert 'correct_answer' not in json.dumps(draft)
    assert not UserKnowledgeState.objects.exists()
    body = {'token': card['token'], 'answers': [{'question': {'id': question.pk, 'answer': 'FAKE'}, 'answer': 'B'}]}
    url = '/api/ai/dsh/actions/confirm/'
    assert auth_client.post(url, body, format='json').status_code == 400
    body['confirmed'] = True
    response = auth_client.post(url, body, format='json')
    assert response.status_code == 200, response.data
    assert response.data['total_score'] == 1
    recorded = UserQuestionStatus.objects.get(user=user, question=question).last_review
    assert auth_client.post(url, body, format='json').data == response.data
    assert UserQuestionStatus.objects.get(user=user, question=question).last_review == recorded
    assert auth_client.get(f"/api/ai/dsh/actions/{card['request_id']}/").data == response.data
    changed = {**body, 'answers': [{'question': {'id': question.pk}, 'answer': 'A'}]}
    assert auth_client.post(url, changed, format='json').status_code == 409
    assert not FAQQuestion.objects.exists()
    with pytest.raises(ValidationError):
        execute_tool(user, 'run_diagnostic', {'mode': 'submit', 'answers': []}, build_context(user, '')['memory']['version'])


@pytest.mark.django_db
def test_retired_faq_cannot_create_or_confirm_a_draft(auth_client, user, settings, tmp_path):
    from django.core import signing
    from ai_assistant.services.dsh_actions import SALT

    enable(settings, user, tmp_path)
    context = build_context(user, '我想请老师人工答疑')
    with pytest.raises(PermissionDenied):
        execute_tool(user, 'create_faq_ticket', {'question_text': '合成提问'}, context['memory']['version'])
    token = signing.dumps({'kind': 'faq', 'user': user.pk}, salt=SALT)
    response = auth_client.post('/api/ai/dsh/actions/confirm/', {'token': token, 'confirmed': True}, format='json')
    assert response.status_code == 403
    assert not FAQQuestion.objects.exists()


@pytest.mark.django_db
def test_expired_or_deleted_source_cannot_write_and_task_token_cannot_confirm(auth_client, user, settings, tmp_path):
    from ai_assistant.dsh_authentication import make_task_token
    from ai_assistant.services.dsh_actions import prepare_diagnostic
    from ai_assistant.models import DshSubmission
    from users.models import AIUsageReservation
    from uuid import uuid4
    enable(settings, user, tmp_path)
    question = Question.objects.create(text='合成过期题', q_type='objective', correct_answer='A')
    card = prepare_diagnostic(user)['visual']['payload']
    body = {'token': card['token'], 'confirmed': True, 'answers': [{'question': {'id': question.pk}, 'answer': 'A'}]}
    url = '/api/ai/dsh/actions/confirm/'
    with patch('ai_assistant.services.dsh_actions.time.time', return_value=card['expires_at']+1):
        assert auth_client.post(url, body, format='json').status_code == 400
    assert not UserQuestionStatus.objects.exists() and not DshSubmission.objects.exists()
    reservation = AIUsageReservation.objects.create(user=user, request_id=uuid4(), attempt_id=uuid4(), week=date(2026,10,26))
    sourced = prepare_diagnostic(user, reservation.pk)['visual']['payload']
    body['token'] = sourced['token']
    callback = APIClient(); callback.credentials(HTTP_AUTHORIZATION='DSH ' + make_task_token(user, reservation))
    assert callback.post(url, body, format='json').status_code == 401
    assert auth_client.post(url, body, format='json').status_code == 409
    reservation.status = 'succeeded'; reservation.response = {'engine': 'dsh', 'deleted': True}; reservation.save()
    assert auth_client.post(url, body, format='json').status_code == 409
    assert auth_client.post(url, {**body, 'token': sourced['token']+'tampered'}, format='json').status_code == 400
    reservation.response = {'engine': 'dsh'}; reservation.save()
    assert auth_client.post(url, body, format='json').status_code == 200
    assert DshSubmission.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_legacy_diagnostic_confirmation_locks_source_until_commit(auth_client, user, settings, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import OperationalError, connection, connections, transaction

    from ai_assistant.models import AIChatMessage, Bot, Conversation, DshSubmission
    from ai_assistant.services.dsh_actions import grade_diagnostic_answers, prepare_diagnostic
    from users.models import AIUsageReservation

    if connection.vendor != 'postgresql':
        pytest.skip('Requires PostgreSQL reservation row locks.')
    enable(settings, user, tmp_path)
    bot = Bot.objects.create(is_xiaoyu=True, name='小宇', bot_type='planner')
    conversation = Conversation.objects.create(user=user, bot=bot, conversation_id=uuid4())
    question = Question.objects.create(text='迁移中的诊断题', q_type='objective', options=['甲', '乙'], correct_answer='B')
    answer = AIChatMessage.objects.create(user=user, bot=bot, conversation_id=conversation.conversation_id,
        role='assistant', content='请完成诊断。', metadata={'engine': 'dsh', 'dsh_session_id': uuid4().hex})
    source = AIUsageReservation.objects.create(user=user, request_id=uuid4(), attempt_id=uuid4(),
        week=date(2026, 10, 26), status='succeeded', response={'engine': 'dsh', 'session_id': answer.metadata['dsh_session_id']})
    card = prepare_diagnostic(user, source.pk)['visual']['payload']
    settings.UNIMIND_LEARNING_RUNTIME = 'ulr'
    settings.UNIMIND_DSH_ENABLED = settings.UNIMIND_DSH_SITE_ENABLED = False
    settings.UNIMIND_DSH_STATE_DIR = 'invalid-legacy-directory'
    ready, release = Event(), Event()
    body = {'token': card['token'], 'confirmed': True, 'answers': [{'question': {'id': question.pk}, 'answer': 'B'}]}

    def grade(*args, **kwargs):
        ready.set()
        assert release.wait(8)
        return grade_diagnostic_answers(*args, **kwargs)

    def confirm():
        client = APIClient()
        client.force_authenticate(user=user)
        try:
            return client.post('/api/ai/learning-actions/confirm/', body, format='json')
        finally:
            connections.close_all()

    with patch('ai_assistant.services.dsh_actions.grade_diagnostic_answers', side_effect=grade), ThreadPoolExecutor() as pool:
        future = pool.submit(confirm)
        try:
            assert ready.wait(5), future.result(timeout=1).status_code
            with pytest.raises(OperationalError), transaction.atomic():
                AIUsageReservation.objects.select_for_update(nowait=True).get(pk=source.pk)
        finally:
            release.set()
        result = future.result(timeout=5)
    assert result.status_code == 200 and result.data['total_score'] == 1
    assert auth_client.post('/api/ai/delete-conversation/', {'conversation_id': conversation.conversation_id},
                            format='json').status_code == 200
    source.refresh_from_db()
    assert source.response['deleted'] and DshSubmission.objects.count() == 1
    assert auth_client.get(f"/api/ai/dsh/actions/{card['request_id']}/").data == result.data


@pytest.mark.django_db(transaction=True)
def test_ulr_diagnostic_completes_and_recovers_without_dsh(auth_client, user, settings, tmp_path):
    from ai_assistant.models import Bot, DshSubmission

    enable(settings, user, tmp_path)
    WeeklyAIQuotaConfig.objects.update_or_create(pk=1, defaults={'course_calls': 200})
    settings.DEBUG = settings.UNIMIND_ULR_PROTOTYPE = False
    settings.UNIMIND_LEARNING_RUNTIME = 'ulr'
    settings.UNIMIND_DSH_ENABLED = settings.UNIMIND_DSH_SITE_ENABLED = settings.UNIMIND_DSH_XIAOYU_ENABLED = False
    bot, _ = Bot.objects.get_or_create(is_xiaoyu=True, defaults={'name': '小宇'})
    kp = KnowledgePoint.objects.create(name='合成诊断考点')
    question = Question.objects.create(knowledge_point=kp, text='合成诊断题', q_type='objective',
        options=['甲', '乙'], correct_answer='B')

    def model(messages, **kwargs):
        if messages[-1]['role'] == 'tool':
            result = json.loads(messages[-1]['content'])
            assert result['question_count'] == 1 and 'correct_answer' not in result
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': '请在卡片内完成作答。'}}]}
        assert 'run_diagnostic' in {tool['function']['name'] for tool in kwargs['tools']}
        return {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [{
            'id': 'diagnostic', 'type': 'function', 'function': {'name': 'run_diagnostic', 'arguments': '{"mode":"generate"}'},
        }]}}]}

    async def consume(response):
        return [json.loads(frame[6:]) async for frame in response.streaming_content if frame.startswith(b'data: ')][-1]

    def draft(conversation_id):
        response = auth_client.post('/api/ai/chat/stream/', {'bot_id': bot.pk, 'conversation_id': conversation_id,
            'request_id': str(uuid4()), 'message': '请准备首次诊断。'}, format='json')
        result = async_to_sync(consume)(response)
        assert result.get('engine') == 'ulr', result
        card, = result['metadata']['dsh_cards']
        assert card['type'] == 'diagnostic_quiz' and 'correct_answer' not in json.dumps(card)
        return card['payload']

    url = '/api/ai/learning-actions/confirm/'
    answers = [{'question': {'id': question.pk}, 'answer': 'B'}]
    with patch('ai_engine.service.AIEngine.call_provider', side_effect=model) as provider, \
         patch('ai_assistant.services.dsh_xiaoyu.schedule_conversation_title'), \
         patch('ai_assistant.services.dsh_xiaoyu.extract_memories_async'), \
         patch('ai_assistant.services.dsh_xiaoyu.run_site_action', side_effect=AssertionError('ULR called DSH')):
        conversation_id = str(uuid4())
        deleted = draft(conversation_id)
        assert auth_client.post('/api/ai/delete-conversation/', {'conversation_id': conversation_id}, format='json').status_code == 200
        assert auth_client.post(url, {'token': deleted['token'], 'answers': answers, 'confirmed': True}, format='json').status_code == 409
        card = draft(str(uuid4()))
        body = {'token': card['token'], 'answers': answers}
        assert auth_client.post(url, body, format='json').status_code == 400
        assert not DshSubmission.objects.exists()
        body['confirmed'] = True
        confirmed = auth_client.post(url, body, format='json')
        assert confirmed.status_code == 200 and confirmed.data['total_score'] == 1
        assert auth_client.post(url, body, format='json').data == confirmed.data
        assert auth_client.get(f"/api/ai/learning-actions/{card['request_id']}/").data == confirmed.data
        assert auth_client.get(f"/api/ai/dsh/actions/{card['request_id']}/").data == confirmed.data
    assert DshSubmission.objects.count() == 1 and provider.call_count == 4
