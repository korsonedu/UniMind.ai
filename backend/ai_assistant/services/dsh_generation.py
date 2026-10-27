"""Internal generation through the existing DSH collector and task gateway."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
from threading import Thread

from django.conf import settings
from django.db import close_old_connections
from jsonschema import validate

from ai_engine.config import get_model_for_task, get_model_tier_for_operation
from .dsh_runtime import DshUnavailable
from .dsh_tasks import run_structured


TEXT_SCHEMA = {'type': 'object', 'properties': {'text': {'type': 'string'}},
               'required': ['text'], 'additionalProperties': False}
TEACHING_OPERATIONS = frozenset({
    'assistant.chat.exam_generator', 'quizzes.bulk_generate', 'quizzes.generate_ai_answer',
    'quizzes.single_pipeline.reviewer', 'quizzes.preview_parse', 'generate_knowledge_tree',
    'knowledge_edge_analyze', 'pipeline.author', 'pipeline.reviewer',
    'pipeline.author_revise', 'pipeline.classifier',
})


def enabled(operation):
    return (getattr(settings, 'UNIMIND_DSH_GENERATION_ENABLED', False)
            or getattr(settings, 'UNIMIND_DSH_TEACHING_ENABLED', False) and operation in TEACHING_OPERATIONS)


@contextmanager
def callbacks(tools, executor):
    if not tools:
        yield None
        return
    definitions = {tool['function']['name']: tool['function'] for tool in tools}
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            close_old_connections()
            status, result = 200, None
            try:
                self.connection.settimeout(15)
                if not secrets.compare_digest(self.headers.get('Authorization', ''), f'Bearer {token}'):
                    raise PermissionError()
                name = self.path[1:]
                if name not in definitions:
                    raise PermissionError()
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 65536:
                    raise ValueError()
                arguments = json.loads(self.rfile.read(size))
                validate(arguments, definitions[name]['parameters'])
                if hasattr(executor, 'check_dsh_scope'):
                    executor.check_dsh_scope()
                result = executor(name, arguments)
                if isinstance(result, str):
                    result = json.loads(result)
                if len(json.dumps(result).encode()) > 2 * 1024 * 1024:
                    raise ValueError()
            except Exception:
                status, result = 403, {'error': '教研工具未获授权、参数无效或执行失败。'}
            finally:
                close_old_connections()
            body = json.dumps(result, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = False
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {'url': f'http://127.0.0.1:{server.server_port}', 'token': token}
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def generate(messages, operation, *, schema=None, tool_name='submit_result',
             tools=(), executor=None, max_tokens=8192, max_requests=5):
    from backoffice.teaching_executor import TeachingExecutor
    tools = list(tools or [])
    if tools:
        names = {tool['function']['name'] for tool in tools}
        if isinstance(executor, TeachingExecutor):
            if names & {'render_visual', 'save_questions_to_bank'}:
                raise DshUnavailable('教研写操作需要界面确认。')
            executor.check_dsh_scope()
        elif not names <= {'lookup_knowledge_point_definition', 'search_similar_questions'}:
            raise DshUnavailable('此旧工具执行器尚未授权用于 DSH。')
    config = get_model_for_task(operation)
    groups = {}
    if len(tools) > 6:
        groups = {str(index // 6): tools[index:index + 6] for index in range(0, len(tools), 6)}
    with callbacks(tools, executor) as bridge:
        internal = {'operation': operation, 'schema': TEXT_SCHEMA if schema is None else schema,
                    'name': tool_name if schema is not None else 'submit_text',
                    'tier': get_model_tier_for_operation(operation) or 'fast',
                    'tokens': min(max(1, int(max_tokens)), 8192),
                    'max_requests': min(max(1, int(max_requests)), 8) if tools else 1,
                    'thinking': config.get('thinking'), 'tools': tools, 'groups': groups,
                    'bridge': bridge,
                    'instruction': '\n'.join(str(row.get('content') or '') for row in messages if row.get('role') == 'system')}
        prompt = json.dumps([row for row in messages if row.get('role') != 'system'], ensure_ascii=False)
        return run_structured('server.generate', prompt, internal=internal)


def chat_result(result):
    return {'choices': [{'message': {'role': 'assistant', 'content': result['text']}, 'finish_reason': 'stop'}]}
