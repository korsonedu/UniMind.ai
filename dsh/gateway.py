"""Per-turn loopback gateway prototype; no student billing or public admission."""
from contextlib import contextmanager
from datetime import datetime, timezone
from http.client import HTTPConnection, HTTPSConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import secrets
import socket
from threading import Event, Lock, Thread, Timer
from time import monotonic
from urllib.parse import urlsplit


TASK_TIMEOUT_SECONDS = 90


@contextmanager
def task_gateway(context, upstream_url, upstream_key, mode, audit_path=None):
    target = urlsplit(upstream_url)
    official = upstream_url == 'https://api.deepseek.com/anthropic/v1/messages'
    fixture = target.scheme == 'http' and target.hostname in ('127.0.0.1', 'localhost', '::1')
    if not ((mode == 'deepseek-official' and official) or (mode == 'local-protocol-smoke' and fixture)):
        raise ValueError('Unsupported model destination')
    if not upstream_key:
        raise ValueError('Missing upstream credential')
    policy = context['model_policy']
    if (policy['operation'] != 'assistant.chat.planner' or policy['tier'] != 'fast'
            or not 1 <= policy['max_requests'] <= 4 or not 1 <= policy['max_tokens'] <= 1024
            or not 1 <= policy['max_request_bytes'] <= 65536):
        raise ValueError('Unsupported M0 task policy')
    allowed_tools = {t['function']['name'] for t in context['tools']}
    capability = secrets.token_urlsafe(32)
    requests = []
    lock = Lock()
    expires = monotonic() + TASK_TIMEOUT_SECONDS
    task_id = secrets.token_hex(12)
    stopping = Event()
    io_lock = Lock()
    active_sockets = set()

    def track(connection):
        with io_lock:
            if stopping.is_set():
                raise TimeoutError('Task closed')
            active_sockets.add(connection)

    def stop_io():
        with io_lock:
            stopping.set()
            connections = list(active_sockets)
        for connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    class Gateway(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(max(0.001, min(5, expires - monotonic())))
            track(self.connection)

        def finish(self):
            try:
                super().finish()
            finally:
                with io_lock:
                    active_sockets.discard(self.connection)

        def log_message(self, *_args):
            pass

        def reject(self, status, code):
            body = json.dumps({'type': 'error', 'error': {'type': 'unimind_gateway', 'message': code}}).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path != '/v1/messages':
                return self.reject(404, 'path_denied')
            credential = self.headers.get('x-api-key', '') or self.headers.get('Authorization', '').removeprefix('Bearer ')
            if not secrets.compare_digest(credential, capability):
                return self.reject(401, 'task_credential_required')
            if monotonic() >= expires:
                return self.reject(403, 'task_expired')
            if not lock.acquire(blocking=False):
                return self.reject(429, 'task_busy')
            try:
                if len(requests) >= policy['max_requests']:
                    return self.reject(429, 'task_request_budget_exhausted')
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= policy['max_request_bytes']:
                        return self.reject(413, 'request_budget_exceeded')
                    body = json.loads(self.rfile.read(length))
                    if (not isinstance(body, dict) or body.get('model') != policy['model']
                            or body.get('stream') is not True or type(body.get('max_tokens')) is not int
                            or not 0 < body['max_tokens'] <= policy['max_tokens']):
                        return self.reject(403, 'model_policy_denied')
                    tools = body.get('tools', [])
                    if not isinstance(tools, list) or any(not isinstance(t, dict) or 'type' in t
                            or t.get('name') not in allowed_tools for t in tools):
                        return self.reject(403, 'tool_policy_denied')
                except (ValueError, TypeError):
                    return self.reject(400, 'invalid_request')
                if stopping.is_set() or monotonic() >= expires:
                    return self.reject(403, 'task_expired')
                # Never forward client headers or enable provider-side search/tools.
                body = {k: v for k, v in body.items() if k in {
                    'model', 'max_tokens', 'messages', 'system', 'tools', 'tool_choice',
                    'stream', 'temperature', 'top_p', 'stop_sequences',
                }}
                body['thinking'] = {'type': 'disabled'}
                record = {'request': len(requests) + 1, 'model': policy['model'],
                          'status': 'started', 'usage': {}, 'usage_complete': False,
                          'tool_results': sum(b.get('type') == 'tool_result'
                              for m in body.get('messages', []) if isinstance(m.get('content'), list)
                              for b in m['content'] if isinstance(b, dict))}
                requests.append(record)  # Failures consume the attempt; no invisible retries.
                started = monotonic()
                streaming = False
                connection = (HTTPSConnection if official else HTTPConnection)(
                    target.hostname, target.port, timeout=max(0.001, min(30, expires - monotonic())))
                upstream_socket = None
                try:
                    connection.connect()
                    upstream_socket = connection.sock
                    track(upstream_socket)
                    if monotonic() >= expires:
                        raise TimeoutError('Task expired')
                    connection.request('POST', target.path, json.dumps(body).encode(), {
                        'Content-Type': 'application/json', 'x-api-key': upstream_key,
                        'anthropic-version': '2023-06-01',
                    })
                    with connection.getresponse() as response:
                        if response.status != 200:
                            record['status'] = f'upstream_http_{response.status}'
                            return self.reject(502, 'upstream_unavailable')
                        if 'text/event-stream' not in response.headers.get('Content-Type', ''):
                            record['status'] = 'invalid_protocol'
                            return self.reject(502, 'upstream_protocol_error')
                        self.send_response(200)
                        self.send_header('Content-Type', 'text/event-stream')
                        self.send_header('Cache-Control', 'no-store')
                        self.end_headers()
                        streaming = True
                        size = 0
                        while True:
                            line = response.readline(65537)
                            if not line:
                                break
                            size += len(line)
                            if len(line) > 65536 or size > 2097152 or monotonic() >= expires:
                                raise RuntimeError('Response budget exceeded')
                            if line.startswith(b'data: '):
                                event = json.loads(line[6:])
                                usage = event.get('usage', event.get('message', {}).get('usage', {}))
                                record['usage'].update({k: v for k, v in usage.items()
                                    if k in ('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens')
                                    and type(v) is int and v >= 0})
                                if event.get('type') == 'message_stop':
                                    record['usage_complete'] = all(k in record['usage'] for k in ('input_tokens', 'output_tokens'))
                            self.wfile.write(line)
                            self.wfile.flush()
                        record['status'] = 'completed' if record['usage_complete'] else ('interrupted' if stopping.is_set() else 'incomplete')
                except Exception:
                    record['status'] = 'interrupted'
                    if not streaming:
                        self.reject(502, 'upstream_unavailable')
                finally:
                    connection.close()
                    with io_lock:
                        active_sockets.discard(upstream_socket)
                    record['elapsed_ms'] = round((monotonic() - started) * 1000)
            finally:
                lock.release()

    # Open the local audit destination before any paid request can be admitted.
    audit = os.fdopen(os.open(audit_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600), 'a') if audit_path else None
    class TaskServer(ThreadingHTTPServer):
        daemon_threads = False  # server_close must join handlers before usage is persisted.

    server = TaskServer(('127.0.0.1', 0), Gateway)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    deadline = Timer(max(0.001, expires - monotonic()), stop_io)
    deadline.daemon = True
    deadline.start()
    try:
        yield {'url': f'http://127.0.0.1:{server.server_port}/v1', 'credential': capability,
               'requests': requests, 'mode': mode, 'policy': policy, 'task_id': task_id}
    finally:
        stop_io()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        deadline.cancel()
        deadline.join()
        if audit:
            with audit:
                audit.write(json.dumps({'task_id': task_id, 'at': datetime.now(timezone.utc).isoformat(),
                    'operation': policy['operation'], 'mode': mode, 'model': policy['model'], 'requests': requests}) + '\n')
