"""Exercise saved course images through signed callbacks and legacy streaming."""
import asyncio
import copy
import json
import socket
from uuid import uuid4
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from ai_assistant.dsh_authentication import make_task_token
from ai_assistant.models import AIChatMessage
from ai_assistant.services.course_context import course_visual_messages, prepare_course_context
from ai_assistant.tests.test_course_context import lesson, question
from ai_assistant.tests.test_course_visual import visual


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Course visual pipeline tests must not access the network')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)


@pytest.fixture
def saved_question(user, lesson, visual, settings):
    settings.UNIMIND_DSH_ENABLED = True
    course, _, bot = lesson
    request = question(user, course)
    request.data['course_context']['visual'] = visual
    context = prepare_course_context(request, bot, request.data['conversation_id'])
    current = AIChatMessage.objects.create(
        user=user, bot=bot, conversation_id=request.data['conversation_id'],
        role='user', content=request.data['message'], metadata={'course_context': context})
    claims = {'conversation_id': str(current.conversation_id),
              'bot_id': bot.pk, 'message_id': current.pk}
    return current, context, claims


def signed_client(user, claims=None):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION='DSH ' + make_task_token(user, chat_context=claims))
    return client


def assert_no_image_bytes(text, context):
    assert isinstance(text, str)
    assert 'base64' not in text
    for frame in context['visual'].values():
        assert frame['image'].split(',', 1)[1] not in text


@pytest.mark.django_db
@pytest.mark.parametrize('with_previous', [False, True])
def test_signed_context_returns_only_saved_question_images(user, lesson, saved_question, with_previous):
    current, context, claims = saved_question
    if not with_previous:
        context['visual'].pop('previous')
        current.metadata['course_context'] = context
        current.save(update_fields=['metadata'])
    _, transcript, _ = lesson
    transcript.revision = 4
    transcript.save(update_fields=['revision'])
    transcript.segments.update(text='NEW_TRANSCRIPT_NOT_IN_SAVED_QUESTION')
    # Caller-provided blocks must not replace the saved images authorized by claims.
    body = {'message': current.content,
            'course_visual_content': [{'type': 'text', 'text': 'FORGED_VISUAL'}],
            'course_visual_message': 'FORGED_QUESTION'}
    response = signed_client(user, claims).post('/api/ai/dsh/context/', body, format='json')
    assert response.status_code == 200
    payload = response.json()
    assert payload['student']['id'] == user.pk
    assert payload['course_visual_message'] == current.content
    blocks = payload['course_visual_content']
    assert isinstance(blocks, list) and blocks == course_visual_messages(context)
    images = [block['image_url']['url'] for block in blocks if block['type'] == 'image_url']
    keys = ['previous', 'current'] if with_previous else ['current']
    assert images == [context['visual'][key]['image'] for key in keys]
    assert len(images) == len(keys)
    assert 'FULL_SEGMENT_END' in payload['system_prompt']
    assert 'NEW_TRANSCRIPT_NOT_IN_SAVED_QUESTION' not in payload['system_prompt']
    assert 'FORGED_VISUAL' not in json.dumps(payload, ensure_ascii=False)
    assert_no_image_bytes(payload['system_prompt'], context)
    current.refresh_from_db()
    assert current.metadata['course_context'] == context


@pytest.mark.django_db
@pytest.mark.parametrize('authentication', ['task_without_claims', 'site_login'])
def test_context_without_signed_chat_claims_cannot_get_images(
        user, auth_client, saved_question, authentication):
    current, context, claims = saved_question
    client = signed_client(user) if authentication == 'task_without_claims' else auth_client
    response = client.post('/api/ai/dsh/context/', {
        'message': current.content, 'chat_context': claims,
        'course_context': context, 'message_id': current.pk,
    }, format='json')
    assert response.status_code == 200
    payload = response.json()
    assert 'course_visual_content' not in payload
    assert 'course_visual_message' not in payload
    assert_no_image_bytes(json.dumps(payload, ensure_ascii=False), context)


