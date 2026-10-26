"""Fixed server-owned DSH grading operations; no student tools or memory."""
from copy import deepcopy
import json
import os
from pathlib import Path
import signal
import subprocess
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from django.conf import settings
from jsonschema import validate, ValidationError as SchemaError
from ai_engine.config import get_model_for_task, FALLBACK_FAST
from ai_engine.tools import GRADING_RESULT_SCHEMA, OBJECTIVE_ANALYSIS_SCHEMA
from .dsh_runtime import DshUnavailable


TASKS = {
    'quizzes.grade_question': ('submit_grading_result', 'pro', 2500, GRADING_RESULT_SCHEMA),
    'quizzes.objective_analysis': ('submit_objective_analysis', 'fast', 2000, OBJECTIVE_ANALYSIS_SCHEMA),
}


def run_structured(operation, prompt):
    if operation not in TASKS or not isinstance(prompt, str) or len(prompt.encode()) > 48000:
        raise DshUnavailable('评分任务类型或材料范围无效。')
    name, tier, tokens, original = TASKS[operation]
    schema = deepcopy(original)
    if operation == 'quizzes.grade_question':
        schema['properties']['error_analysis']['type'] = ['object', 'null']
    wire_schema = deepcopy(schema)
    if operation == 'quizzes.grade_question':
        rating = wire_schema['properties']['memorix_rating']
        rating.pop('minimum'); rating.pop('maximum')
        rating['enum'] = [1, 2, 3, 4]
        error = wire_schema['properties']['error_analysis']
        error['type'] = 'object'
        wire_schema['properties']['error_analysis'] = {'oneOf': [error, {'type': 'null'}]}
    python = getattr(settings, 'UNIMIND_DSH_PYTHON', '')
    state_dir = getattr(settings, 'UNIMIND_DSH_STATE_DIR', '')
    if (not python or not Path(python).is_absolute() or not Path(python).is_file()
            or not state_dir or not Path(state_dir).is_absolute()):
        raise DshUnavailable('尚未配置服务端 DSH 评分环境。')
    config = get_model_for_task(operation)
    if operation == 'quizzes.objective_analysis':
        config['model'] = os.getenv('AI_MODEL_OBJECTIVE_ANALYSIS') or os.getenv('AI_MODEL_FAST') or FALLBACK_FAST
    fixture = getattr(settings, 'UNIMIND_DSH_FIXTURE_URL', '')
    if fixture:
        if not settings.DEBUG or urlsplit(fixture).scheme != 'http' or urlsplit(fixture).hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise DshUnavailable('协议模拟仅允许本机开发环境。')
        model = {'url': fixture, 'key': 'local-protocol-fixture', 'mode': 'local-protocol-smoke'}
    else:
        if urlsplit(config['base_url']).hostname != 'api.deepseek.com' or not config['api_key']:
            raise DshUnavailable('尚未配置已授权的 DeepSeek 官方来源。')
        model = {'url': 'https://api.deepseek.com/anthropic/v1/messages', 'key': config['api_key'], 'mode': 'deepseek-official'}
    context = {'model_policy': {'operation': operation, 'tier': tier, 'model': config['model'],
                               'max_requests': 1, 'max_tokens': tokens, 'max_request_bytes': 65536},
               'tools': [{'function': {'name': name, 'description': '提交本次结构化评阅结果', 'parameters': wire_schema}}]}
    root = Path(state_dir)
    tasks = root / '.tasks'
    environment = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL', 'TMPDIR', 'SSL_CERT_FILE', 'SSL_CERT_DIR') if key in os.environ}
    worker = Path(settings.BASE_DIR).parent / 'dsh' / 'structured_worker.py'
    try:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        tasks.mkdir(mode=0o700, exist_ok=True)
        with TemporaryDirectory(prefix='grading-', dir=tasks) as home:
            payload = {'prompt': prompt, 'context': context, 'model': model, 'home': home, 'state_dir': state_dir}
            with subprocess.Popen([python, str(worker)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, env=environment, start_new_session=True) as process:
                try:
                    output, _ = process.communicate(json.dumps(payload).encode(), timeout=120)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.communicate()
                    raise DshUnavailable('DSH 评分超时，请稍后重试。') from None
                except BaseException:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.communicate()
                    raise
            if process.returncode or len(output) > 2 * 1024 * 1024:
                raise ValueError()
            response = json.loads(output)
            if not isinstance(response, dict) or response.get('status') != 200:
                raise ValueError()
            result = response['result']
            json.dumps(result, allow_nan=False)
            validate(result, schema)
            return result
    except (OSError, ValueError, KeyError, TypeError, SchemaError):
        raise DshUnavailable('DSH 未返回有效评分，本轮未写入成绩。') from None
