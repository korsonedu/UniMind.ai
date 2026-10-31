"""Signed admin bridge + actual DSH parser; temporary DB and protocol fixture only."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch
from uuid import uuid4

from smoke import ROOT, fixture_database, model_fixture


def backend_smoke():
    database = fixture_database()  # Reject existing/non-temporary DBs before Django setup.
    os.environ.update(DB_ENGINE='django.db.backends.sqlite3', DB_NAME=database)
    sys.path.insert(0, str(ROOT / 'backend'))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school_system.settings')
    import django
    django.setup()
    from django.core.management import call_command
    from django.test import override_settings
    from rest_framework.test import APIClient
    from users.models import User
    from quizzes.models import ContentPipelineTask, KnowledgePoint, Question
    from backoffice.tasks import run_teaching_task
    call_command('migrate', interactive=False, verbosity=0)
    admins = [User.objects.create_superuser(username=f'parser-admin-{i}') for i in range(2)]
    actors = [str(uuid4()), str(uuid4())]
    secret = 'isolated-parser-fixture-secret-with-32-characters'
    client = APIClient()

    def request(operation, data):
        path = f'/api/backoffice/operations/{operation}/'
        body = json.dumps(data, ensure_ascii=False).encode()
        timestamp, nonce = str(int(time.time())), str(uuid4())
        canonical = '\n'.join(['v1', 'POST', path, actors[0], timestamp, nonce, hashlib.sha256(body).hexdigest()])
        signature = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
        return client.post(path, body, content_type='application/json', HTTP_X_UNIMIND_OPERATOR=actors[0],
            HTTP_X_UNIMIND_TIMESTAMP=timestamp, HTTP_X_UNIMIND_NONCE=nonce, HTTP_X_UNIMIND_SIGNATURE=signature)

    with override_settings(UNIMIND_ADMIN_BRIDGE_SECRET=secret,
            UNIMIND_DIRECTUS_ADMIN_MAP=dict(zip(actors, [user.pk for user in admins])),
            CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}):
        kp = KnowledgePoint.objects.create(name='合成录入考点', level='kp')
        data = {'kind': 'parse', 'kp_ids': [kp.pk], 'raw_text': '合成录入题：久期反映什么？答案：利率敏感度。', 'request_id': str(uuid4())}
        assert client.post('/api/backoffice/operations/teaching.generate/', data, format='json').status_code == 401
        with patch('backoffice.tasks.run_teaching_task.delay') as queue:
            first = request('teaching.generate', data)
            assert first.status_code == 200, first.data
            tid = first.data['id']
            assert request('teaching.generate', data).data['id'] == tid
            queue.assert_called_once_with(tid)
        run_teaching_task(tid)
        run_teaching_task(tid)
        task = ContentPipelineTask.objects.get(pk=tid)
        assert task.status == 'review', task.error_message
        assert not Question.objects.exists()
        candidate = task.result['questions'][0]
        assert candidate['kp_id'] == kp.pk and candidate['answer'].startswith('合成答案')
        review = {'id': tid, 'action': 'approve', 'question_indices': [0], 'request_id': str(uuid4())}
        assert request('pipeline.review', review).status_code == 400
        review['confirmed'] = True
        assert request('pipeline.review', review).status_code == 200
        assert request('pipeline.review', review).status_code == 200
        assert Question.objects.count() == 1
        print('RESULT ' + json.dumps({'signed_admin': True, 'native_parser': True,
            'draft_before_confirmation': True, 'confirmed_import_once': True}))


def main():
    if '--backend-fixture' in sys.argv:
        backend_smoke()
        return
    python = sys.argv[sys.argv.index('--backend-python') + 1]
    model, calls = model_fixture()
    try:
        with TemporaryDirectory(prefix='unimind-m0-smoke-') as state:
            env = {**os.environ, 'ACCOUNT_ENABLED': 'false', 'ACCOUNT_RSA_KEY_PATH': '',
                'ACCOUNT_DEV_LOCAL_CACHE': 'true', 'DJANGO_ENV': 'development', 'DEBUG': 'true',
                'UNIMIND_CONTENT_INSTITUTION_ID': 'global', 'UNIMIND_DSH_TEACHING_ENABLED': 'true',
                'UNIMIND_DSH_PYTHON': sys.executable, 'UNIMIND_DSH_STATE_DIR': str(Path(state) / 'tasks'),
                'UNIMIND_DSH_FIXTURE_URL': f'http://127.0.0.1:{model.server_port}/v1/messages',
                'UNIMIND_M0_FIXTURE_DB': str(Path(state) / 'db.sqlite3')}
            result = subprocess.run([python, __file__, '--backend-fixture'], env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=160)
            if result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
            assert len(calls) == 1, 'parser retries must not generate extra model requests'
            assert [tool['name'] for tool in calls[0]['tools']] == ['submit_questions']
            assert calls[0]['temperature'] == .2 and calls[0]['max_tokens'] == 3200
            assert '解析' in json.dumps(calls[0]['system'], ensure_ascii=False)
            print(next(line for line in result.stdout.splitlines() if line.startswith('RESULT ')))
    finally:
        model.shutdown()
        model.server_close()


if __name__ == '__main__':
    main()
