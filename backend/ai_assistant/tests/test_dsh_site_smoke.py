"""Targeted admission and existing quota smoke for the opt-in site bridge."""
from datetime import date
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import sys
from uuid import uuid4
from unittest.mock import patch

import pytest
from django.db import OperationalError
from rest_framework.test import APIClient

from ai_assistant.dsh_authentication import make_task_token
from ai_assistant.services.dsh_runtime import DshUnavailable, run_site_action, site_request_lock
from users.models import AIUsageReservation, WeeklyAIQuotaConfig, WeeklyAIUsage


@pytest.mark.django_db
def test_task_callback_scope(user, settings):
    settings.UNIMIND_DSH_ENABLED = True
    reservation = AIUsageReservation.objects.create(user=user, request_id=uuid4(), attempt_id=uuid4(), week=date(2026, 10, 26))
    token = make_task_token(user, reservation)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION='DSH ' + token)
    assert client.post('/api/ai/dsh/context/', {}, format='json').json()['student']['id'] == user.pk
    assert client.get('/api/ai/memories/').status_code == 401
    other = type(user).objects.create_user(username='other-site-student')
    client.credentials(HTTP_AUTHORIZATION='DSH ' + make_task_token(other, reservation))
    assert client.post('/api/ai/dsh/context/', {}, format='json').status_code == 401
    client.credentials(HTTP_AUTHORIZATION='DSH ' + token + 'tampered')
    assert client.post('/api/ai/dsh/context/', {}, format='json').status_code == 401
    with patch('time.time', return_value=1000):
        expired = make_task_token(user, reservation)
    with patch('time.time', return_value=1121):
        client.credentials(HTTP_AUTHORIZATION='DSH ' + expired)
        assert client.post('/api/ai/dsh/context/', {}, format='json').status_code == 401
    reservation.status = 'succeeded'
    reservation.save()
    client.credentials(HTTP_AUTHORIZATION='DSH ' + token)
    assert client.post('/api/ai/dsh/context/', {}, format='json').status_code == 401


@pytest.mark.django_db
def test_site_quota_and_idempotency(auth_client, user, settings, tmp_path):
    url = '/api/ai/dsh/chat/'
    body = {'message': '查询学习统计', 'request_id': str(uuid4()), 'model': 'client-cannot-select'}
    assert auth_client.post(url, body, format='json').status_code == 404
    settings.UNIMIND_DSH_ENABLED = settings.UNIMIND_DSH_SITE_ENABLED = True
    settings.UNIMIND_DSH_STATE_DIR = str(tmp_path / 'site-state')
    WeeklyAIQuotaConfig.objects.update_or_create(pk=1, defaults={'experience_calls': 20, 'course_calls': 200})
    assert APIClient().post(url, body, format='json').status_code == 401
    with site_request_lock(user):
        assert auth_client.post(url, body, format='json').status_code == 409
    assert not AIUsageReservation.objects.filter(user=user).exists()
    result = {'content': '合成统计', 'finish_reason': 'completed', 'session_id': 'a' * 32}
    with patch('ai_assistant.views_dsh.run_site_action', return_value=result) as runtime:
        first = auth_client.post(url, body, format='json')
        assert first.status_code == 200, first.data
        assert auth_client.post(url, body, format='json').json() == first.json()
        assert runtime.call_count == 1
        assert runtime.call_args.kwargs['message'] == body['message']
        assert 'model' not in runtime.call_args.kwargs
        assert auth_client.post(url, {**body, 'message': '另一问题'}, format='json').status_code == 400
    assert WeeklyAIUsage.objects.get(user=user).ai_calls == 1
    failed = {'message': '未完成', 'request_id': str(uuid4())}
    with patch('ai_assistant.views_dsh.run_site_action', return_value={'content': '截断', 'finish_reason': 'max-tokens'}):
        assert auth_client.post(url, failed, format='json').status_code == 503
    assert AIUsageReservation.objects.get(user=user, request_id=failed['request_id']).status == 'released'
    assert WeeklyAIUsage.objects.get(user=user).ai_calls == 1
    with patch('ai_assistant.views_dsh.run_site_action', return_value={'deleted': True}):
        assert auth_client.post('/api/ai/dsh/session/delete/', {'session_id': 'a' * 32}, format='json').status_code == 200
    assert AIUsageReservation.objects.get(user=user, request_id=body['request_id']).response == {'engine': 'dsh', 'session_id': 'a' * 32, 'deleted': True}
    with patch('ai_assistant.views_dsh.run_site_action') as runtime:
        assert auth_client.post(url, body, format='json').status_code == 410
        runtime.assert_not_called()


