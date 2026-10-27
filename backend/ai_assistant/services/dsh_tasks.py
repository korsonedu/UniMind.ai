"""Fixed server-owned DSH structured operations; no student tools or memory."""
from copy import deepcopy
import json
import os
from pathlib import Path
import signal
import subprocess
from time import monotonic
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from django.conf import settings
from jsonschema import validate, ValidationError as SchemaError
from ai_engine.config import get_model_for_task, FALLBACK_FAST
from ai_engine.tools import GRADING_RESULT_SCHEMA, OBJECTIVE_ANALYSIS_SCHEMA, QUESTION_LIST_SCHEMA
from .dsh_runtime import DshUnavailable
from .dsh_scope import generation_scope, current_execution


TITLE_SCHEMA = {
    'type': 'object',
    'properties': {'title': {'type': 'string'}},
    'required': ['title'],
    'additionalProperties': False,
}

MEMORY_EXTRACTION_SCHEMA = {
    'type': 'object',
    'properties': {
        'memories': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'memory_type': {'type': 'string', 'enum': ['preference', 'academic', 'interaction', 'teacher_context']},
                    'key': {'type': 'string'},
                    'value': {'type': 'string'},
                    'confidence': {'type': 'number'},
                    'evidence': {'type': 'string'},
                },
                'required': ['memory_type', 'key', 'value', 'confidence', 'evidence'],
                'additionalProperties': False,
            },
        },
    },
    'required': ['memories'],
    'additionalProperties': False,
}

TASKS = {
    'quizzes.grade_question': ('submit_grading_result', 'pro', 2500, GRADING_RESULT_SCHEMA),
    'quizzes.preview_parse': ('submit_questions', 'fast', 3200, QUESTION_LIST_SCHEMA),
    'quizzes.objective_analysis': ('submit_objective_analysis', 'fast', 2000, OBJECTIVE_ANALYSIS_SCHEMA),
    'assistant.title': ('submit_title', 'fast', 64, TITLE_SCHEMA),
    'assistant.memory_extract': ('submit_memories', 'fast', 800, MEMORY_EXTRACTION_SCHEMA),
}


def wire_schema(schema):
    """Lower nullable unions to the installed SDK's supported equivalent."""
    result = deepcopy(schema)
    bounds = {key: result.pop(key) for key in ('minimum', 'maximum') if key in result}
    if bounds:
        result['description'] = (result.get('description', '') + ' ' + json.dumps(bounds)).strip()
    if isinstance(result.get('type'), list):
        types = result.pop('type')
        return {'oneOf': [wire_schema({**result, 'type': kind}) if kind != 'null' else {'type': 'null'} for kind in types]}
    if result.get('type') == 'string' and 'enum' in result:
        result['enum'] = [value for value in result['enum'] if isinstance(value, str)]
    if 'properties' in result:
        result['properties'] = {name: wire_schema(value) for name, value in result['properties'].items()}
    if 'items' in result:
        result['items'] = wire_schema(result['items'])
    return result


