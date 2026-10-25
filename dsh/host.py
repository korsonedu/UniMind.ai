"""Loopback-only, single-student M0 Host. Not a production model gateway."""
import importlib.metadata
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from deepseek_harness import DeepSeekHarness
from gateway import task_gateway


ROOT = Path(__file__).resolve().parent


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
        'Content-Type': 'application/json', 'Authorization': 'Token ' + token,
    }, method='POST')
    with build_opener(NoRedirect()).open(request, timeout=15) as response:
        return json.load(response)


def run_turn(message, model_config=None):
    if model_config is None:
        model_url = os.environ.get('UNIMIND_DSH_MODEL_URL', '')
        if urlsplit(model_url).hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise HostConfigurationError('请通过隔离验证启动器配置模型来源。')
        model_config = {'url': model_url.rstrip('/') + '/messages',
                        'key': 'local-protocol-fixture', 'mode': 'local-protocol-smoke'}
    context = backend_request('/api/ai/dsh/context/', {'message': message})
    audit_path = None
    if model_config['mode'] == 'deepseek-official':
        state = ROOT.parent / '.m0-state'
        state.mkdir(exist_ok=True)
        audit_path = state / 'gateway-usage.jsonl'
    with task_gateway(context, model_config['url'], model_config['key'], model_config['mode'], audit_path) as gateway, \
            TemporaryDirectory(prefix='unimind-dsh-') as home:
        with DeepSeekHarness(
            dsh_home=home, cwd=home, patches=(str(ROOT / 'profile.patch.yml'),),
            provider='deepseek-official', model=context['model_policy']['model'],
            base_url=gateway['url'], api_key=gateway['credential'], max_tokens=context['model_policy']['max_tokens'],
            request_timeout_seconds=90, initialize_timeout_seconds=20,
            env={
                'UNIMIND_API_URL': os.environ.get('UNIMIND_API_URL', 'http://127.0.0.1:8000'),
                'UNIMIND_AUTH_TOKEN': os.environ.get('UNIMIND_AUTH_TOKEN', ''),
                'UNIMIND_DSH_MESSAGE': message,
            },
        ) as harness:
            result = harness.run(message)
    if not result.final_response:
        raise RuntimeError('DSH turn did not produce a response')
    if not gateway['requests'] or any(r['status'] != 'completed' for r in gateway['requests']):
        raise RuntimeError('Gateway turn did not complete')
    usage = {'operation': context['model_policy']['operation'], 'mode': gateway['mode'],
             'model': context['model_policy']['model'], 'requests': gateway['requests'], 'task_id': gateway['task_id']}
    return {
        'content': result.final_response,
        'finish_reason': result.finish_reason,
        'session_id': result.session_id,
        'mode': gateway['mode'], 'gateway': usage,
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
        if self.path not in ('/context', '/chat'):
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
            result = backend_request('/api/ai/dsh/context/', {'message': message}) if self.path == '/context' else run_turn(message, self.model_config)
            return self.reply(200, result)
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
