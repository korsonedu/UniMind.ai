"""Loopback-only, single-student M0 Host. Not a production model gateway."""
import importlib.metadata
import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from deepseek_harness import DeepSeekHarness
from gateway import task_gateway
from sessions import SessionStore, SessionUnavailable, context_version
from cards import tool_cards


ROOT = Path(__file__).resolve().parent
SESSIONS = SessionStore(ROOT.parent / '.m0-state' / 'sessions')


class HostConfigurationError(Exception):
    """Only fixed, user-facing configuration messages belong in this error."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def backend_request(path, body):
    token = os.environ.get('UNIMIND_AUTH_TOKEN', '')
    if not token:
        raise HostConfigurationError('尚未配置 M0 学生身份。')
    base = os.environ.get('UNIMIND_API_URL', 'http://127.0.0.1:8000')
    if urlsplit(base).hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise HostConfigurationError('M0 业务接口仅允许本机隔离服务。')
    request = Request(base.rstrip('/') + path, json.dumps(body).encode(), {
        'Content-Type': 'application/json', 'Authorization': ('DSH ' if os.environ.get('UNIMIND_DSH_AUTH_SCHEME') == 'DSH' else 'Token ') + token,
    }, method='POST')
    with build_opener(NoRedirect()).open(request, timeout=15) as response:
        return json.load(response)


def run_turn(message, model_config=None, session_id=None):
    with SESSIONS.lock:
        return run_session_turn(message, model_config, session_id)


def run_session_turn(message, model_config, session_id):
    if model_config is None:
        model_url = os.environ.get('UNIMIND_DSH_MODEL_URL', '')
        if urlsplit(model_url).hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise HostConfigurationError('请通过隔离验证启动器配置模型来源。')
        model_config = {'url': model_url.rstrip('/') + '/messages',
                        'key': 'local-protocol-fixture', 'mode': 'local-protocol-smoke'}
    context = backend_request('/api/ai/dsh/context/', {'message': message})
    context['runtime_source'] = model_config['mode']
    state = SESSIONS.load(context, session_id) if session_id else SESSIONS.create(context)
    recent = [{'role': m['role'], 'content': m['content'][-1000:]} for m in state['messages'][state['runtime_start']:][-6:]] if state['runtime_ready'] else []
    if recent:
        context = backend_request('/api/ai/dsh/context/', {'message': message, 'recent_messages': recent})
        context['runtime_source'] = model_config['mode']
        if context_version(context) != state['context_version']:
            SESSIONS.invalidate(context, state)
            recent = []
            context = backend_request('/api/ai/dsh/context/', {'message': message})
            context['runtime_source'] = model_config['mode']
    state['dirty'] = True
    SESSIONS.save(context, state)
    home = SESSIONS.directory(context, state['id']) / 'runtime'
    home.mkdir(mode=0o700, exist_ok=True)
    audit_path = None
    if model_config['mode'] == 'deepseek-official':
        audit_directory = Path(os.environ.get('UNIMIND_DSH_AUDIT_DIR', ROOT.parent / '.m0-state'))
        audit_directory.mkdir(exist_ok=True)
        audit_path = audit_directory / 'gateway-usage.jsonl'
    with task_gateway(context, model_config['url'], model_config['key'], model_config['mode'], audit_path) as gateway:
        with DeepSeekHarness(
            dsh_home=str(home), cwd=str(home), patches=(str(ROOT / 'profile.patch.yml'),),
            provider='deepseek-official', model=context['model_policy']['model'],
            base_url=gateway['url'], api_key=gateway['credential'], max_tokens=context['model_policy']['max_tokens'],
            request_timeout_seconds=90, initialize_timeout_seconds=20,
            env={
                'UNIMIND_API_URL': os.environ.get('UNIMIND_API_URL', 'http://127.0.0.1:8000'),
                'UNIMIND_AUTH_TOKEN': os.environ.get('UNIMIND_AUTH_TOKEN', ''),
                'UNIMIND_DSH_MESSAGE': message,
                'UNIMIND_DSH_RECENT_MESSAGES': json.dumps(recent, ensure_ascii=False),
            },
        ) as harness:
            session = harness.resume_session(state['runtime_id']) if state['runtime_ready'] else harness.start_session(state['runtime_id'])
            result = session.run(message)
    if any(r['status'] == 'upstream_http_402' for r in gateway['requests']):
        raise HostConfigurationError('DeepSeek 官方接口返回 402（余额不足），请检查账户余额；本轮未完成。')
    if not result.final_response:
        raise RuntimeError('DSH turn did not produce a response')
    if result.finish_reason != 'completed':
        raise HostConfigurationError('本轮未完整完成，请重新提问；未保存为成功对话。')
    if not gateway['requests'] or any(r['status'] != 'completed' for r in gateway['requests']):
        raise RuntimeError('Gateway turn did not complete')
    current = backend_request('/api/ai/dsh/context/', {'message': message})
    current['runtime_source'] = model_config['mode']
    if context_version(current) != state['context_version']:
        SESSIONS.invalidate(current, state)
        raise HostConfigurationError('学生记忆或权限已变化，本轮结果未保留，请重新提问。')
    state['messages'].extend([{'role': 'user', 'content': message},
                              {'role': 'assistant', 'content': result.final_response, 'mode': gateway['mode'],
                               'cards': tool_cards(result.events, context)}])
    state.update(dirty=False, runtime_ready=True, updated_at=datetime.now(timezone.utc).isoformat())
    SESSIONS.save(context, state)
    usage = {'operation': context['model_policy']['operation'], 'mode': gateway['mode'],
             'model': context['model_policy']['model'], 'requests': gateway['requests'], 'task_id': gateway['task_id']}
    routing = {**context['routing'], 'selected_calls': [event['data']['name'] for event in result.events
               if event.get('type') == 'tool/call']}
    return {
        'content': result.final_response,
        'finish_reason': result.finish_reason,
        'session_id': state['id'], 'session': SESSIONS.public(state),
        'mode': gateway['mode'], 'gateway': usage, 'routing': routing,
    }


class Handler(BaseHTTPRequestHandler):
    model_config = None

    def log_message(self, *_args):
        pass  # Do not log cookies, user prompts or tokens.

    def reply(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != '/health':
            return self.reply(404, {'error': 'not_found'})
        self.reply(200, {
            'sdk': importlib.metadata.version('deepseek-harness-sdk'),
            'backend_configured': bool(os.environ.get('UNIMIND_AUTH_TOKEN')),
            'model_configured': bool(self.model_config or os.environ.get('UNIMIND_DSH_MODEL_URL')),
            'mode': self.model_config['mode'] if self.model_config else 'local-protocol-smoke',
        })

    def do_POST(self):
        origin = self.headers.get('Origin')
        if origin and origin not in ('http://127.0.0.1:5175', 'http://localhost:5175'):
            return self.reply(403, {'error': 'origin_denied'})
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.reply(415, {'error': 'json_required'})
        if self.path not in ('/context', '/chat', '/session/read', '/session/new', '/session/delete'):
            return self.reply(404, {'error': 'not_found'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length < 1 or length > 16384:
                return self.reply(400, {'error': 'invalid_body_size'})
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                return self.reply(400, {'error': 'json_object_required'})
            message = data.get('message', '')
            if not isinstance(message, str) or len(message) > 4000:
                return self.reply(400, {'error': 'invalid_message'})
            session_id = data.get('session_id')
            if self.path.startswith('/session/'):
                with SESSIONS.lock:
                    context = backend_request('/api/ai/dsh/context/', {})
                    context['runtime_source'] = self.model_config['mode'] if self.model_config else 'local-protocol-smoke'
                    if self.path == '/session/new':
                        result = SESSIONS.public(SESSIONS.create(context))
                    elif self.path == '/session/delete':
                        SESSIONS.delete(context, session_id)
                        result = {'deleted': True}
                    else:
                        result = SESSIONS.public(SESSIONS.load(context, session_id))
            else:
                result = backend_request('/api/ai/dsh/context/', {'message': message}) if self.path == '/context' else run_turn(message, self.model_config, session_id)
            return self.reply(200, result)
        except SessionUnavailable:
            return self.reply(404, {'error': '本机会话不存在或不属于当前账号，请开启新会话。'})
        except HostConfigurationError as exc:
            return self.reply(400, {'error': str(exc)})
        except HTTPError as exc:
            return self.reply(400, {'error': f'业务接口返回 {exc.code}'})
        except (ValueError, UnicodeError):
            return self.reply(400, {'error': '请求或本地配置格式无效，请检查配置。'})
        except Exception:
            return self.reply(503, {'error': 'M0 链路尚不可用，请检查本地服务与运行日志。'})


if __name__ == '__main__':
    print('UniMind M0 Host: http://127.0.0.1:8791 (local protocol smoke only)', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8791), Handler).serve_forever()
