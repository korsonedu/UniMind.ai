"""Actual DSH + actual Django, with a local deterministic model protocol fixture."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from tempfile import TemporaryDirectory, gettempdir


ROOT = Path(__file__).resolve().parent.parent


def official_config(python, env_path):
    # Parse with the existing backend dependency; the credential stays in a private pipe.
    source = """
import json, sys
from dotenv import dotenv_values
from urllib.parse import urlsplit
values = dotenv_values(sys.argv[1])
endpoint = values.get('LLM_BASE_URL') or 'https://api.deepseek.com/v1/chat/completions'
if urlsplit(endpoint).hostname != 'api.deepseek.com':
    raise SystemExit('Existing model source is not DeepSeek official')
key = values.get('LLM_API_KEY')
if not key:
    raise SystemExit('Existing official credential is missing')
print(json.dumps({'url': 'https://api.deepseek.com/anthropic/v1/messages', 'key': key, 'mode': 'deepseek-official'}))
"""
    return json.loads(subprocess.check_output([python, '-c', source, str(Path(env_path).resolve())], text=True))


def fixture_database():
    marker = os.environ.get('UNIMIND_M0_FIXTURE_DB', '')
    path = Path(marker).resolve() if marker else None
    if (path is None or path.name != 'db.sqlite3' or path.exists()
            or path.parent.parent != Path(gettempdir()).resolve()
            or not path.parent.name.startswith('unimind-m0-smoke-') or not path.parent.is_dir()):
        raise RuntimeError('An isolated fixture database created by the parent process is required')
    return str(path)


def backend_fixture():
    database = fixture_database()  # Refuse before Django setup or any database operation.
    os.environ.update({'DB_ENGINE': 'django.db.backends.sqlite3', 'DB_NAME': database,
                       'ACCOUNT_ENABLED': 'false', 'ACCOUNT_DEV_LOCAL_CACHE': 'true',
                       'UNIMIND_DSH_ENABLED': 'true', 'UNIMIND_CONTENT_INSTITUTION_ID': 'global',
                       'DJANGO_ENV': 'development', 'DEBUG': 'true'})
    from wsgiref.simple_server import make_server, WSGIRequestHandler
    sys.path.insert(0, str(ROOT / 'backend'))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school_system.settings')
    import django
    django.setup()
    from django.core.management import call_command
    call_command('migrate', interactive=False, verbosity=0)
    from django.contrib.auth import get_user_model
    from rest_framework.authtoken.models import Token
    from users.models import CourseStudentStatus
    from ai_assistant.models import AgentMemory
    from courses.models import Course
    user = get_user_model().objects.create_user(username='m0-student', nickname='M0 验证学生')
    other = get_user_model().objects.create_user(username='m0-other')
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    AgentMemory.objects.create(user=user, key='讲解偏好', value='先举例再给公式', source='manual')
    AgentMemory.objects.create(user=other, key='private', value='OTHER_STUDENT_PRIVATE', source='manual')
    Course.objects.create(title='M0 货币银行学样例', description='隔离数据，不是正式课程。')
    token = Token.objects.create(user=user)
    from django.core.wsgi import get_wsgi_application

    class Quiet(WSGIRequestHandler):
        def log_message(self, *_args):
            pass

    server = make_server('127.0.0.1', 0, get_wsgi_application(), handler_class=Quiet)
    print('READY ' + json.dumps({'port': server.server_port, 'token': token.key}), flush=True)
    server.serve_forever()


def model_fixture():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    requests = []

    class Model(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(body)
            has_result = any(block.get('type') == 'tool_result'
                             for m in body.get('messages', []) if isinstance(m.get('content'), list)
                             for block in m['content'])
            if has_result:
                block = {'type': 'text', 'text': ''}
                delta = {'type': 'text_delta', 'text': 'M0 协议冒烟：已读取本人学习统计，将按“先举例再给公式”的偏好解释。'}
                finish = 'end_turn'
            else:
                block = {'type': 'tool_use', 'id': 'm0-call', 'name': 'get_learning_stats', 'input': {}}
                delta = {'type': 'input_json_delta', 'partial_json': '{}'}
                finish = 'tool_use'
            events = [
                {'type': 'message_start', 'message': {'id': 'm0-response', 'type': 'message',
                 'role': 'assistant', 'content': [], 'model': 'deepseek-flash', 'stop_reason': None,
                 'stop_sequence': None, 'usage': {'input_tokens': 20, 'output_tokens': 0}}},
                {'type': 'content_block_start', 'index': 0, 'content_block': block},
                {'type': 'content_block_delta', 'index': 0, 'delta': delta},
                {'type': 'content_block_stop', 'index': 0},
                {'type': 'message_delta', 'delta': {'stop_reason': finish, 'stop_sequence': None}, 'usage': {'output_tokens': 10}},
                {'type': 'message_stop'},
            ]
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            for event in events:
                self.wfile.write((f'event: {event["type"]}\ndata: ' + json.dumps(event, ensure_ascii=False) + '\n\n').encode())

    server = ThreadingHTTPServer(('127.0.0.1', 0), Model)
    Thread(target=server.serve_forever, daemon=True).start()
    return server, requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--backend-fixture', action='store_true')
    parser.add_argument('--backend-python')
    parser.add_argument('--serve', action='store_true', help='Keep isolated fixtures and loopback Host alive for the React page')
    parser.add_argument('--official-env', help='Use the authorized DeepSeek official credential in this existing backend .env')
    args = parser.parse_args()
    if args.backend_fixture:
        return backend_fixture()
    if not args.backend_python:
        parser.error('--backend-python must point to the existing Django Python environment')

    def stop(_signal, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    with TemporaryDirectory(prefix='unimind-m0-smoke-') as state:
        env = {**os.environ, 'ACCOUNT_ENABLED': 'false', 'ACCOUNT_RSA_KEY_PATH': '',
               'ACCOUNT_DEV_LOCAL_CACHE': 'true', 'UNIMIND_DSH_ENABLED': 'true',
               'UNIMIND_CONTENT_INSTITUTION_ID': 'global', 'DB_ENGINE': 'django.db.backends.sqlite3',
               'UNIMIND_M0_FIXTURE_DB': str(Path(state) / 'db.sqlite3'), 'DB_NAME': str(Path(state) / 'db.sqlite3'),
               'ALLOWED_HOSTS': '127.0.0.1,localhost', 'DJANGO_ENV': 'development'}
        backend = subprocess.Popen([args.backend_python, __file__, '--backend-fixture'],
                                   env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        model = None
        try:
            while True:
                line = backend.stdout.readline()
                if not line:
                    raise RuntimeError('Isolated Django fixture failed to start: ' + backend.stderr.read()[-4000:])
                if line.startswith('READY '):
                    identity = json.loads(line[6:])
                    break
            model, calls = model_fixture()
            os.environ.update({
                'UNIMIND_API_URL': f'http://127.0.0.1:{identity["port"]}',
                'UNIMIND_AUTH_TOKEN': identity['token'],
                'UNIMIND_DSH_MODEL_URL': f'http://127.0.0.1:{model.server_port}/v1',
            })
            from host import run_turn
            config = official_config(args.backend_python, args.official_env) if args.official_env else None
            result = run_turn('请调用工具查询我的实际学习统计，再按我的讲解偏好用三句话解释。没有学习记录时说明暂无记录，不要编造。', config)
            assert result['content']
            if config:
                assert any(r['tool_results'] for r in result['gateway']['requests']), 'Official model did not return a tool result'
                assert all(r['usage_complete'] for r in result['gateway']['requests']), 'Official usage is incomplete'
                print(json.dumps({'runtime': 'actual-dsh-sdk', 'backend': 'actual-django-isolated-sqlite',
                                  'model': 'deepseek-official', 'gateway': result['gateway'],
                                  'content': result['content']}, ensure_ascii=False), flush=True)
            else:
                assert len(calls) == 2, f'Expected one tool round; got {len(calls)} model requests'
                first = json.dumps(calls[0], ensure_ascii=False)
                assert '先举例再给公式' in first
                assert 'OTHER_STUDENT_PRIVATE' not in first
                names = {t['name'] for t in calls[0].get('tools', [])}
                assert names and names <= {'get_learning_stats', 'get_recent_practice_result', 'get_user_weak_points', 'search_courses', 'search_asr'}, names
                tool_results = [b for m in calls[1]['messages'] if isinstance(m.get('content'), list)
                                for b in m['content'] if b.get('type') == 'tool_result']
                assert tool_results and 'attempted_questions' in json.dumps(tool_results)
                print(json.dumps({'runtime': 'actual-dsh-sdk', 'model': 'local-deterministic-protocol-fixture',
                                  'backend': 'actual-django-isolated-sqlite', 'model_requests': len(calls),
                                  'tools': sorted(names), 'memory_isolated': True,
                                  'tool_result_received': True, 'gateway': result['gateway'],
                                  'content': result['content']}, ensure_ascii=False), flush=True)
            if args.serve:
                from http.server import ThreadingHTTPServer
                from host import Handler
                Handler.model_config = config
                print('M0 Host ready: http://127.0.0.1:8791; all student data are temporary fixtures.', flush=True)
                ThreadingHTTPServer(('127.0.0.1', 8791), Handler).serve_forever()
        finally:
            backend.terminate()
            backend.wait(timeout=10)
            if model:
                model.shutdown()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
