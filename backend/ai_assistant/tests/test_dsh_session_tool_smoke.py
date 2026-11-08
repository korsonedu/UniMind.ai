"""Actual pinned DSH plugin + Django callbacks; the model is a loopback fixture."""
import json
import os
from pathlib import Path
import subprocess
from threading import Thread
from uuid import uuid4
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from wsgiref.simple_server import make_server, WSGIRequestHandler

import pytest
from django.core.wsgi import get_wsgi_application
from django.utils import timezone

from ai_assistant.dsh_authentication import make_task_token
from users.models import AIUsageReservation
from .test_session_tool_smoke import REGISTRATION, tool_chat


@pytest.mark.django_db(transaction=True)
def test_native_dsh_register_call_and_mount(tool_chat, settings, tmp_path):
    root = Path(__file__).resolve().parents[3]
    python = root / '.m0-venv/bin/python'
    if not python.exists():
        pytest.skip('Local pinned DSH environment is not installed')
    user, bot, current = tool_chat
    settings.UNIMIND_DSH_ENABLED = True
    settings.ALLOWED_HOSTS = ['127.0.0.1']
    claims = {'message_id': current.pk, 'conversation_id': str(current.conversation_id), 'bot_id': bot.pk}
    reservation = AIUsageReservation.objects.create(user=user, request_id=uuid4(), attempt_id=uuid4(), week=timezone.now().date())
    calls = []
    experiment = {'title': '乘法实验',
        'html': '<button id="go">计算</button><output id="out"></output><script>document.querySelector("#go").onclick=()=>document.querySelector("#out").textContent=6*7;</script>',
        'checks': [{'selector': '#go', 'action': 'click', 'expect_selector': '#out', 'expect_text': '42'}]}

    class Quiet(WSGIRequestHandler):
        def log_message(self, *_args):
            pass

    class Model(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            calls.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            plan = [[('find_learning_tools', {'group': 'authoring'})],
                    [('register_session_tool', REGISTRATION), ('build_learning_experiment', experiment)],
                    [('session_product', {'a': 6, 'b': 7})], []]
            selected = plan[len(calls) - 1] if len(calls) <= 4 else []
            events = [{'type': 'message_start', 'message': {'id': f'msg-{len(calls)}', 'type': 'message',
                'role': 'assistant', 'content': [], 'model': calls[-1]['model'], 'stop_reason': None,
                'stop_sequence': None, 'usage': {'input_tokens': 20, 'output_tokens': 0}}}]
            blocks = [({'type': 'tool_use', 'id': f'call-{len(calls)}-{i}', 'name': name, 'input': {}},
                       {'type': 'input_json_delta', 'partial_json': json.dumps(arguments)})
                      for i, (name, arguments) in enumerate(selected)]
            if not selected:
                blocks = [({'type': 'text', 'text': ''}, {'type': 'text_delta', 'text': '计算结果为 42，请操作实验。'})]
            for i, (block, delta) in enumerate(blocks):
                events.extend([{'type': 'content_block_start', 'index': i, 'content_block': block},
                    {'type': 'content_block_delta', 'index': i, 'delta': delta}, {'type': 'content_block_stop', 'index': i}])
            events.extend([{'type': 'message_delta', 'delta': {'stop_reason': 'tool_use' if selected else 'end_turn',
                'stop_sequence': None}, 'usage': {'output_tokens': 10}}, {'type': 'message_stop'}])
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            for event in events:
                self.wfile.write(('event: ' + event['type'] + '\ndata: ' + json.dumps(event) + '\n\n').encode())
                self.wfile.flush()

    backend = make_server('127.0.0.1', 0, get_wsgi_application(), handler_class=Quiet)
    model = ThreadingHTTPServer(('127.0.0.1', 0), Model)
    threads = [Thread(target=server.serve_forever, daemon=True) for server in (backend, model)]
    for thread in threads:
        thread.start()
    try:
        source = '''
import json, sys
import host
from sessions import SessionStore
host.SESSIONS = SessionStore(sys.argv[1])
print(json.dumps(host.run_turn(sys.argv[2])))
'''
        process = subprocess.run([str(python), '-c', source, str(tmp_path / 'sessions'), current.content],
            cwd=root / 'dsh', env={'PATH': os.defpath, 'HOME': str(Path.home()),
                'UNIMIND_API_URL': f'http://127.0.0.1:{backend.server_port}',
                'UNIMIND_AUTH_TOKEN': make_task_token(user, reservation, chat_context=claims),
                'UNIMIND_DSH_AUTH_SCHEME': 'DSH',
                'UNIMIND_DSH_MODEL_URL': f'http://127.0.0.1:{model.server_port}/v1'},
            capture_output=True, text=True, timeout=100)
        assert process.returncode == 0, process.stderr[-4000:]
        result = json.loads(process.stdout)
        assert len(calls) == 4
        assert all(len(call.get('tools', [])) <= 8 for call in calls)
        assert 'session_product' not in {tool['name'] for tool in calls[1]['tools']}
        assert 'session_product' in {tool['name'] for tool in calls[2]['tools']}
        tool_results = [block for message in calls[3]['messages'] if isinstance(message.get('content'), list)
                        for block in message['content'] if block.get('type') == 'tool_result']
        assert any('"product":42' in str(block.get('content')).replace(' ', '') for block in tool_results)
        assert result['session']['messages'][-1]['cards'][0]['type'] == 'learning_experiment'
        assert all(row['status'] == 'completed' for row in result['gateway']['requests'])
        current.refresh_from_db()
        assert current.metadata['session_tools']['session_product']['revision'] == 1
        assert len(current.metadata['learning_experiments']) == 1
    finally:
        for server in (backend, model):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=2)
