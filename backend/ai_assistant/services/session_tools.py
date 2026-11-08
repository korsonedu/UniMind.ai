"""Model-authored JSON functions registered only inside the current prototype chat."""
import json
import math
import subprocess

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from rest_framework.exceptions import NotFound, ValidationError

from ai_assistant.models import AIChatMessage
from .learning_experiments import anchor_for, check_access, ExperimentConflict


NAME_PATTERN = r'^session_[a-z][a-z0-9_]{0,39}$'
SCHEMA_KEYS = {'type', 'description', 'properties', 'required', 'additionalProperties',
               'items', 'enum', 'minimum', 'maximum', 'minLength', 'maxLength', 'minItems', 'maxItems'}


def validate_schema(schema, depth=0):
    if (not isinstance(schema, dict) or depth > 3 or set(schema) - SCHEMA_KEYS
            or not isinstance(schema.get('type'), str)
            or schema['type'] not in {'object', 'array', 'string', 'number', 'integer', 'boolean', 'null'}):
        raise ValidationError('参数 Schema 仅支持三层以内的 JSON 基础类型、属性、数组、枚举和范围约束。')
    if schema['type'] == 'object':
        properties = schema.get('properties', {})
        if (not isinstance(properties, dict) or len(properties) > 12
                or schema.get('additionalProperties') is not False):
            raise ValidationError('对象参数最多 12 个属性，须设置 additionalProperties=false。')
        for child in properties.values():
            validate_schema(child, depth + 1)
    if schema['type'] == 'array':
        validate_schema(schema.get('items'), depth + 1)


def json_size(value, limit):
    try:
        if len(json.dumps(value, allow_nan=False).encode()) > limit:
            raise ValueError()
    except (ValueError, TypeError, RecursionError):
        raise ValidationError(f'输入或结果必须是 {limit} 字节以内的有限 JSON 数据。') from None


def run_code(source, inputs):
    from .learning_worker import run
    try:
        return run('session_tool_worker.py', {'source': source, 'inputs': inputs})
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {'ok': False, 'error': '会话工具执行失败或超时。'}


def current_anchor(executor):
    claims = getattr(executor, 'experiment_context', None) or {}
    current = AIChatMessage.objects.filter(user=executor.user, pk=claims.get('message_id'), role='user',
        conversation_id=claims.get('conversation_id'), bot_id=claims.get('bot_id')).first()
    if not current:
        raise ValidationError('会话工具需要当前对话授权。')
    return anchor_for(executor.user, current.conversation_id)


def definition(item):
    return {'type': 'function', 'function': {'name': item['name'],
        'description': f"{item['description']}（当前对话工具 v{item['revision']}）",
        'parameters': item['parameters']}}


def refresh(executor, offered=None):
    from .tool_executor import set_permitted_tools
    items = current_anchor(executor).metadata.get('session_tools', {})
    dynamic = [definition(item) for item in items.values()]
    offered = offered if offered is not None else executor._session_tool_offered
    offered[:] = [tool for tool in offered if not tool['function']['name'].startswith('session_')] + dynamic
    permitted = [tool for tool in executor._permitted_tool_definitions.values()
                 if not tool['function']['name'].startswith('session_')]
    set_permitted_tools(executor, [*permitted, *dynamic])
    executor._session_tool_offered = offered
    executor._session_tool_versions = {name: item['revision'] for name, item in items.items()}
    if executor._allowed_tool_names is not None:
        executor._allowed_tool_names = {name for name in executor._allowed_tool_names if not name.startswith('session_')} | set(items)
    return offered


