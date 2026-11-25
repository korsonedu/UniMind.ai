"""Drive two XiaoYu processes with independent locks and one test database."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from time import monotonic, sleep
from uuid import UUID, uuid4

import pytest


def child_database_environment(connection, sqlite_path):
    database = connection.settings_dict
    result = {f'DB_{field}': str(database.get(field) or '') for field in ('ENGINE', 'NAME', 'HOST', 'PORT', 'USER', 'PASSWORD')}
    if connection.vendor == 'sqlite':
        with closing(sqlite3.connect(sqlite_path)) as copied:
            connection.connection.backup(copied)
        result['DB_NAME'] = str(sqlite_path)
    elif connection.vendor != 'postgresql':
        pytest.skip('The child processes require SQLite or PostgreSQL.')
    return result


def run_worker():
    import django
    django.setup()

    from asgiref.sync import async_to_sync
    from django.test import override_settings
    from rest_framework.test import APIClient
    from unittest.mock import patch

    from ai_assistant.models import AIChatMessage
    from users.models import AIUsageReservation, User, WeeklyAIUsage

    user_id, ready, bodies = sys.argv[1:]
    user = User.objects.get(pk=user_id)
    client = APIClient()
    client.force_authenticate(user)

    def model(*_, **__):
        if ready:
            Path(ready).touch()
            assert sys.stdin.readline() == '\n'
        return {'choices': [{'finish_reason': 'stop', 'message': {'content': '进程对照答复。'}}]}

    async def final(response):
        assert response.status_code == 200
        events = [json.loads(frame[6:]) async for frame in response.streaming_content if frame.startswith(b'data: ')]
        return events[-1]

    with override_settings(ALLOWED_HOSTS=['testserver'], USE_MEM0=False, UNIMIND_DSH_TITLE_ENABLED=False,
            UNIMIND_DSH_MEMORY_ENABLED=False, CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}), \
            patch('ai_engine.service.AIEngine.call_provider', side_effect=model) as provider, \
            patch('ai_assistant.services.dsh_xiaoyu.extract_memories_async'), \
            patch('ai_assistant.services.dsh_xiaoyu.schedule_conversation_title'):
        results = [async_to_sync(final)(client.post('/api/ai/chat/stream/', body, format='json')) for body in json.loads(bodies)]
        print(json.dumps({'results': results, 'model_calls': provider.call_count,
            'charged': WeeklyAIUsage.objects.get(user=user).ai_calls,
            'requests': AIUsageReservation.objects.filter(user=user).count(),
            'messages': AIChatMessage.objects.filter(user=user).count()}, ensure_ascii=False))


@pytest.mark.django_db(transaction=True)
def test_ulr_database_serializes_one_conversation_across_processes(user, settings, tmp_path):
    from django.db import connection
    from django.utils import timezone

    from ai_assistant.models import AIChatMessage, Bot
    from users.learning import CHAT_RESERVATION_TTL
    from users.models import AIUsageReservation, CourseStudentStatus, WeeklyAIQuotaConfig

    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    WeeklyAIQuotaConfig.objects.update_or_create(pk=1, defaults={'experience_calls': 20, 'course_calls': 200})
    bot, _ = Bot.objects.get_or_create(is_xiaoyu=True, defaults={'name': '小宇'})
    database = tmp_path / 'shared.sqlite3'
    child_db = child_database_environment(connection, database)

    ready = tmp_path / 'first-model-waiting'
    body = {'bot_id': bot.pk, 'conversation_id': str(uuid4()), 'request_id': str(uuid4()), 'message': '第一条提问。'}
    contender = {**body, 'request_id': str(uuid4()), 'message': '同会话的另一条提问。'}
    independent = {**contender, 'request_id': str(uuid4()), 'conversation_id': str(uuid4())}

    def run(node, bodies, signal=''):
        postgresql = connection.vendor == 'postgresql'
        env = {**os.environ, **child_db, 'DJANGO_SETTINGS_MODULE': 'school_system.settings', 'PYTHONPATH': str(settings.BASE_DIR),
            'DEBUG': 'false' if postgresql else 'true', 'UNIMIND_LEARNING_RUNTIME': 'ulr' if postgresql else 'legacy',
            'UNIMIND_ULR_PROTOTYPE': 'true', 'UNIMIND_DSH_ENABLED': 'false', 'UNIMIND_DSH_XIAOYU_ENABLED': 'false',
            'UNIMIND_DSH_STATE_DIR': node if postgresql else str(tmp_path / node)}
        return subprocess.Popen([sys.executable, __file__, str(user.pk), str(signal), json.dumps(bodies)],
            cwd=settings.BASE_DIR, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def finish(process, prompt=''):
        try:
            stdout, stderr = process.communicate(prompt, timeout=15)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
        assert process.returncode == 0, stderr
        return json.loads(stdout.splitlines()[-1])

    def wait_for_model(process, signal):
        deadline = monotonic() + 12
        while not signal.exists() and process.poll() is None and monotonic() < deadline:
            sleep(.02)
        assert signal.exists() and process.poll() is None

    first = run('node-a', [body], ready)
    try:
        wait_for_model(first, ready)
        peer = finish(run('node-b', [body, contender, independent]))
        assert [event.get('is_error', False) for event in peer['results']] == [True, True, False]
        assert peer['model_calls'] == peer['charged'] == 1
        assert peer['requests'] == 2
        owner = finish(first, '\n')
        assert owner['results'][0]['engine'] == 'ulr' and owner['model_calls'] == 1
    finally:
        if first.poll() is None:
            first.kill()
            first.communicate()

    replay = finish(run('node-b', [body]))
    assert replay['results'] == owner['results'] and replay['model_calls'] == 0
    assert replay['messages'] == 4 and replay['charged'] == replay['requests'] == 2

    lost = {**body, 'request_id': str(uuid4()), 'message': '进程退出前的提问。'}
    crashed_signal = tmp_path / 'crashed-model-waiting'
    crashed = run('node-a', [lost], crashed_signal)
    try:
        wait_for_model(crashed, crashed_signal)
    finally:
        crashed.kill()
        crashed.communicate()

    expired_at = timezone.now() - CHAT_RESERVATION_TTL
    if connection.vendor == 'sqlite':
        with closing(sqlite3.connect(database)) as storage, storage:
            prompt_id, = storage.execute('SELECT MAX(id) FROM ai_assistant_aichatmessage').fetchone()
            scoped = storage.execute('UPDATE users_aiusagereservation SET updated_at = ? WHERE request_id = ?',
                (expired_at.strftime('%Y-%m-%d %H:%M:%S.%f'), UUID(lost['request_id']).hex))
            assert scoped.rowcount == 1
    else:
        prompt_id = AIChatMessage.objects.get(user=user, metadata__runtime_request_id=lost['request_id']).pk
        assert AIUsageReservation.objects.filter(user=user, request_id=lost['request_id']).update(updated_at=expired_at) == 1
    resumed = finish(run('node-b', [lost]))
    assert resumed['results'][0]['engine'] == 'ulr' and resumed['model_calls'] == 1
    assert resumed['results'][0]['user_message']['message_id'] == prompt_id
    assert resumed['messages'] == 6 and resumed['charged'] == resumed['requests'] == 3


if __name__ == '__main__':
    run_worker()