@pytest.mark.django_db
@pytest.mark.parametrize('mismatch', ['user', 'message_text', 'message_id', 'conversation', 'bot'])
def test_signed_course_visual_identity_mismatches_are_forbidden(user, saved_question, mismatch):
    current, context, saved_claims = saved_question
    claims = dict(saved_claims)
    actor, message = user, current.content
    if mismatch == 'user':
        actor = type(user).objects.create_user(username='other-visual-owner')
    elif mismatch == 'message_text':
        message = '替换后的问题'
    elif mismatch == 'message_id':
        # The signed message ID exists but belongs to another question.
        other = AIChatMessage.objects.create(
            user=user, bot=current.bot, conversation_id=current.conversation_id,
            role='user', content='本人的另一条问题', metadata={'course_context': context})
        claims['message_id'] = other.pk
    elif mismatch == 'conversation':
        claims['conversation_id'] = str(uuid4())
    else:
        claims['bot_id'] = current.bot_id + 1
    response = signed_client(actor, claims).post(
        '/api/ai/dsh/context/', {'message': message}, format='json')
    assert response.status_code == 403
    payload = response.json()
    assert 'course_visual_content' not in payload
    assert_no_image_bytes(json.dumps(payload, ensure_ascii=False), context)


def stream_events(response):
    assert response.status_code == 200

    async def collect():
        return b''.join([chunk async for chunk in response.streaming_content])

    raw = asyncio.run(collect()) if response.is_async else b''.join(response.streaming_content)
    return [json.loads(line[6:]) for line in raw.decode().splitlines() if line.startswith('data: ')]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('with_previous', [False, True])
def test_legacy_engine_receives_image_arrays_and_same_request_replays_frozen_sources(
        auth_client, user, lesson, visual, settings, with_previous):
    if not with_previous:
        visual.pop('previous')
    from users.models import AIUsageReservation, WeeklyAIQuotaConfig
    settings.UNIMIND_DSH_XIAOYU_ENABLED = False
    WeeklyAIQuotaConfig.objects.update_or_create(
        pk=1, defaults={'experience_calls': 20, 'course_calls': 200})
    course, transcript, bot = lesson
    request = question(user, course)
    request.data['course_context']['visual'] = visual
    body = {**request.data, 'bot_id': bot.pk}
    context = prepare_course_context(request, bot, body['conversation_id'])
    frozen = copy.deepcopy(context)
    expected_blocks = course_visual_messages(frozen)

    def answer(**kwargs):
        messages = kwargs['messages']
        visual_messages = [row for row in messages if isinstance(row['content'], list)]
        assert len(visual_messages) == 1
        assert visual_messages[0]['role'] == 'user'
        assert visual_messages[0]['content'] == expected_blocks
        assert any(block['type'] == 'image_url' for block in visual_messages[0]['content'])
        # The actual dispatch path must preserve the array, with no stringified copy.
        text_messages = [row for row in messages if isinstance(row['content'], str)]
        for row in text_messages:
            assert_no_image_bytes(row['content'], frozen)
            assert 'image_url' not in row['content']
        reference = '\n'.join(row['content'] for row in text_messages)
        assert 'FULL_SEGMENT_END' in reference and 'OUTSIDE_AFTER' not in reference
        assert messages[-1] == {'role': 'user', 'content': body['message']}
        return {'content': '结合画面和讲稿解释折现。', 'finish_reason': 'completed'}

    with patch('ai_engine.service.AIEngine.call_ai_with_streaming_tools', side_effect=answer) as engine, \
         patch('ai_assistant.services.title_generator.sync_generate_title', return_value='课程图文答疑'):
        events = stream_events(auth_client.post('/api/ai/chat/stream/', body, format='json'))
        done = next(event for event in events if event.get('done'))
        assert done['full_content'] == '结合画面和讲稿解释折现。'
        assert not done.get('is_error')
        assert done['metadata']['course_context'] == frozen
        assert done['user_message']['metadata']['course_context'] == frozen
        engine.assert_called_once()

        # Same request and pixels, but the database now has a different transcript.
        transcript.revision = 4
        transcript.save(update_fields=['revision'])
        transcript.segments.update(text='CHANGED_AFTER_SUCCESS')
        refreshed = prepare_course_context(request, bot, body['conversation_id'])
        assert refreshed['revision'] == 4 and refreshed['segments'] != frozen['segments']
        replay_events = stream_events(auth_client.post('/api/ai/chat/stream/', body, format='json'))
        replay = next(event for event in replay_events if event.get('done'))
        assert replay == done
        engine.assert_called_once()

    rows = list(AIChatMessage.objects.filter(conversation_id=body['conversation_id']).order_by('id'))
    assert [row.role for row in rows] == ['user', 'assistant']
    assert rows[0].pk == done['user_message']['message_id']
    assert rows[1].pk == done['message_id']
    assert all(row.metadata['course_context'] == frozen for row in rows)
    reservation = AIUsageReservation.objects.get(user=user, request_id=body['request_id'])
    assert reservation.status == 'succeeded' and reservation.response == done
