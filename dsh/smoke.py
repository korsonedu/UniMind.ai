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
    from wsgiref.simple_server import make_server, WSGIRequestHandler, WSGIServer
    from socketserver import ThreadingMixIn
    sys.path.insert(0, str(ROOT / 'backend'))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school_system.settings')
    import django
    django.setup()
    from django.core.management import call_command
    call_command('migrate', interactive=False, verbosity=0)
    from django.contrib.auth import get_user_model
    from rest_framework.authtoken.models import Token
    from users.models import CourseStudentStatus
    from ai_assistant.models import AgentMemory, Bot
    from courses.models import Course
    from courses.models import VideoTranscript, TranscriptSegment
    from quizzes.models import KnowledgePoint, Question, UserQuestionStatus, UserKnowledgeState, QuizExam, ExamQuestionResult
    from users.models import LearningSession
    from django.utils import timezone
    from datetime import timedelta
    from uuid import uuid4
    Bot.objects.create(name='小宇', bot_type='planner', system_prompt='科晟小宇隔离合成验证。')
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
    from study_room.models import StudySession
    from study_room import session_manager
    # Only this guarded temporary fixture substitutes an absent current Redis snapshot.
    session_manager.get_session = lambda user_id: None
    StudySession.objects.create(user=user, status='ended', ended_at=timezone.now(), total_focus_seconds=1500)
    StudySession.objects.create(user=other, status='ended', ended_at=timezone.now(), total_focus_seconds=5940, task_name='OTHER_PRIVATE_FOCUS')
    now = timezone.now()
    UserQuestionStatus.objects.filter(pk=status.pk).update(next_review_at=now-timedelta(days=1))
    UserKnowledgeState.objects.create(user=user, knowledge_point=kp, mastery_score=40)
    LearningSession.objects.create(user=user, session_id=uuid4(), kind='video', course=course,
        started_at=now-timedelta(minutes=20), ended_at=now, active_seconds=1200)
    exam = QuizExam.objects.create(user=user, status='completed', total_score=8, max_score=10,
        total_questions=1, graded_count=1, summary='合成练习结果，仅供链路验证。')
    ExamQuestionResult.objects.create(exam=exam, question=question, user_answer='A', score=8,
        max_score=10, is_correct=True, status='graded')
    QuizExam.objects.create(user=user, status='grading', total_questions=2, graded_count=0)
    token = Token.objects.create(user=user)
    other_token = Token.objects.create(user=other)
    from django.conf import settings
    if settings.UNIMIND_DSH_SITE_ENABLED:
        from users.models import WeeklyAIQuotaConfig
        WeeklyAIQuotaConfig.objects.update_or_create(pk=1, defaults={'experience_calls': 20, 'course_calls': 200})
        CourseStudentStatus.objects.create(user=other, is_course_student=True)
        if settings.UNIMIND_DSH_GRADING_ENABLED:
            grading_kp = KnowledgePoint.objects.create(name='M0主观评阅', code='M0-GRADING', subject='金融431')
            Question.objects.create(knowledge_point=grading_kp, q_type='subjective', subjective_type='short',
                text='合成主观题：解释久期对债券利率风险的含义。', grading_points='解释敏感程度5分；说明方向5分。',
                correct_answer='久期衡量价格对利率的敏感程度，久期越长越敏感。')
            objective_kp = KnowledgePoint.objects.create(name='M0客观评阅', code='M0-GRADING-OBJECTIVE', subject='金融431')
            Question.objects.create(knowledge_point=objective_kp, q_type='objective', text='合成客观题：久期越长越敏感？',
                options=['是', '否'], correct_answer='A')
    from django.core.wsgi import get_wsgi_application

    class Quiet(WSGIRequestHandler):
        def log_message(self, *_args):
            pass

    class ThreadedServer(ThreadingMixIn, WSGIServer):
        daemon_threads = True

    application = get_wsgi_application()
    if settings.UNIMIND_DSH_SITE_ENABLED:
        import socket
        from asgiref.sync import sync_to_async
        from django.core.asgi import get_asgi_application
        from daphne.server import Server
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(('127.0.0.1', int(os.environ.get('UNIMIND_M0_FIXTURE_PORT', '0'))))
            port = probe.getsockname()[1]
        settings.UNIMIND_DSH_API_URL = f'http://127.0.0.1:{port}'
        asgi = get_asgi_application()
        drop_next_chat = [False]
        async def browser_fixture(scope, receive, send):
            path = scope.get('path', '')
            identities = {'/api/ai/dsh-fixture/student-a/': user, '/api/ai/dsh-fixture/student-b/': other}
            if path == '/api/ai/dsh-fixture/drop-next-chat/':
                drop_next_chat[0] = True
                await send({'type': 'http.response.start', 'status': 200, 'headers': [(b'content-type', b'application/json')]})
                await send({'type': 'http.response.body', 'body': b'{"next_chat_response":"will_be_dropped_after_completion"}'})
                return
            if path in (*identities, '/api/ai/dsh-fixture/logout/'):
                # Only reachable after fixture_database() validates a newly created temporary DB.
                value = await sync_to_async(lambda: Token.objects.get_or_create(user=identities[path])[0].key)() if path in identities else ''
                cookie = f'auth_token={value}; HttpOnly; SameSite=Lax; Path=/' + ('; Max-Age=0' if not value else '')
                await send({'type': 'http.response.start', 'status': 302, 'headers': [(b'location', b'/dev/dsh?source=site'), (b'set-cookie', cookie.encode())]})
                await send({'type': 'http.response.body', 'body': b''})
                return
            if path in ('/api/ai/dsh/chat/', '/api/ai/dsh/chat/stream/') and drop_next_chat[0]:
                drop_next_chat[0] = False
                async def discard(_message):
                    pass
                await asgi(scope, receive, discard)
                await send({'type': 'http.response.start', 'status': 503, 'headers': [(b'content-type', b'application/json')]})
                await send({'type': 'http.response.body', 'body': b'{"error":"Synthetic delivery failure after server completion"}'})
                return
            await asgi(scope, receive, send)
        def ready():
            print('READY ' + json.dumps({'port': port, 'token': token.key, 'other_token': other_token.key}), flush=True)
        Server(browser_fixture, endpoints=[f'tcp:port={port}:interface=127.0.0.1'], ready_callable=ready,
               verbosity=0, action_logger=lambda *_args: None).run()
        return
    server = make_server('127.0.0.1', 0, application, server_class=ThreadedServer, handler_class=Quiet)
    settings.UNIMIND_DSH_API_URL = f'http://127.0.0.1:{server.server_port}'
    print('READY ' + json.dumps({'port': server.server_port, 'token': token.key, 'other_token': other_token.key}), flush=True)
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
            response_status = getattr(self.server, 'response_status', status)
            if response_status != 200:
                self.send_response(response_status)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"type":"error","error":{"type":"fixture_error","message":"unavailable"}}')
                return
            has_result = any(block.get('type') == 'tool_result'
                             for m in body.get('messages', [])[-1:] if isinstance(m.get('content'), list)
                             for block in m['content'])
            latest = body.get('messages', [])[-1].get('content', '') if body.get('messages') else ''
            prompt = next((m.get('content', '') for m in reversed(body.get('messages', []))
                if m.get('role') == 'user' and not (isinstance(m.get('content'), list)
                    and any(b.get('type') == 'tool_result' for b in m['content']))), '')
            prompt = json.dumps(prompt, ensure_ascii=False)
            demo = 'M0只读演示：学习统计。' in prompt
            discovered = ''
            if has_result:
                for result in latest:
                    content = result.get('content', '')
                    if isinstance(content, list):
                        content = ''.join(b.get('text', '') for b in content if b.get('type') == 'text')
                    try:
                        value = json.loads(content)
                    except (ValueError, TypeError):
                        continue
                    if isinstance(value, dict) and value.get('group'):
                        discovered = value['group']
            tools = None
            collectors = {tool.get('name') for tool in body.get('tools', [])}
            if 'submit_grading_result' in collectors:
                tools = [('submit_grading_result', {'score': 8, 'feedback': '合成评分：方向正确，补充敏感度解释。',
                    'analysis': '合成示范：久期越长，对利率变化越敏感。', 'memorix_rating': 3, 'error_analysis': None})]
            elif 'submit_objective_analysis' in collectors:
                tools = [('submit_objective_analysis', {'why_correct': '合成解释：选项A符合定义。',
                    'why_wrong': '合成提醒：请核对敏感度方向。', 'pitfalls': '区分方向和程度。'})]
            elif 'submit_questions' in collectors:
                tools = [('submit_questions', {'questions': [{'question': '合成录入题：久期反映什么？',
                    'q_type': 'subjective', 'subjective_type': 'short', 'options': None,
                    'answer': '合成答案：债券价格对利率变化的敏感度。',
                    'grading_points': ['利率敏感度'], 'difficulty_level': 'normal'}]})]
            elif 'submit_title' in collectors:
                tools = [('submit_title', {'title': '合成学习概览'})]
            elif 'submit_memories' in collectors:
                tools = [('submit_memories', {'memories': [{'memory_type': 'preference', 'key': '讲解顺序',
                    'value': '喜欢先举例', 'confidence': .9, 'evidence': '我喜欢先举例'}]})]
            elif demo:
                if not has_result:
                    tools = [('find_learning_tools', {'group': 'resources'}), ('get_learning_stats', {}),
                             ('get_recent_practice_result', {'exam_id': 1}), ('get_knowledge_mastery_map', {})]
                elif discovered == 'resources':
                    tools = [('find_learning_tools', {'group': 'practice'}),
                             ('search_courses', {'query': 'M0久期'}), ('search_asr', {'query': '久期'})]
                elif discovered == 'practice':
                    tools = [('get_user_wrong_questions', {}), ('get_practice_questions', {'kp_name': 'M0久期', 'limit': 2}),
                             ('get_due_reviews', {})]
            elif 'M0工具发现' in prompt:
                if not has_result:
                    tools = [('find_learning_tools', {'group': 'resources'})]
                elif discovered == 'resources':
                    tools = [('search_courses', {'query': 'M0久期'})]
            elif 'M0专注迁移' in prompt:
                if not has_result:
                    tools = [('get_study_status', {}), ('get_focus_history', {'days': 7})]
            elif not has_result:
                tools = [('get_recent_practice_result', {})] if 'M0批改快照' in prompt else [('get_learning_stats', {})]
                if tools[0][0] not in {t['name'] for t in body.get('tools', [])}:
                    tools = [('find_learning_tools', {'group': 'progress'})]
            elif discovered == 'progress':
                tools = [('get_learning_stats', {})]
            if tools is None:
                blocks = [({'type': 'text', 'text': ''}, {'type': 'text_delta',
                    'text': '本地协议模拟已完成工具往返；下方卡片来自隔离 Django 数据库的合成数据，不代表真实模型的判断。'})]
                finish = 'end_turn'
            else:
                blocks = [({'type': 'tool_use', 'id': f'm0-call-{len(requests)}-{index}', 'name': name, 'input': {}},
                    {'type': 'input_json_delta', 'partial_json': json.dumps(arguments)})
                    for index, (name, arguments) in enumerate(tools)]
                finish = 'tool_use'
            events = [
                {'type': 'message_start', 'message': {'id': 'm0-response', 'type': 'message',
                 'role': 'assistant', 'content': [], 'model': 'deepseek-flash', 'stop_reason': None,
                 'stop_sequence': None, 'usage': {'input_tokens': 20, 'output_tokens': 0}}},
            ]
            for index, (block, delta) in enumerate(blocks):
                events.append({'type': 'content_block_start', 'index': index, 'content_block': block})
                fragments = [delta]
                if delta.get('type') == 'text_delta' and getattr(self.server, 'stream_delay', 0):
                    text = delta['text']
                    fragments = [{**delta, 'text': text[offset:offset + 10]} for offset in range(0, len(text), 10)]
                events.extend({'type': 'content_block_delta', 'index': index, 'delta': fragment} for fragment in fragments)
                events.append({'type': 'content_block_stop', 'index': index})
            events += [
                {'type': 'message_delta', 'delta': {'stop_reason': finish, 'stop_sequence': None}, 'usage': {'output_tokens': 10}},
                {'type': 'message_stop'},
            ]
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            for event in events:
                self.wfile.write((f'event: {event["type"]}\ndata: ' + json.dumps(event, ensure_ascii=False) + '\n\n').encode())
                self.wfile.flush()
                if event.get('delta', {}).get('type') == 'text_delta' and getattr(self.server, 'stream_delay', 0):
                    from threading import Event
                    Event().wait(self.server.stream_delay)

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
                demo = run_turn('M0只读演示：学习统计。')
                cards = demo['session']['messages'][-1]['cards']
                assert len(cards) == 8, [(c['tool'], c['type']) for c in cards]
                assert len(demo['gateway']['requests']) == 4
                assert all(r['tool_count'] <= 8 for r in demo['gateway']['requests'])
                previews = [c for c in cards if c['tool'] == 'get_practice_questions']
                assert previews[0]['type'] == 'question_preview' and 'answer' not in json.dumps(previews[0]['payload'])
                assert any(c['type'] == 'practice_result' and c['payload']['total_score'] == 8 for c in cards)
                print(json.dumps({'readonly_cards': len(cards), 'card_types': sorted({c['type'] for c in cards}),
                    'practice_preview_without_answer': True, 'business_card_source': 'actual-django-synthetic-data'}, ensure_ascii=False), flush=True)
                start = len(calls)
                discovered = run_turn('M0工具发现')
                assert len(calls) - start == 3
                assert {t['name'] for t in calls[start]['tools']} == {'find_learning_tools'}
                assert {t['name'] for t in calls[start+1]['tools']} == {'find_learning_tools', 'search_courses', 'search_asr', 'search_knowledge_tree'}
                assert discovered['session']['messages'][-1]['cards'][0]['tool'] == 'search_courses'
                print(json.dumps({'native_group_discovery': True, 'model_requests': 3,
                    'max_visible_tools': max(r['tool_count'] for r in discovered['gateway']['requests']),
                    'selected_calls': discovered['routing']['selected_calls']}, ensure_ascii=False), flush=True)
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
