"""Actual site identity/quota → isolated worker → actual DSH → Django callbacks."""
import argparse
from contextlib import ExitStack
import fcntl
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from smoke import ROOT, model_fixture


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--backend-python', required=True)
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    model, calls = model_fixture()
    model.stream_delay = 0.15
    with TemporaryDirectory(prefix='unimind-m0-smoke-') as state:
        env = {**os.environ, 'ACCOUNT_ENABLED': 'false', 'ACCOUNT_RSA_KEY_PATH': '',
               'ACCOUNT_DEV_LOCAL_CACHE': 'true', 'UNIMIND_DSH_ENABLED': 'true',
               'UNIMIND_DSH_SITE_ENABLED': 'true', 'UNIMIND_DSH_GRADING_ENABLED': 'true', 'UNIMIND_DSH_PYTHON': sys.executable,
               'UNIMIND_DSH_STATE_DIR': str(Path(state) / 'sessions'),
               'UNIMIND_DSH_FIXTURE_URL': f'http://127.0.0.1:{model.server_port}/v1/messages',
               'UNIMIND_CONTENT_INSTITUTION_ID': 'global', 'DB_ENGINE': 'django.db.backends.sqlite3',
               'UNIMIND_M0_FIXTURE_DB': str(Path(state) / 'db.sqlite3'), 'DB_NAME': str(Path(state) / 'db.sqlite3'),
               'ALLOWED_HOSTS': '127.0.0.1,localhost', 'DJANGO_ENV': 'development',
               'UNIMIND_M0_FIXTURE_PORT': str(args.port)}
        diagnostics = open(Path(state) / 'backend.log', 'w+')
        backend = subprocess.Popen([args.backend_python, str(ROOT / 'dsh' / 'smoke.py'), '--backend-fixture'],
            env=env, stdout=subprocess.PIPE, stderr=diagnostics, text=True)
        try:
            while True:
                line = backend.stdout.readline()
                if not line:
                    raise RuntimeError('Isolated site fixture failed to start')
                if line.startswith('READY '):
                    identity = json.loads(line[6:])
                    break
            base = f'http://127.0.0.1:{identity["port"]}'

            def request(token, path, body):
                req = Request(base + (path if path.startswith('/api/') else '/api/ai/dsh/' + path + '/'), None if body is None else json.dumps(body).encode(),
                    {'Content-Type': 'application/json', 'Authorization': 'Token ' + token})
                try:
                    with urlopen(req, timeout=130) as response:
                        return response.status, json.load(response)
                except HTTPError as exc:
                    with exc:
                        try:
                            return exc.code, json.load(exc)
                        except ValueError:
                            return exc.code, {'error': 'non_json_error'}

            def request_stream(token, body):
                from time import monotonic
                req = Request(base + '/api/ai/dsh/chat/stream/', json.dumps(body).encode(),
                    {'Content-Type': 'application/json', 'Authorization': 'Token ' + token})
                events, times = [], []
                with urlopen(req, timeout=130) as response:
                    assert 'text/event-stream' in response.headers['Content-Type']
                    for line in response:
                        if line.startswith(b'data: '):
                            events.append(json.loads(line[6:]))
                            times.append(monotonic())
                return events, times

            a = {'message': '查询学习统计，临时代号 SITE_A_42。', 'request_id': str(uuid4())}
            b = {'message': '查询学习统计，临时代号 SITE_B_86。', 'request_id': str(uuid4())}
            with ExitStack() as locks:
                slots = Path(state) / 'sessions' / '.slots'
                slots.mkdir(parents=True, exist_ok=True)
                for index in range(4):
                    lock = locks.enter_context(open(slots / str(index), 'a'))
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                status, _ = request(identity['token'], 'chat', {'message': '查询学习统计', 'request_id': str(uuid4())})
                assert status == 503 and not calls
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(request, identity['token'], 'chat', a)
                second = pool.submit(request, identity['other_token'], 'chat', b)
                status_a, result_a = first.result()
                status_b, result_b = second.result()
            assert status_a == status_b == 200, (status_a, result_a, status_b, result_b)
            assert result_a['session_id'] != result_b['session_id']
            for call in calls:
                body = json.dumps(call, ensure_ascii=False)
                assert not ('先举例再给公式' in body and 'OTHER_STUDENT_PRIVATE' in body)
                assert not ('SITE_A_42' in body and 'SITE_B_86' in body)
            count = len(calls)
            sessions_a = request(identity['token'], 'sessions', None)[1]['sessions']
            sessions_b = request(identity['other_token'], 'sessions', None)[1]['sessions']
            assert {row['id'] for row in sessions_a} == {result_a['session_id']}
            assert {row['id'] for row in sessions_b} == {result_b['session_id']}
            assert 'SITE_B_86' not in json.dumps(sessions_a, ensure_ascii=False)
            assert len(calls) == count
            assert request(identity['token'], 'chat', a) == (200, result_a)
            assert len(calls) == count
            sid = result_a['session_id']
            assert request(identity['other_token'], 'session/read', {'session_id': sid})[0] == 404
            assert request(identity['other_token'], 'session/delete', {'session_id': sid})[0] == 404
            assert request(identity['token'], 'session/read', {'session_id': sid})[0] == 200
            start = len(calls)
            status, resumed = request(identity['token'], 'chat', {'message': '继续查询学习统计。',
                'request_id': str(uuid4()), 'session_id': sid})
            assert status == 200 and resumed['session_id'] == sid, (status, resumed)
            assert len(resumed['session']['messages']) == 4
            assert 'SITE_A_42' in json.dumps(calls[start]['messages'], ensure_ascii=False)
            assert 'SITE_B_86' not in json.dumps(calls[start]['messages'], ensure_ascii=False)
            assert request(identity['token'], 'session/delete', {'session_id': sid}) == (200, {'deleted': True})
            assert not list((Path(state) / 'sessions').rglob(f'{sid}/transcript.json'))
            assert request(identity['token'], 'chat', a)[0] == 410
            assert request(identity['token'], 'sessions', None)[1]['sessions'] == []
            assert request(identity['other_token'], 'session/read', {'session_id': result_b['session_id']})[0] == 200
            streaming = {'message': '查询学习统计，流式验证。', 'request_id': str(uuid4())}
            events, times = request_stream(identity['token'], streaming)
            assert events[-1]['type'] == 'done', events
            result_stream = events[-1]['result']
            first_text = next(index for index, event in enumerate(events) if event['type'] == 'text_delta')
            assert sum(event['type'] == 'text_delta' for event in events) >= 3
            assert times[-1] - times[first_text] >= 0.2, 'ASGI must deliver provisional text before task settlement'
            assert ''.join(event['text'] for event in events if event['type'] == 'text_delta') == result_stream['content']
            assert any(event['type'] == 'tool_status' for event in events)
            assert result_stream['session']['messages'][-1]['cards']
            count = len(calls)
            assert request(identity['token'], 'chat', streaming) == (200, result_stream)
            assert len(calls) == count
            status, practice = request(identity['token'], '/api/ai/practice/start/', {'kp_name': 'M0主观评阅', 'count': 1})
            assert status == 200 and practice['questions'], (status, practice)
            read_url = f'/api/ai/practice/session/{practice["session_id"]}/'
            assert request(identity['token'], read_url, None)[1]['questions'] == practice['questions']
            assert request(identity['other_token'], read_url, None)[0] == 403
            practice_body = {'session_id': practice['session_id'], 'answers': [
                {'question_id': practice['questions'][0]['id'], 'answer': '久期越长，价格对利率变化越敏感。'}]}
            assert request(identity['other_token'], '/api/ai/practice/submit/', practice_body)[0] == 403
            count = len(calls)
            status, grade = request(identity['token'], '/api/ai/practice/submit/', practice_body)
            assert status == 200 and grade['total_score'] == 8, (status, grade)
            assert len(calls) == count + 1, 'native concludeTurn must end after one collector call'
            assert calls[-1]['model'] == 'deepseek-v4-pro' and calls[-1]['temperature'] == 0.2
            assert [tool['name'] for tool in calls[-1]['tools']] == ['submit_grading_result']
            assert 'OTHER_STUDENT_PRIVATE' not in json.dumps(calls[-1], ensure_ascii=False)
            assert request(identity['token'], '/api/ai/practice/submit/', practice_body) == (200, grade)
            assert len(calls) == count + 1
            assert request(identity['token'], read_url, None)[1]['result'] == grade
            status, objective = request(identity['token'], '/api/ai/practice/start/', {'kp_name': 'M0客观评阅', 'count': 1})
            assert status == 200, (status, objective)
            status, objective_grade = request(identity['token'], '/api/ai/grading/grade/', {
                'question_id': objective['questions'][0]['id'], 'user_answer': 'B'})
            assert status == 200 and objective_grade['score'] == 0, (status, objective_grade)
            assert [tool['name'] for tool in calls[-1]['tools']] == ['submit_objective_analysis']
            status, failed_practice = request(identity['token'], '/api/ai/practice/start/', {'kp_name': 'M0主观评阅', 'count': 1})
            assert status == 200, (status, failed_practice)
            model.response_status = 503
            failed_grade_calls = len(calls)
            status, _ = request(identity['token'], '/api/ai/practice/submit/', {
                **practice_body, 'session_id': failed_practice['session_id']})
            assert status == 503
            assert len(calls) == failed_grade_calls + 1, 'grading must not retry transient provider failures'
            model.response_status = 422
            files = set((Path(state) / 'sessions').rglob('transcript.json'))
            failed = {'message': '查询学习统计。', 'request_id': str(uuid4())}
            failed_events, _ = request_stream(identity['token'], failed)
            assert failed_events[-1]['type'] == 'error' and failed_events[-1]['status'] == 503
            assert not any(event['type'] == 'done' for event in failed_events)
            assert set((Path(state) / 'sessions').rglob('transcript.json')) == files
            source = """
import json, os, sys
sys.path.insert(0, sys.argv[1])
os.environ.setdefault('DJANGO_SETTINGS_MODULE','school_system.settings')
import django
django.setup()
from users.models import WeeklyAIUsage, AIUsageReservation
from quizzes.models import GradingRecord, PracticeSubmission
print(json.dumps({'calls': list(WeeklyAIUsage.objects.order_by('user_id').values_list('ai_calls',flat=True)),
    'graded_records': GradingRecord.objects.filter(user__username='m0-student',question__knowledge_point__name='M0主观评阅').count(),
    'practice_submissions': PracticeSubmission.objects.filter(user__username='m0-student').count(),
    'failed_released': AIUsageReservation.objects.get(request_id=sys.argv[2]).status == 'released',
    'deleted_responses': list(AIUsageReservation.objects.filter(user__username='m0-student',status='succeeded',response__deleted=True).values_list('response',flat=True))}))
"""
            ledger = json.loads(subprocess.check_output([args.backend_python, '-c', source,
                str(ROOT / 'backend'), failed['request_id']], env=env, text=True))
            assert ledger['graded_records'] == ledger['practice_submissions'] == 1, ledger
            assert ledger['calls'] == [3, 1] and ledger['failed_released'], ledger
            assert len(ledger['deleted_responses']) == 2
            assert all(response == {'engine': 'dsh', 'session_id': sid, 'deleted': True} for response in ledger['deleted_responses'])
            print(json.dumps({'site_authentication': True, 'subjective_dsh_grade_saved_once': True,
                'objective_score_deterministic': True, 'failed_grade_not_saved': True, 'asgi_stream_before_completion': True, 'stream_replay_no_extra_call': True, 'parallel_students_isolated': True,
                'native_session_resumed': True, 'cross_student_session_denied': True,
                'idempotent_without_extra_model_call': True, 'weekly_calls': ledger['calls'],
                'failed_call_released': True, 'session_and_cached_text_deleted': True,
                'runtime_capacity_denied_without_model_call': True, 'failed_new_session_cleaned': True,
                'model': 'local-protocol-fixture', 'runtime': 'actual-dsh-sdk'}, ensure_ascii=False), flush=True)
            if args.serve:
                import signal
                model.response_status = 200
                print(json.dumps({'site_fixture': base, 'browser_entry': '/dev/dsh?source=site',
                    'synthetic_login_a': '/api/ai/dsh-fixture/student-a/',
                    'synthetic_login_b': '/api/ai/dsh-fixture/student-b/',
                    'synthetic_logout': '/api/ai/dsh-fixture/logout/',
                    'browser_practice': f'/xiaoyu/practice/{failed_practice["session_id"]}'}, ensure_ascii=False), flush=True)
                signal.pause()
        except Exception:
            diagnostics.flush()
            diagnostics.seek(0)
            text = diagnostics.read()
            print(json.dumps({'sqlite_database_locked': 'database is locked' in text,
                              'internal_server_error': 'Internal Server Error' in text}), flush=True)
            raise
        finally:
            backend.terminate()
            backend.wait(timeout=10)
            model.shutdown()
            model.server_close()
            diagnostics.close()


if __name__ == '__main__':
    main()
