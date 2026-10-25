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
    from courses.models import VideoTranscript, TranscriptSegment
    from quizzes.models import KnowledgePoint, Question, UserQuestionStatus, UserKnowledgeState, QuizExam, ExamQuestionResult
    from users.models import LearningSession
    from django.utils import timezone
    from datetime import timedelta
    from uuid import uuid4
    user = get_user_model().objects.create_user(username='m0-student', nickname='M0 验证学生')
    other = get_user_model().objects.create_user(username='m0-other')
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    AgentMemory.objects.create(user=user, key='讲解偏好', value='先举例再给公式', source='manual')
    AgentMemory.objects.create(user=other, key='private', value='OTHER_STUDENT_PRIVATE', source='manual')
    kp = KnowledgePoint.objects.create(name='M0久期', code='M0-DURATION', subject='金融431')
    course = Course.objects.create(title='M0久期课程（合成样例）', description='隔离数据，不是正式课程。', knowledge_point=kp)
    transcript = VideoTranscript.objects.create(course=course, asr_status='completed')
    TranscriptSegment.objects.create(transcript=transcript, start_time=60, end_time=90,
        text='合成讲稿：久期反映债券价格对利率变化的敏感程度。', index=0)
    question = Question.objects.create(knowledge_point=kp, q_type='single_choice',
        text='合成题：其他条件相同时，久期越长，债券价格对利率变动是否越敏感？',
        options=['越敏感', '越不敏感'], correct_answer='A')
    status = UserQuestionStatus.objects.create(user=user, question=question, wrong_count=2,
        reps=3, difficulty=7, stability=2)
    now = timezone.now()
    UserQuestionStatus.objects.filter(pk=status.pk).update(next_review_at=now-timedelta(days=1))
    UserKnowledgeState.objects.create(user=user, knowledge_point=kp, mastery_score=40)
    LearningSession.objects.create(user=user, session_id=uuid4(), kind='video', course=course,
        started_at=now-timedelta(minutes=20), ended_at=now, active_seconds=1200)
    exam = QuizExam.objects.create(user=user, status='completed', total_score=8, max_score=10,
        total_questions=1, graded_count=1, summary='合成练习结果，仅供链路验证。')
    ExamQuestionResult.objects.create(exam=exam, question=question, user_answer='A', score=8,
        max_score=10, is_correct=True, status='graded')
    token = Token.objects.create(user=user)
    from django.core.wsgi import get_wsgi_application

    class Quiet(WSGIRequestHandler):
        def log_message(self, *_args):
            pass

    server = make_server('127.0.0.1', 0, get_wsgi_application(), handler_class=Quiet)
    print('READY ' + json.dumps({'port': server.server_port, 'token': token.key}), flush=True)
    server.serve_forever()


