"""Persistent synthetic preview; run with the existing Django Python environment."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from urllib.parse import quote, urlsplit


ROOT = Path(__file__).resolve().parent.parent
STUDENTS = {'student-a': 'm0-student', 'student-b': 'm0-other'}


def isolate_environment():
    runtime = {name: os.environ[name] for name in ('PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'SYSTEMROOT')
               if name in os.environ}
    os.environ.clear()
    os.environ.update(runtime, PYTHON_DOTENV_DISABLED='1')


def preview_state(value):
    root = ROOT.resolve()
    candidate = Path(value) if Path(value).is_absolute() else root / value
    if any(path.is_symlink() for path in (candidate, *candidate.parents) if path.is_relative_to(root)):
        raise ValueError('Preview state cannot use symbolic links.')
    state = candidate.resolve()
    if not state.is_relative_to(root / '.m0-state') or state == root / '.m0-state':
        raise ValueError('Preview state must be a directory below .m0-state.')
    if any((state / name).is_symlink() for name in ('db.sqlite3', 'sessions', 'media', 'redis.log', 'runtime.json', '.preview.lock')):
        raise ValueError('Preview files cannot use symbolic links.')
    return state


def check_database(state):
    uri = 'file:' + quote(str(state / 'db.sqlite3')) + '?mode=ro'
    with sqlite3.connect(uri, uri=True) as database:
        names = {row[0] for row in database.execute('SELECT username FROM users_user')}
    if names != set(STUDENTS.values()):
        raise ValueError('Preview database must contain only the two synthetic students.')


def sdk_executable(value):
    # Resolving the executable symlink would bypass pyvenv.cfg and lose the SDK.
    python = os.path.abspath(value)
    if not Path(python).is_file() or subprocess.run([python, '-c', 'import deepseek_harness'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15).returncode:
        raise ValueError('The selected Python cannot import the installed DSH SDK.')
    return python


def seed_database():
    from django.contrib.auth import get_user_model
    from rest_framework.authtoken.models import Token
    from ai_assistant.models import Bot
    from courses.models import Course, CourseModule
    from quizzes.models import KnowledgePoint, Question
    from users.models import CourseStudentStatus, WeeklyAIQuotaConfig
    Bot.objects.create(name='小宇', bot_type='planner', system_prompt='科晟小宇隔离合成预览。')
    for username in STUDENTS.values():
        user = get_user_model().objects.create_user(username=username, nickname='合成预览学生')
        CourseStudentStatus.objects.create(user=user, is_course_student=username == STUDENTS['student-b'])
        Token.objects.create(user=user)
    WeeklyAIQuotaConfig.objects.update_or_create(pk=1, defaults={'experience_calls': 20, 'course_calls': 200})
    kp = KnowledgePoint.objects.create(name='M0久期', code='M0-DURATION', subject='金融431')
    Course.objects.create(title='M0久期课程（合成样例）', description='隔离数据，不是正式课程。', knowledge_point=kp)
    public = CourseModule.objects.create(name='M0公开体验', subject='金融431', is_public=True)
    Course.objects.create(title='M0公开课（合成样例）', module=public, description='用于注册学生权限预览，不是正式课程。')
    Question.objects.create(knowledge_point=kp, q_type='objective',
        text='合成题：其他条件相同时，久期越长，债券价格对利率变动是否越敏感？',
        options=['越敏感', '越不敏感'], correct_answer='A')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', default='.m0-state/preview')
    parser.add_argument('--init', action='store_true', help='Initialize a new synthetic database; never replace an existing one')
    parser.add_argument('--model', choices=('fixture', 'deepseek'), default='fixture')
    parser.add_argument('--backend-env', type=Path, help='Read only the authorized DeepSeek model configuration')
    parser.add_argument('--sdk-python', type=Path, default=ROOT / '.m0-venv/bin/python')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    isolate_environment()
    state = preview_state(args.state_dir)
    database = state / 'db.sqlite3'
    existing = database.exists()
    if existing:
        check_database(state)
    elif not args.init:
        parser.error('A new preview requires --init; existing data are never replaced.')
    python = sdk_executable(args.sdk_python)
    if not 1 <= args.port <= 65535:
        parser.error('Invalid SDK Python or port.')
    model_url, key = '', 'local-protocol-fixture'
    if args.model == 'deepseek':
        from dotenv import dotenv_values
        if not args.backend_env or not args.backend_env.is_file():
            parser.error('--model deepseek requires an existing --backend-env file.')
        values = dotenv_values(args.backend_env, interpolate=False)
        if urlsplit(values.get('LLM_BASE_URL') or 'https://api.deepseek.com').hostname != 'api.deepseek.com' or not values.get('LLM_API_KEY'):
            parser.error('The selected configuration is not an authorized DeepSeek official source.')
        key = values['LLM_API_KEY']
    redis_program = shutil.which('redis-server')
    if not redis_program:
        parser.error('redis-server is required for the isolated preview.')
    os.umask(0o077)
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (state / '.preview.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error('This preview state is already in use.')
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            redis_port = probe.getsockname()[1]
        with (state / 'redis.log').open('a') as log:
            redis = subprocess.Popen([redis_program, '--bind', '127.0.0.1', '--port', str(redis_port),
                '--save', '', '--appendonly', 'no', '--maxmemory', '64mb', '--maxmemory-policy', 'noeviction', '--dir', str(state)],
                stdout=log, stderr=log, env={name: os.environ[name] for name in ('PATH', 'LANG') if name in os.environ})
            model = None
            try:
                for _ in range(50):
                    if redis.poll() is not None:
                        raise RuntimeError('Isolated Redis failed to start.')
                    with socket.socket() as probe:
                        if probe.connect_ex(('127.0.0.1', redis_port)) == 0:
                            break
                    time.sleep(.1)
                else:
                    raise RuntimeError('Isolated Redis is unavailable.')
                if args.model == 'fixture':
                    from smoke import model_fixture
                    model, _ = model_fixture()
                    model_url = f'http://127.0.0.1:{model.server_port}/v1/messages'
                os.environ.update(ACCOUNT_ENABLED='false', ACCOUNT_RSA_KEY_PATH='', ACCOUNT_DEV_LOCAL_CACHE='true',
                    DJANGO_ENV='development', DEBUG='true', DB_ENGINE='django.db.backends.sqlite3', DB_NAME=str(database),
                    ALLOWED_HOSTS='127.0.0.1,localhost', UNIMIND_CONTENT_INSTITUTION_ID='global',
                    UNIMIND_DSH_ENABLED='true', UNIMIND_DSH_SITE_ENABLED='true', UNIMIND_DSH_XIAOYU_ENABLED='true',
                    UNIMIND_DSH_TITLE_ENABLED='true', UNIMIND_DSH_MEMORY_ENABLED='true', UNIMIND_DSH_GRADING_ENABLED='true',
                    UNIMIND_DSH_TEACHING_ENABLED='true', UNIMIND_DSH_GENERATION_ENABLED='true',
                    UNIMIND_DSH_FIXTURE_URL=model_url, UNIMIND_DSH_PYTHON=python,
                    UNIMIND_DSH_STATE_DIR=str(state / 'sessions'), UNIMIND_DSH_API_URL=f'http://127.0.0.1:{args.port}',
                    REDIS_URL=f'redis://127.0.0.1:{redis_port}/0', CELERY_BROKER_URL='memory://', CELERY_RESULT_BACKEND='cache+memory://',
                    LLM_API_KEY=key, LLM_BASE_URL='https://api.deepseek.com/v1/chat/completions')
                sys.path.insert(0, str(ROOT / 'backend'))
                os.environ['DJANGO_SETTINGS_MODULE'] = 'school_system.settings'
                import django
                django.setup()
                from django.conf import settings
                from django.core.management import call_command
                settings.FEISHU_NOTIFY_PASSWORD = ''
                settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
                settings.MEDIA_ROOT = str(state / 'media')
                settings.MEDIA_URL = '/media/'
                settings.STORAGES = {
                    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
                }
                settings.DATABASES['default'].setdefault('OPTIONS', {}).update(timeout=20, transaction_mode='IMMEDIATE')
                settings.CHANNEL_LAYERS = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}
                settings.CELERY_TASK_ALWAYS_EAGER = True
                from school_system.celery import app
                app.conf.update(task_always_eager=True, broker_url='memory://', result_backend='cache+memory://')
                call_command('migrate', interactive=False, verbosity=0)
                if not existing:
                    seed_database()
                check_database(state)
                from rest_framework.authtoken.models import Token
                from school_system.asgi import application
                from daphne.server import Server
                tokens = {name: Token.objects.get(user__username=username).key for name, username in STUDENTS.items()}

                async def preview_application(scope, receive, send):
                    prefix = '/api/ai/dsh-preview/'
                    if scope['type'] == 'http' and scope['path'].startswith(prefix):
                        name = scope['path'][len(prefix):].strip('/')
                        if scope['method'] == 'GET' and name in tokens:
                            headers = [(b'location', b'/xiaoyu'), (b'cache-control', b'no-store'),
                                (b'set-cookie', f'auth_token={tokens[name]}; Path=/; HttpOnly; SameSite=Lax'.encode())]
                            await send({'type': 'http.response.start', 'status': 303, 'headers': headers})
                            await send({'type': 'http.response.body', 'body': b''})
                            return
                    await application(scope, receive, send)

                def ready():
                    info = {'model': 'deepseek-official' if args.model == 'deepseek' else 'local-protocol-smoke',
                            'redis_port': redis_port, 'port': args.port, 'tasks': 'eager-memory', 'data': 'synthetic',
                            'login_paths': [f'/api/ai/dsh-preview/{name}/' for name in STUDENTS]}
                    (state / 'runtime.json').write_text(json.dumps(info))
                    print(json.dumps(info), flush=True)
                Server(preview_application, endpoints=[f'tcp:port={args.port}:interface=127.0.0.1'], verbosity=0,
                       ready_callable=ready, action_logger=lambda *_args: None).run()
            finally:
                if model:
                    model.shutdown()
                    model.server_close()
                redis.terminate()
                redis.wait(timeout=5)


if __name__ == '__main__':
    main()
