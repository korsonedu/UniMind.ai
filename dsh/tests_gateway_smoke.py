"""Small HTTP smoke for admission, budgets and actual streamed usage."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from threading import Event, Thread
from time import monotonic
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from gateway import task_gateway
from smoke import model_fixture


def slow_fixture():
    ready = Event()

    class Slow(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            try:
                self.wfile.write(b'data: {')
                self.wfile.flush()
                ready.set()
                for _ in range(20):
                    Event().wait(0.06)
                    self.wfile.write(b' ')
                    self.wfile.flush()
                self.wfile.write(b'"type":"ping"}\n\n')
            except OSError:
                pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Slow)
    Thread(target=server.serve_forever, daemon=True).start()
    return server, ready


class GatewaySmoke(unittest.TestCase):
    def test_insufficient_balance_is_not_retried_upstream(self):
        upstream, calls = model_fixture(status=402)
        context = {'model_policy': {'operation': 'assistant.chat.planner', 'tier': 'fast',
                   'model': 'deepseek-v4-flash', 'max_requests': 4, 'max_tokens': 128, 'max_request_bytes': 4096}, 'tools': []}
        try:
            with task_gateway(context, f'http://127.0.0.1:{upstream.server_port}/v1/messages',
                              'SYNTHETIC_SECRET', 'local-protocol-smoke') as gateway:
                for _ in range(2):
                    request = Request(gateway['url'] + '/messages', json.dumps({'model': 'deepseek-v4-flash',
                        'stream': True, 'max_tokens': 128, 'messages': []}).encode(), {'x-api-key': gateway['credential']})
                    with self.assertRaises(HTTPError) as error:
                        urlopen(request, timeout=5)
                    with error.exception:
                        self.assertEqual(error.exception.code, 402)
                self.assertEqual(len(calls), 1)
                self.assertEqual(gateway['requests'][0]['status'], 'upstream_http_402')
        finally:
            upstream.shutdown()
            upstream.server_close()

    def check_interrupted_stream(self, deadline):
        upstream, ready = slow_fixture()
        context = {'model_policy': {'operation': 'assistant.chat.planner', 'tier': 'fast',
                   'model': 'deepseek-v4-flash', 'max_requests': 1, 'max_tokens': 128, 'max_request_bytes': 4096}, 'tools': []}
        try:
            with TemporaryDirectory() as temp, patch('gateway.TASK_TIMEOUT_SECONDS', deadline):
                audit = Path(temp) / 'usage.jsonl'
                with task_gateway(context, f'http://127.0.0.1:{upstream.server_port}/v1/messages',
                                  'SYNTHETIC_SECRET', 'local-protocol-smoke', audit) as gateway:
                    body = {'model': 'deepseek-v4-flash', 'stream': True, 'max_tokens': 128, 'messages': []}
                    def consume():
                        try:
                            with urlopen(Request(gateway['url'] + '/messages', json.dumps(body).encode(),
                                         {'x-api-key': gateway['credential']}), timeout=3) as response:
                                response.read()
                        except OSError:
                            pass
                    started = monotonic()
                    client = Thread(target=consume, daemon=True)
                    client.start()
                    self.assertTrue(ready.wait(2))
                    if deadline < 1:
                        client.join(timeout=2)
                        self.assertLess(monotonic() - started, 0.8)
                saved = json.loads(audit.read_text())['requests'][0]
                self.assertEqual(saved['status'], 'interrupted')
                self.assertIn('elapsed_ms', saved)
                self.assertFalse(saved['usage_complete'])
                client.join(timeout=2)
                self.assertFalse(client.is_alive())
        finally:
            upstream.shutdown()
            upstream.server_close()

    def test_deadline_interrupts_partial_line(self):
        self.check_interrupted_stream(0.2)

    def test_shutdown_settles_audit(self):
        self.check_interrupted_stream(5)

    def test_task_admission_and_usage(self):
        upstream, calls = model_fixture()
        context = {'model_policy': {'operation': 'assistant.chat.planner', 'tier': 'fast',
                   'model': 'deepseek-v4-flash', 'max_requests': 1, 'max_tokens': 128, 'max_request_bytes': 4096},
                   'tools': [{'function': {'name': 'get_learning_stats'}}]}
        try:
            with TemporaryDirectory() as temp:
                audit = Path(temp) / 'usage.jsonl'
                with task_gateway(context, f'http://127.0.0.1:{upstream.server_port}/v1/messages',
                                  'SYNTHETIC_UPSTREAM_SECRET', 'local-protocol-smoke', audit) as gateway:
                    body = {'model': 'deepseek-v4-flash', 'stream': True, 'max_tokens': 128,
                            'messages': [{'role': 'user', 'content': 'SYNTHETIC_PRIVATE_PROMPT'}]}

                    def send(data, credential=gateway['credential']):
                        request = Request(gateway['url'] + '/messages', json.dumps(data).encode(),
                                          {'Content-Type': 'application/json', 'x-api-key': credential})
                        try:
                            with urlopen(request, timeout=5) as response:
                                return response.status, response.read()
                        except HTTPError as exc:
                            with exc:
                                return exc.code, exc.read()

                    self.assertEqual(send(body, 'wrong')[0], 401)
                    self.assertEqual(send({**body, 'model': 'deepseek-v4-pro'})[0], 403)
                    self.assertEqual(send({**body, 'max_tokens': 129})[0], 403)
                    self.assertEqual(send({**body, 'tools': [{'name': 'web_search', 'type': 'web_search'}]})[0], 403)
                    self.assertEqual(send({**body, 'messages': [{'role': 'user', 'content': 'x' * 4096}]})[0], 413)
                    self.assertEqual(calls, [])
                    self.assertEqual(send(body)[0], 200)
                    self.assertEqual(send(body)[0], 429)
                    self.assertEqual(len(calls), 1)
                    self.assertEqual(gateway['requests'][0]['usage'], {'input_tokens': 20, 'output_tokens': 10})
                    self.assertTrue(gateway['requests'][0]['usage_complete'])
                text = audit.read_text()
                self.assertNotIn('SYNTHETIC_UPSTREAM_SECRET', text)
                self.assertNotIn('SYNTHETIC_PRIVATE_PROMPT', text)
                self.assertEqual(json.loads(text)['requests'][0]['status'], 'completed')
        finally:
            upstream.shutdown()
            upstream.server_close()

    def test_official_destination_cannot_be_replaced(self):
        with self.assertRaises(ValueError):
            with task_gateway({}, 'https://example.invalid/messages', 'SYNTHETIC_SECRET', 'deepseek-official'):
                self.fail('Unapproved destination admitted')


if __name__ == '__main__':
    unittest.main()