@pytest.mark.django_db
def test_timeout_cleans_parent_owned_session(user, settings, tmp_path):
    settings.DEBUG = True
    settings.UNIMIND_DSH_PYTHON = sys.executable
    settings.UNIMIND_DSH_API_URL = 'http://127.0.0.1:8911'
    settings.UNIMIND_DSH_STATE_DIR = str(tmp_path / 'sessions')
    settings.UNIMIND_DSH_FIXTURE_URL = 'http://127.0.0.1:8912/v1/messages'
    def communicate(body=None, **_kwargs):
        if body is None:
            return b'', b''
        payload = json.loads(body)
        owner = hashlib.sha256(json.dumps([payload['api_url'], user.pk]).encode()).hexdigest()
        directory = Path(payload['state_dir']) / owner / (payload.get('session_id') or 'b' * 32)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'transcript.json').write_text('SYNTHETIC_PRIVATE_PROMPT')
        raise subprocess.TimeoutExpired('worker', 120)
    with patch('ai_assistant.services.dsh_runtime.subprocess.Popen') as popen, \
            patch('ai_assistant.services.dsh_runtime.os.killpg') as kill:
        process = popen.return_value.__enter__.return_value
        process.pid = 123456789
        process.communicate.side_effect = communicate
        with pytest.raises(DshUnavailable):
            run_site_action(user, 'chat', message='合成超时提问')
        kill.assert_called_once_with(process.pid, signal.SIGKILL)
    assert not list(Path(settings.UNIMIND_DSH_STATE_DIR).rglob('transcript.json'))


@pytest.mark.django_db
def test_delete_cache_failure_can_be_retried(auth_client, user, settings, tmp_path):
    settings.UNIMIND_DSH_ENABLED = settings.UNIMIND_DSH_SITE_ENABLED = True
    settings.UNIMIND_DSH_STATE_DIR = str(tmp_path / 'sessions')
    sid = 'c' * 32
    reservation = AIUsageReservation.objects.create(user=user, request_id=uuid4(), attempt_id=uuid4(),
        week=date(2026, 10, 26), status='succeeded',
        response={'engine': 'dsh', 'session_id': sid, 'content': 'SYNTHETIC_DELETED_TEXT'})
    with patch('ai_assistant.views_dsh.run_site_action', return_value={'deleted': True}) as runtime:
        with patch('ai_assistant.views_dsh.AIUsageReservation.objects.filter') as query:
            query.return_value.update.side_effect = OperationalError('database is locked')
            assert auth_client.post('/api/ai/dsh/session/delete/', {'session_id': sid}, format='json').status_code == 503
        runtime.assert_not_called()
        assert auth_client.post('/api/ai/dsh/session/delete/', {'session_id': sid}, format='json').status_code == 200
    missing = DshUnavailable('missing')
    missing.status_code = 404
    with patch('ai_assistant.views_dsh.run_site_action', side_effect=missing):
        assert auth_client.post('/api/ai/dsh/session/delete/', {'session_id': sid}, format='json').status_code == 200
    reservation.refresh_from_db()
    assert reservation.response == {'engine': 'dsh', 'session_id': sid, 'deleted': True}


@pytest.mark.django_db
def test_site_status_cookie_and_source(user, settings):
    from rest_framework.authtoken.models import Token
    client = APIClient()
    client.cookies['auth_token'] = Token.objects.get_or_create(user=user)[0].key
    url = '/api/ai/dsh/status/'
    assert client.get(url).status_code == 404
    settings.UNIMIND_DSH_ENABLED = settings.UNIMIND_DSH_SITE_ENABLED = True
    assert APIClient().get(url).status_code == 401
    settings.DEBUG = True
    settings.UNIMIND_DSH_FIXTURE_URL = 'http://127.0.0.1:8912/v1/messages'
    result = client.get(url)
    assert result.status_code == 200
    assert result.json() == {'student': {'id': user.pk, 'name': user.nickname or user.username},
                             'mode': 'local-protocol-smoke', 'model_configured': True}
    settings.DEBUG = False
    assert client.get(url).json()['mode'] == 'unavailable'
    assert client.get(url).json()['model_configured'] is False
    settings.UNIMIND_DSH_FIXTURE_URL = ''
    with patch('ai_assistant.views_dsh.get_model_for_task', return_value={'base_url': 'https://api.deepseek.com/v1/chat/completions', 'api_key': ''}):
        assert client.get(url).json()['mode'] == 'unavailable'
    with patch('ai_assistant.views_dsh.get_model_for_task', return_value={'base_url': 'https://unapproved.invalid/v1', 'api_key': 'SYNTHETIC_SECRET'}):
        assert client.get(url).json()['model_configured'] is False
    with patch('ai_assistant.views_dsh.get_model_for_task', return_value={'base_url': 'https://api.deepseek.com/v1/chat/completions', 'api_key': 'SYNTHETIC_SECRET'}):
        assert client.get(url).json()['mode'] == 'deepseek-official'
        assert 'SYNTHETIC_SECRET' not in client.get(url).content.decode()
    client.credentials(HTTP_AUTHORIZATION='DSH ' + make_task_token(user))
    client.cookies.clear()
    assert client.get(url).status_code == 401