def equivalent(actual, expected):
    if isinstance(expected, bool) or isinstance(actual, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-6)
    if isinstance(expected, dict) and isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(equivalent(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list) and isinstance(actual, list):
        return len(actual) == len(expected) and all(equivalent(a, b) for a, b in zip(actual, expected))
    return type(actual) is type(expected) and actual == expected


def register(executor, arguments):
    check_access(executor.user)
    error = next(Draft202012Validator(SESSION_TOOLS[0]['function']['parameters']).iter_errors(arguments), None)
    if error:
        raise ValidationError(error.message[:300])
    parameters = arguments['parameters']
    json_size(parameters, 4096)
    validate_schema(parameters)
    if parameters.get('type') != 'object':
        raise ValidationError('工具顶层参数必须是 object。')
    try:
        Draft202012Validator.check_schema(parameters)
    except SchemaError:
        raise ValidationError('参数 Schema 不合法。') from None
    anchor = current_anchor(executor)
    name = arguments['name']
    items = anchor.metadata.get('session_tools', {})
    previous = items.get(name)
    if previous and arguments.get('base_revision') != previous['revision']:
        raise ExperimentConflict('修改工具前请读取当前代码与版本号。')
    if not previous and arguments.get('base_revision') is not None:
        raise ValidationError('新建工具须省略 base_revision。')
    if not previous and len(items) >= 6:
        raise ValidationError('本原型每个对话最多注册 6 个工具，请修改已有工具。')
    for sample in arguments['tests']:
        json_size(sample, 8192)
        error = next(Draft202012Validator(parameters).iter_errors(sample['input']), None)
        if error:
            raise ValidationError(f'自检输入不符合参数 Schema：{error.message[:200]}')
    report = run_code(arguments['source'], [sample['input'] for sample in arguments['tests']])
    if not report.get('ok'):
        return {'error': '会话工具自检执行失败，尚未注册。', 'diagnostics': report}
    tests = [{'input': sample['input'], 'expected': sample['expected'], 'actual': actual,
              'ok': equivalent(actual, sample['expected'])}
             for sample, actual in zip(arguments['tests'], report['results'])]
    if len(tests) != len(arguments['tests']) or not all(test['ok'] for test in tests):
        return {'error': '会话工具自检结果不符，尚未注册。请复核源码和期望值。', 'tests': tests}
    item = {key: arguments[key] for key in ('name', 'description', 'parameters', 'source', 'tests')}
    item['revision'] = previous['revision'] + 1 if previous else 1
    metadata = {**anchor.metadata, 'session_tools': {**items, name: item}}
    if not AIChatMessage.objects.filter(pk=anchor.pk, metadata=anchor.metadata).update(metadata=metadata):
        raise ExperimentConflict()
    refresh(executor)
    return {'registered': True, 'name': name, 'revision': item['revision'], 'definition': definition(item),
            'tests': tests, 'message': '下一次工具请求可以直接按此名称调用；仅限当前对话。'}


def read(executor, arguments):
    check_access(executor.user)
    item = current_anchor(executor).metadata.get('session_tools', {}).get(arguments.get('name'))
    if not item:
        raise NotFound('当前对话没有这个会话工具。')
    refresh(executor)
    return item


def invoke(executor, name, arguments):
    check_access(executor.user)
    item = current_anchor(executor).metadata.get('session_tools', {}).get(name)
    if not item:
        raise NotFound('当前对话没有这个会话工具。')
    if getattr(executor, '_session_tool_versions', {}).get(name) != item['revision']:
        raise ExperimentConflict('工具版本已变化，请重新读取后调用。')
    json_size(arguments, 4096)
    error = next(Draft202012Validator(item['parameters']).iter_errors(arguments), None)
    if error:
        raise ValidationError(error.message[:300])
    result = run_code(item['source'], [arguments])
    if not result.get('ok') or len(result.get('results', [])) != 1:
        return {'error': str(result.get('error') or '工具执行失败')[:700]}
    json_size(result['results'][0], 8192)
    return {'tool': name, 'revision': item['revision'], 'result': result['results'][0]}


SESSION_TOOLS = [
    {'type': 'function', 'function': {'name': 'register_session_tool',
        'description': '把自己编写的纯 JavaScript JSON 函数注册为当前对话的新工具。源码须声明 function run(input)，返回有限 JSON 数据；不使用 DOM、网络、文件或第三方包。先运行自检，通过后下一轮可直接调用新工具名。修改前先读取，再传当前 base_revision；失败不会替换旧版本。',
        'parameters': {'type': 'object', 'additionalProperties': False, 'properties': {
            'name': {'type': 'string', 'pattern': NAME_PATTERN},
            'description': {'type': 'string', 'minLength': 1, 'maxLength': 300},
            'parameters': {'type': 'object'},
            'source': {'type': 'string', 'minLength': 1, 'maxLength': 12000},
            'base_revision': {'type': 'integer', 'minimum': 1},
            'tests': {'type': 'array', 'minItems': 1, 'maxItems': 5, 'items': {
                'type': 'object', 'additionalProperties': False,
                'properties': {'input': {'type': 'object'}, 'expected': {
                    'description': '期望的完整 JSON 返回值，对象字段必须与函数返回完全一致，不能只列部分字段。选用可独立核算的样例，不猜测复杂小数。'}},
                'required': ['input', 'expected']}}},
            'required': ['name', 'description', 'parameters', 'source', 'tests']}}},
    {'type': 'function', 'function': {'name': 'read_session_tool',
        'description': '读取当前对话已注册工具的代码、参数、自检与版本，同时刷新本轮工具列表。修改前必须先读取。',
        'parameters': {'type': 'object', 'additionalProperties': False,
            'properties': {'name': {'type': 'string', 'pattern': NAME_PATTERN}}, 'required': ['name']}}},
]