@generation_scope()
def run_structured(operation, prompt, *, internal=None):
    if (operation not in TASKS and not (operation == 'server.generate' and internal)
            or not isinstance(prompt, str) or len(prompt.encode()) > 48000):
        raise DshUnavailable('结构化任务类型或材料范围无效。')
    name, tier, tokens, original = ((internal['name'], internal['tier'], internal['tokens'], internal['schema'])
                                   if internal else TASKS[operation])
    schema = deepcopy(original)
    if operation == 'quizzes.grade_question':
        schema['properties']['error_analysis']['type'] = ['object', 'null']
    wire = wire_schema(schema)
    if operation == 'quizzes.grade_question':
        rating = wire['properties']['memorix_rating']
        rating['enum'] = [1, 2, 3, 4]
    array_result = operation == 'quizzes.preview_parse' or schema.get('type') == 'array'
    if array_result:
        wire = {'type': 'object', 'properties': {'questions': wire}, 'required': ['questions'], 'additionalProperties': False}
    python = getattr(settings, 'UNIMIND_DSH_PYTHON', '')
    state_dir = getattr(settings, 'UNIMIND_DSH_STATE_DIR', '')
    if (not python or not Path(python).is_absolute() or not Path(python).is_file()
            or not state_dir or not Path(state_dir).is_absolute()):
        raise DshUnavailable('尚未配置服务端 DSH 任务环境。')
    config = get_model_for_task(internal['operation'] if internal else operation)
    if tier == 'fast' and not internal:
        override = os.getenv('AI_MODEL_OBJECTIVE_ANALYSIS') if operation == 'quizzes.objective_analysis' else None
        config['model'] = override or os.getenv('AI_MODEL_FAST') or FALLBACK_FAST
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
               'tools': [{'function': {'name': name, 'description': '提交本次结构化结果', 'parameters': wire}}]}
    instructions = {
        'quizzes.preview_parse': '你是科晟教研录入助手。只解析给定资料中的题目、选项、答案和评分点，保持原意，不自行补写缺失的答案；不能确认的内容留空交给人工复核。',
        'assistant.title': '你是对话标题生成器。根据用户和助手的第一轮内容生成不超过15个字的标题。只输出标题，不加引号或前缀。',
        'assistant.memory_extract': '你是学生长期记忆提取助手。只提取用户亲口明确陈述的稳定偏好、学业背景和交互习惯；不提取助手建议、假设、未确认计划或临时情绪。每条记忆必须附用户原话作为 evidence。单次提问、人工答疑、查资料、准备草稿或本次发布前确认的操作要求不构成长期记忆，不从问题知识点推断学业背景。仅提取明确自述的长期事实；没有合格事实也必须调用提交工具返回 memories=[]。',
    }
    context['task_instruction'] = instructions.get(operation, '你是科晟课程评阅老师。严格按给定题目、参考答案和评分点评阅。')
    context['model_policy']['deadline'] = current_execution()['deadline']
    if internal:
        if len(internal['instruction'].encode()) > 16000:
            raise DshUnavailable('系统任务材料过长。')
        context['task_instruction'] = internal['instruction']
        context['model_policy'].update(max_requests=internal['max_requests'], task_operation=internal['operation'], thinking=internal['thinking'])
        context['model_policy']['temperature'] = internal['temperature']
        context['research_tools'] = [{**tool, 'function': {**tool['function'], 'parameters': wire_schema(tool['function']['parameters'])}} for tool in internal['tools']]
        by_name = {tool['function']['name']: tool for tool in context['research_tools']}
        context['research_groups'] = {key: [by_name[tool['function']['name']] for tool in group] for key, group in internal['groups'].items()}
        context['bridge'] = internal['bridge']
        context['available_tools'] = context['tools'] + internal['tools']
        if internal['groups']:
            context['available_tools'].append({'function': {'name': 'find_teaching_tools'}})
    root = Path(state_dir)
    tasks = root / '.tasks'
    environment = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL', 'TMPDIR', 'SSL_CERT_FILE', 'SSL_CERT_DIR') if key in os.environ}
    worker = Path(settings.BASE_DIR).parent / 'dsh' / 'structured_worker.py'
    try:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        tasks.mkdir(mode=0o700, exist_ok=True)
        with TemporaryDirectory(prefix='structured-', dir=tasks) as home:
            payload = {'prompt': prompt, 'context': context, 'model': model, 'home': home, 'state_dir': state_dir}
            with subprocess.Popen([python, str(worker)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, env=environment, start_new_session=True) as process:
                try:
                    output, _ = process.communicate(json.dumps(payload).encode(), timeout=max(.01, min(120, current_execution()['deadline'] - monotonic() + 2)))
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.communicate()
                    raise DshUnavailable('DSH 任务超时，请稍后重试。') from None
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
            if array_result:
                if not isinstance(result, dict) or set(result) != {'questions'}:
                    raise ValueError()
                result = result['questions']
            json.dumps(result, allow_nan=False)
            validate(result, schema)
            return result
    except (OSError, ValueError, KeyError, TypeError, SchemaError):
        raise DshUnavailable('DSH 未返回有效结构化结果，本轮未写入业务结果。') from None