def model_fixture(status=200):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    requests = []

    class Model(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(body)
            if status != 200:
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"type":"error","error":{"type":"fixture_error","message":"unavailable"}}')
                return
            has_result = any(block.get('type') == 'tool_result'
                             for m in body.get('messages', [])[-1:] if isinstance(m.get('content'), list)
                             for block in m['content'])
            latest = body.get('messages', [])[-1].get('content', '')
            demo = 'M0只读演示' in json.dumps(latest, ensure_ascii=False)
            if has_result:
                blocks = [({'type': 'text', 'text': ''}, {'type': 'text_delta',
                    'text': '本地协议模拟已完成工具往返；下方卡片来自隔离 Django 数据库的合成数据，不代表真实模型的判断。'})]
                finish = 'end_turn'
            else:
                tools = [('get_learning_stats', {})]
                if demo:
                    tools += [('get_recent_practice_result', {}), ('get_due_reviews', {}),
                              ('search_courses', {'query': 'M0久期'}), ('search_asr', {'query': '久期'}),
                              ('get_user_wrong_questions', {}), ('get_practice_questions', {'kp_name': 'M0久期', 'limit': 2}),
                              ('get_knowledge_mastery_map', {})]
                blocks = [({'type': 'tool_use', 'id': f'm0-call-{index}', 'name': name, 'input': {}},
                    {'type': 'input_json_delta', 'partial_json': json.dumps(arguments)})
                    for index, (name, arguments) in enumerate(tools)]
                finish = 'tool_use'
            events = [
                {'type': 'message_start', 'message': {'id': 'm0-response', 'type': 'message',
                 'role': 'assistant', 'content': [], 'model': 'deepseek-flash', 'stop_reason': None,
                 'stop_sequence': None, 'usage': {'input_tokens': 20, 'output_tokens': 0}}},
            ]
            for index, (block, delta) in enumerate(blocks):
                events.extend([
                    {'type': 'content_block_start', 'index': index, 'content_block': block},
                    {'type': 'content_block_delta', 'index': index, 'delta': delta},
                    {'type': 'content_block_stop', 'index': index},
                ])
            events += [
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
            import host
            from sessions import SessionStore
            host.SESSIONS = SessionStore(Path(state) / 'sessions')
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
                expected = host.backend_request('/api/ai/dsh/context/', {'message': '请调用工具查询我的实际学习统计，再按我的讲解偏好用三句话解释。没有学习记录时说明暂无记录，不要编造。'})
                assert names == {t['function']['name'] for t in expected['tools']}, names
                assert [c['type'] for c in result['session']['messages'][-1]['cards']] == ['data_card']
                tool_results = [b for m in calls[1]['messages'] if isinstance(m.get('content'), list)
                                for b in m['content'] if b.get('type') == 'tool_result']
                assert tool_results and 'attempted_questions' in json.dumps(tool_results)
                assert 'visual' not in json.dumps(tool_results), 'UI card leaked into model content'
                print(json.dumps({'runtime': 'actual-dsh-sdk', 'model': 'local-deterministic-protocol-fixture',
                                  'backend': 'actual-django-isolated-sqlite', 'model_requests': len(calls),
                                  'tools': sorted(names), 'memory_isolated': True,
                                  'tool_result_received': True, 'gateway': result['gateway'],
                                  'content': result['content']}, ensure_ascii=False), flush=True)
                # Restart the Host interpreter as well as DSH; only the local files survive.
                restore = """
import json, sys
import host
from sessions import SessionStore
host.SESSIONS = SessionStore(sys.argv[1])
print(json.dumps(host.run_turn(**json.load(sys.stdin)), ensure_ascii=False))
"""
                resumed = json.loads(subprocess.check_output([sys.executable, '-c', restore, str(Path(state) / 'sessions')],
                    cwd=str(ROOT / 'dsh'), input=json.dumps({'message': '接着解释上一轮的结果。', 'session_id': result['session_id']}),
                    text=True, stderr=subprocess.PIPE))
                history = json.dumps(calls[2]['messages'], ensure_ascii=False)
                assert '没有学习记录时说明暂无记录' in history and result['content'] in history
                assert resumed['session_id'] == result['session_id'] and len(resumed['session']['messages']) == 4
                assert resumed['session']['messages'][1]['cards'] == result['session']['messages'][1]['cards']
                print(json.dumps({'native_session_restored': True, 'visible_messages': 4, 'sdk_processes': 2, 'host_processes': 2}), flush=True)
                from urllib.request import Request, urlopen
                memory_id = host.backend_request('/api/ai/dsh/context/', {})['memory']['items'][0]['id']
                memory_url = os.environ['UNIMIND_API_URL'] + f'/api/ai/memories/{memory_id}/'
                def change_memory(method, body=None):
                    request = Request(memory_url, json.dumps(body).encode() if body is not None else None,
                                      {'Authorization': 'Token ' + identity['token'], 'Content-Type': 'application/json'}, method=method)
                    with urlopen(request, timeout=5) as response:
                        assert response.status in (200, 204)
                start = len(calls)
                change_memory('PATCH', {'value': '先给定义再用数字例子'})
                corrected = run_turn('请查询学习统计。', session_id=result['session_id'])
                fresh = json.dumps(calls[start], ensure_ascii=False)
                assert '先给定义再用数字例子' in fresh and '先举例再给公式' not in fresh
                assert '没有学习记录时说明暂无记录' not in fresh
                assert len(corrected['session']['messages']) == 6 and corrected['session']['notice']
                start = len(calls)
                change_memory('DELETE')
                deleted = run_turn('请查询学习统计。', session_id=result['session_id'])
                fresh = json.dumps(calls[start], ensure_ascii=False)
                assert '先给定义再用数字例子' not in fresh and '先举例再给公式' not in fresh
                assert len(deleted['session']['messages']) == 8
                print(json.dumps({'memory_correction_rebuilt_context': True, 'memory_deletion_rebuilt_context': True,
                                  'original_transcript_retained': True}), flush=True)
                demo = run_turn('M0只读演示：查询学习统计、最近练习、到期复习、课程讲稿、错题、题库预览和掌握图谱。')
                cards = demo['session']['messages'][-1]['cards']
                assert len(cards) == 8, [(c['tool'], c['type']) for c in cards]
                previews = [c for c in cards if c['tool'] == 'get_practice_questions']
                assert previews[0]['type'] == 'question_preview' and 'answer' not in json.dumps(previews[0]['payload'])
                assert any(c['type'] == 'practice_result' and c['payload']['total_score'] == 8 for c in cards)
                print(json.dumps({'readonly_cards': len(cards), 'card_types': sorted({c['type'] for c in cards}),
                    'practice_preview_without_answer': True, 'business_card_source': 'actual-django-synthetic-data'}, ensure_ascii=False), flush=True)
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