@pytest.mark.django_db(transaction=True)
def test_site_stream_is_live_and_idempotent(auth_client, user, settings, tmp_path):
    from asgiref.sync import async_to_sync
    from threading import Event
    settings.UNIMIND_DSH_ENABLED = settings.UNIMIND_DSH_SITE_ENABLED = True
    settings.UNIMIND_DSH_STATE_DIR = str(tmp_path / 'stream-state')
    WeeklyAIQuotaConfig.objects.update_or_create(pk=1, defaults={'experience_calls': 20, 'course_calls': 200})
    body = {'message': '合成流式提问', 'request_id': str(uuid4())}
    finish = Event()
    result = {'content': '完整回答', 'finish_reason': 'completed', 'session_id': 'd' * 32}
    def runtime(*_args, on_event=None, **_kwargs):
        on_event({'type': 'step', 'step': 1})
        on_event({'type': 'text_delta', 'text': '临时正文'})
        assert finish.wait(5), 'consumer did not receive a live event'
        return dict(result)
    async def consume(response, live=False):
        frames = []
        async for frame in response.streaming_content:
            if frame.startswith(b'data: '):
                event = json.loads(frame[6:])
                frames.append(event)
                if live and event['type'] == 'text_delta':
                    assert not finish.is_set()
                    finish.set()
        return frames
    with patch('ai_assistant.views_dsh.run_site_action', side_effect=runtime) as mocked:
        response = auth_client.post('/api/ai/dsh/chat/stream/', body, format='json')
        assert response.status_code == 200 and response.is_async
        events = async_to_sync(consume)(response, True)
        assert [event['type'] for event in events] == ['step', 'text_delta', 'done']
        assert events[-1]['result']['content'] == '完整回答'
        again = auth_client.post('/api/ai/dsh/chat/stream/', body, format='json')
        assert async_to_sync(consume)(again)[-1] == events[-1]
        assert mocked.call_count == 1
    assert WeeklyAIUsage.objects.get(user=user).ai_calls == 1
    with patch('ai_assistant.views_dsh.run_site_action', side_effect=DshUnavailable()):
        failed = auth_client.post('/api/ai/dsh/chat/stream/', {**body, 'request_id': str(uuid4())}, format='json')
        assert [event['type'] for event in async_to_sync(consume)(failed)] == ['error']
    assert WeeklyAIUsage.objects.get(user=user).ai_calls == 1


def test_stream_terminal_does_not_wait_for_slow_consumer():
    from asgiref.sync import async_to_sync
    import asyncio
    from threading import Event
    from ai_assistant.services.dsh_stream import stream_events
    continue_task, cleaned = Event(), Event()
    cleanup_calls = []
    def cleanup():
        cleanup_calls.append(True)
        if len(cleanup_calls) == 2:
            cleaned.set()
    def action(emit):
        emit({'type': 'step', 'step': 1})
        assert continue_task.wait(2)
        for _ in range(100):
            emit({'type': 'text_delta', 'text': '合成片段'})
        return {'content': '完整结果'}
    async def consume():
        unused = stream_events(action)
        await unused.aclose()
        assert cleanup_calls == [], 'unconsumed response must not start a task'
        stream = stream_events(action)
        try:
            assert b'"step"' in await anext(stream)
            continue_task.set()
            assert await asyncio.to_thread(cleaned.wait, 1), 'completed producer must release ORM even if consumer stalls'
            events = [json.loads(frame[6:]) async for frame in stream]
            assert len(events) <= 64 and events[-1] == {'type': 'done', 'result': {'content': '完整结果'}}
        finally:
            await stream.aclose()
        cleanup_calls.clear(); cleaned.clear(); continue_task.clear()
        disconnected = stream_events(action)
        assert b'"step"' in await anext(disconnected)
        await disconnected.aclose()
        continue_task.set()
        assert await asyncio.to_thread(cleaned.wait, 1), 'disconnected task must still finish cleanup'
    with patch('ai_assistant.services.dsh_stream.close_old_connections', side_effect=cleanup):
        async_to_sync(consume)()
