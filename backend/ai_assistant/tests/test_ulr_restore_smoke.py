"""Restore a synthetic DSH snapshot with the native PostgreSQL clients."""
import gzip
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
from uuid import UUID, uuid4

import pytest
from django.core.management import call_command
from django.db import connection
from django.utils import timezone

from ai_assistant.models import AIChatMessage, Bot, Conversation
from users.models import AIUsageReservation, CourseStudentStatus, WeeklyAIQuotaConfig
from .test_ulr_process_smoke import child_database_environment


def verify_restored_conversations(user_id, site_body, imported_id):
    from asgiref.sync import async_to_sync
    from django.conf import settings
    from django.test import override_settings
    from rest_framework.test import APIClient
    from unittest.mock import patch

    from users.models import User, WeeklyAIUsage

    assert settings.UNIMIND_LEARNING_RUNTIME == 'ulr' and not settings.UNIMIND_DSH_ENABLED
    user = User.objects.get(pk=user_id)
    client = APIClient()
    client.force_authenticate(user)
    legacy = AIUsageReservation.objects.get(user=user, request_id=site_body['request_id']).response
    initial_charge = WeeklyAIUsage.objects.get(user=user).ai_calls
    seen = []

    def model(messages, **kwargs):
        seen.append(json.dumps(messages, ensure_ascii=False))
        return {'choices': [{'finish_reason': 'stop', 'message': {'content': '从恢复的原对话继续。'}}]}

    async def final(response):
        assert response.status_code == 200
        events = [json.loads(frame[6:]) async for frame in response.streaming_content if frame.startswith(b'data: ')]
        return events[-1]

    def send(body):
        return async_to_sync(final)(client.post('/api/ai/chat/stream/', body, format='json'))

    with override_settings(ALLOWED_HOSTS=['testserver'], USE_MEM0=False, UNIMIND_DSH_TITLE_ENABLED=False,
            UNIMIND_DSH_MEMORY_ENABLED=False, CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}), \
            patch('ai_engine.service.AIEngine.call_provider', side_effect=model), \
            patch('ai_assistant.services.dsh_xiaoyu.run_site_action', side_effect=AssertionError('Unexpected DSH call')), \
            patch('ai_assistant.services.dsh_xiaoyu.extract_memories_async'), \
            patch('ai_assistant.services.dsh_xiaoyu.schedule_conversation_title'):
        assert send(site_body) == legacy and not seen
        changed = {**site_body, 'external_video_context': {**site_body['external_video_context'], 'part': 2}}
        assert client.post('/api/ai/chat/', changed, format='json').status_code == 400
        assert not seen and WeeklyAIUsage.objects.get(user=user).ai_calls == initial_charge
        histories = ((site_body['conversation_id'], legacy['full_content']), (imported_id, '合成迁移答复'))
        for index, (conversation_id, old_reply) in enumerate(histories, start=1):
            body = {'bot_id': site_body['bot_id'], 'conversation_id': conversation_id, 'request_id': str(uuid4()),
                    'message': '请接着上次的讲解。'}
            resumed = send(body)
            assert resumed['engine'] == 'ulr' and resumed['conversation_id'] == conversation_id
            assert len(seen) == index and old_reply in seen[-1]
            assert WeeklyAIUsage.objects.get(user=user).ai_calls == initial_charge + index
            assert send(body) == resumed
            receipt = client.get(f"/api/ai/chat-requests/{body['request_id']}/")
            assert receipt.status_code == 200 and receipt.data['response'] == resumed
            assert len(seen) == index and WeeklyAIUsage.objects.get(user=user).ai_calls == initial_charge + index


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(not os.environ.get('ULR_QUEUE_SMOKE'), reason='optional native PostgreSQL restore smoke')
def test_native_restore_and_retirement_gate(user, settings, tmp_path):
    if connection.vendor != 'postgresql':
        pytest.skip('Requires a disposable PostgreSQL test database.')
    from django.db.backends.postgresql.psycopg_any import sql
    from types import SimpleNamespace

    from ai_assistant.services.external_video_context import prepare_external_video_context
    from ai_assistant.views import _reserve_chat_request
    from quizzes.models import ContentPipelineTask
    from users.learning import confirm_ai_call

    assert shutil.which('psql') and shutil.which('pg_dump')
    settings.UNIMIND_DSH_ENABLED = False
    bot = Bot.objects.create(is_xiaoyu=True, name='小宇', bot_type='planner')
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    WeeklyAIQuotaConfig.objects.update_or_create(pk=1, defaults={'experience_calls': 20, 'course_calls': 200})
    api_url, session_id = 'http://127.0.0.1:8000', uuid4().hex
    transcript = {'id': session_id, 'messages': [{'role': 'user', 'content': '合成迁移问题'},
                                             {'role': 'assistant', 'content': '合成迁移答复'}]}
    AIUsageReservation.objects.create(user=user, request_id=uuid4(), attempt_id=uuid4(), week=timezone.now().date(),
        status='succeeded', response={'engine': 'dsh', 'session_id': session_id, 'finish_reason': 'completed',
                                     'session': transcript, 'content': transcript['messages'][-1]['content']})
    state = tmp_path / 'dsh-state'
    owner = hashlib.sha256(json.dumps([api_url, user.pk]).encode()).hexdigest()
    directory = state / owner / session_id
    directory.mkdir(parents=True)
    (directory / 'transcript.json').write_text(json.dumps(transcript, ensure_ascii=False))

    site_id, site_session = uuid4(), uuid4().hex
    site = {'user': user, 'bot': bot, 'conversation_id': site_id}
    Conversation.objects.create(**site, title='合成原小宇对话')
    site_body = {'bot_id': bot.pk, 'conversation_id': str(site_id), 'request_id': str(uuid4()), 'message': '合成原问答',
        'external_video_context': {'platform': 'bilibili', 'external_id': 'BV1Restore', 'video_seconds': 60}}
    video = prepare_external_video_context(SimpleNamespace(data=site_body), bot, site_id)
    receipt = _reserve_chat_request(user, site_body, bot, conversation_id=site_id)
    prompt = AIChatMessage.objects.create(**site, role='user', content=site_body['message'],
        metadata={'runtime_request_id': site_body['request_id'], 'external_video_context': video})
    metadata = {'engine': 'dsh', 'dsh_session_id': site_session, 'external_video_context': video,
                'learning_turn': {'message_id': prompt.pk}}
    answer = AIChatMessage.objects.create(**site, role='assistant', content='合成原会话答复', metadata=metadata)
    confirm_ai_call(receipt, response={'engine': 'dsh', 'done': True, 'session_id': site_session,
        'full_content': answer.content, 'message_id': answer.pk, 'user_message': {'message_id': prompt.pk, 'metadata': prompt.metadata}, 'metadata': metadata})
    site_directory = state / owner / site_session
    site_directory.mkdir()
    (site_directory / 'transcript.json').write_text(json.dumps({'id': site_session, 'messages': [
        {'role': row.role, 'content': row.content} for row in (prompt, answer)]}, ensure_ascii=False))
    unsettled = ContentPipelineTask.objects.create(created_by=user, task_type='ai_generate',
        title='合成待核对旧出题', status='failed', payload={'bulk_mode': True, 'current_stage': 'generating'})

    env = {'PATH': os.environ['PATH'], 'TMPDIR': str(tmp_path), 'DJANGO_ENV': 'test',
           'UNIMIND_DSH_ENABLED': 'false', 'UNIMIND_LEARNING_RUNTIME': 'ulr',
           **child_database_environment(connection, tmp_path / 'unused.sqlite3')}
    pg_options = ['-h', env['DB_HOST'], '-p', env['DB_PORT'], '-U', env['DB_USER']]
    pg_env = {**env, 'PGPASSWORD': env['DB_PASSWORD']}
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    for name in ('backup_db.sh', 'restore_db.sh'):
        shutil.copy2(Path(settings.BASE_DIR).parent / 'scripts' / name, scripts / name)
    config = tmp_path / 'backend' / '.env'
    config.parent.mkdir()
    for name in ('media', 'logs'):
        (config.parent / name).mkdir()
    config.write_text(f'UNIMIND_DSH_STATE_DIR={shlex.quote(str(state))}\n')
    saved = subprocess.run(['bash', str(scripts / 'backup_db.sh')], env=env,
                           capture_output=True, text=True, timeout=60)
    assert saved.returncode == 0, saved.stderr
    backup, = (tmp_path / 'backups').glob('*.sql.gz')
    checksum = hashlib.sha256(backup.read_bytes()).hexdigest()
    assert backup.with_suffix('.gz.sha256').read_text().split()[0] == checksum
    timestamp = backup.name.removeprefix(f"{env['DB_NAME']}_").removesuffix('.sql.gz')
    archive = backup.with_name(f'files_{timestamp}.tar.gz')
    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert archive.with_suffix('.gz.sha256').read_text().split()[0] == archive_hash
    inventory = StringIO()
    call_command('audit_dsh_sessions', state_dir=str(state), api_url=api_url, state_fingerprint=True,
                 database_backup=str(backup), stdout=inventory)
    fingerprints = json.loads(inventory.getvalue())
    assert fingerprints['database_fingerprint'] == checksum and fingerprints['state_transcripts'] == 2

    restored_files = tmp_path / 'restored-files'
    state_prefix = state.as_posix().lstrip('/')
    with tarfile.open(archive, 'r:gz') as bundle:
        state_entries = [entry for entry in bundle if entry.name.startswith(f'{state_prefix}/')]
        bundle.extractall(restored_files, members=state_entries, filter='data')
    restored_state = restored_files / state_prefix
    assert restored_state.is_dir()
    script = scripts / 'restore_db.sh'
    target = f'ulr_restore_{uuid4().hex}'
    failed_target = f'{target}_failed'
    # Simulate a checkout configured for a different database on the same disposable cluster.
    config.write_text(f'DB_NAME={failed_target}\n')
    restored_env = {**env, 'DB_NAME': target}
    command = [sys.executable, str(Path(settings.BASE_DIR) / 'manage.py'), 'audit_dsh_sessions',
               '--state-dir', str(restored_state), '--api-url', api_url]
    gate = [*command, '--require-paired-restore', '--database-backup', str(backup), '--expected-state-fingerprint',
            fingerprints['state_fingerprint'], '--expected-database-fingerprint', checksum]
    def sql_probe(database, query):
        return subprocess.run(['psql', '-XAtv', 'ON_ERROR_STOP=1', *pg_options, '-d', database, '-c', query],
                              env=pg_env, capture_output=True, text=True, timeout=10, check=True).stdout.strip()

    try:
        for database in (target, failed_target):
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
            sql_probe(database, 'CREATE TABLE old_record AS SELECT 19 AS value')
        restored = subprocess.run(['bash', str(script), str(backup)], input='YES\n', text=True,
                                  env=restored_env, capture_output=True, timeout=60)
        assert restored.returncode == 0, restored.stderr
        assert sql_probe(target, "SELECT to_regclass('old_record') IS NULL") == 't'
        assert sql_probe(failed_target, 'SELECT value FROM old_record') == '19'
        imported = subprocess.run([*command, '--import-verified'], env=restored_env, capture_output=True,
                                  text=True, timeout=30, check=True)
        assert json.loads(imported.stdout)['imported'] == 1
        blocked = subprocess.run(gate, env=restored_env, capture_output=True, text=True, timeout=30)
        report = json.loads(blocked.stdout)
        assert blocked.returncode != 0 and report['snapshot_pair_verified'] and report['database_restore_verified']
        assert not report['paired_migration_verified']
        assert report['blockers'] == {'unsettled_legacy_question_pipelines': 1}
        assert report['unsettled_question_pipeline_ids'] == [unsettled.pk]
        # Settle the synthetic review on the restored copy for the continuation check.
        sql_probe(target, f"UPDATE quizzes_contentpipelinetask SET status = 'cancelled' WHERE id = {unsettled.pk}")
        unsettled.refresh_from_db()
        assert unsettled.status == 'failed'
        verify = ('from ai_assistant.tests.test_ulr_restore_smoke import verify_restored_conversations; '
                  f'verify_restored_conversations({user.pk}, {site_body!r}, {str(UUID(hex=session_id))!r})')
        continued = subprocess.run([sys.executable, command[1], 'shell', '-c', verify],
            env={**restored_env, 'DEBUG': 'false', 'UNIMIND_DSH_XIAOYU_ENABLED': 'false'},
            capture_output=True, text=True, timeout=30)
        assert continued.returncode == 0, continued.stderr
        verified = subprocess.run(gate, env=restored_env, capture_output=True, text=True, timeout=30, check=True)
        report = json.loads(verified.stdout)
        assert report['snapshot_pair_verified'] and report['database_restore_verified'] and report['migrated']
        assert report['paired_migration_verified']
        assert report['site_matched'] == report['already_imported'] == 1
        assert report['target_runtime'] == 'ulr'
        legacy = subprocess.run(gate, env={**restored_env, 'UNIMIND_LEARNING_RUNTIME': 'legacy'},
                                capture_output=True, text=True, timeout=30)
        report = json.loads(legacy.stdout)
        assert legacy.returncode != 0 and report['snapshot_pair_verified'] and report['database_restore_verified']
        assert not report['paired_migration_verified']
        assert report['blockers'] == {'target_runtime_not_ulr': 1}
        wrong = subprocess.run(gate, env=env, capture_output=True, text=True, timeout=30)
        report = json.loads(wrong.stdout)
        assert wrong.returncode != 0 and report['snapshot_pair_verified'] and not report['database_restore_verified']
        assert not report['paired_migration_verified']
        assert report['blockers']['database_restore_fingerprint_mismatch'] == 1

        broken = tmp_path / 'broken.sql.gz'
        broken.write_bytes(gzip.compress(b'CREATE TABLE restore_probe(id integer);\nSELECT 1/0;\n', mtime=0))
        failed = subprocess.run(['bash', str(script), str(broken)], input='YES\n', text=True,
                                env={**env, 'DB_NAME': failed_target}, capture_output=True, timeout=30)
        assert failed.returncode != 0 and 'division by zero' in failed.stderr
        assert sql_probe(failed_target, 'SELECT value FROM old_record') == '19'
        assert sql_probe(failed_target, "SELECT to_regclass('restore_probe') IS NULL AND "
                                        "current_setting('unimind.restore_sha256', true) IS NULL") == 't'
    finally:
        with connection.cursor() as cursor:
            for database in (target, failed_target):
                cursor.execute(sql.SQL('DROP DATABASE IF EXISTS {}').format(sql.Identifier(database)))
