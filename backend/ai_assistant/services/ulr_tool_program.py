"""Compile model instructions into fixed, authorized ULR read operations."""
import re

from jsonschema import Draft202012Validator
from rest_framework.exceptions import PermissionDenied

from ai_engine.tools import GET_PRACTICE_QUESTIONS_SCHEMA, SEARCH_ASR_SCHEMA


NAME = 'run_course_tools'
PRACTICE_NAME = 'run_practice_tools'
CURRENT_COURSE_NAME = 'locate_current_course_transcript'
# Bump when the instruction grammar or its bound operation contracts change.
VERSION = 5
PROGRAM_OPS = {
    NAME: ('search_courses', 'search_asr'),
    PRACTICE_NAME: ('search_knowledge_tree', 'get_practice_questions'),
    CURRENT_COURSE_NAME: ('search_asr',),
}
SOURCE_ACCESS_REVOKED = 'source_access_revoked'
TEXT = {'type': 'string', 'pattern': r'\S'}
PRACTICE_FILTERS = ('difficulty', 'q_type', 'subjective_type', 'limit', 'exclude_mastered')
PROGRAM_DESCRIPTIONS = {
    NAME: '查找课程并在命中的一门课内定位讲稿。',
    PRACTICE_NAME: '查找知识点并从命中的一个知识点准备站内练习卡。',
    CURRENT_COURSE_NAME: '在当前打开的课程中定位讲稿，课程由站内页面提供。',
}
_ORDINALS = ('一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '十一', '十二', '十三', '十四', '十五')
_ENGLISH_ORDINALS = ('first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'tenth',
                     'eleventh', 'twelfth', 'thirteenth', 'fourteenth', 'fifteenth')


def requested_rank(message, practice):
    chinese_unit = r'(?:项|个(?:相关|匹配的?)?知识点)' if practice else r'门(?:相关|匹配的?)?课(?:程)?'
    english_unit = r'(?:knowledge point|result)' if practice else r'course'
    ranks = {int(value) if value.isascii() else _ORDINALS.index(value) + 1
             for value in re.findall(rf'第\s*([1-9][0-9]?|{"|".join(reversed(_ORDINALS))})\s*{chinese_unit}', message)}
    ranks.update(_ENGLISH_ORDINALS.index(value) + 1 for value in re.findall(
        rf'\b({"|".join(_ENGLISH_ORDINALS)})\s+(?:(?:matching|relevant)\s+)?{english_unit}\b', message.lower()))
    return ranks.pop() if len(ranks) == 1 else None


def program_tool(name, properties, max_rank):
    return {'type': 'function', 'function': {
        'name': name,
            'description': (f'{PROGRAM_DESCRIPTIONS[name]} 单独提交 v={VERSION}。默认要求唯一匹配，多个匹配时请用户补充名称或学科；'
                        '仅当用户明确指定第几项时才传 rank（第一项为 1）。'),
        'parameters': {'type': 'object', 'additionalProperties': False, 'required': ['v', 'find'], 'properties': {
            'v': {'type': 'integer', 'enum': [VERSION]},
            'find': {**TEXT, 'description': '要查找的课程或知识点'},
            'subject': TEXT,
            'rank': {'type': 'integer', 'minimum': 1, 'maximum': max_rank},
            **properties,
        }},
    }}


PROGRAM_TOOLS = {
    NAME: program_tool(NAME,
        {'query': {**TEXT, 'description': '讲稿关键词，省略时沿用 find'},
         'limit': SEARCH_ASR_SCHEMA['properties']['limit']}, 10),
    PRACTICE_NAME: program_tool(PRACTICE_NAME,
        {field: GET_PRACTICE_QUESTIONS_SCHEMA['properties'][field] for field in PRACTICE_FILTERS}, 15),
    CURRENT_COURSE_NAME: {'type': 'function', 'function': {
        'name': CURRENT_COURSE_NAME,
        'description': f'{PROGRAM_DESCRIPTIONS[CURRENT_COURSE_NAME]} 单独提交 v={VERSION} 和讲稿搜索词。',
        'parameters': {'type': 'object', 'additionalProperties': False, 'required': ['v', 'query'], 'properties': {
            'v': {'type': 'integer', 'enum': [VERSION]},
            'query': {**TEXT, 'description': '讲稿关键词'}, 'limit': SEARCH_ASR_SCHEMA['properties']['limit'],
        }},
    }},
}


def program_discovery(tool, program_names):
    function = tool['function']
    parameters = function['parameters']
    programs = [{
        'required': ['program'],
        'properties': {
            'program': {'enum': [name]},
            'instruction': PROGRAM_TOOLS[name]['function']['parameters'],
        },
    } for name in program_names]
    descriptions = ' '.join(f'{name} {PROGRAM_DESCRIPTIONS[name]}' for name in program_names)
    return {**tool, 'function': {**function,
        'description': (f"{function['description']} 请单独调用。组合指令提交 program 和 instruction。{descriptions} "
                        '默认只接受唯一匹配。只有用户明确指定第几项时才传 rank，第一项为 1。'
                        '只传 program 可先查看指令契约。'),
        'parameters': {'type': 'object', 'additionalProperties': False,
            'properties': {**parameters['properties'], 'program': {'type': 'string', 'enum': program_names},
                           'instruction': {'type': 'object'}},
            'oneOf': [{'required': ['group'], 'not': {'required': ['instruction']}}, *programs]}}}


def run_program(arguments, allowed_tools, execute, *, name=NAME, message='', current_course_id=None):
    operations = PROGRAM_OPS[name]
    second = operations[-1]
    anchored = name == CURRENT_COURSE_NAME
    practice = name == PRACTICE_NAME
    collection, binding = ('results', 'knowledge_point_id') if practice else ('courses', 'course_id')

    def failure(code, message, *, repairable=False, **details):
        return {'error': {'code': code, 'message': message, 'repairable': repairable}, 'steps_executed': [], **details}

    if isinstance(arguments, dict) and 'v' not in arguments:
        return failure('missing_tool_version', '工具指令缺少版本。', field='$.v', current_version=VERSION)
    if isinstance(arguments, dict) and (type(arguments['v']) is not int or arguments['v'] != VERSION):
        return failure('stale_tool_version', '工具指令版本不符。', field='$.v', current_version=VERSION)
    schema = PROGRAM_TOOLS[name]['function']['parameters']
    if isinstance(arguments, dict):
        arguments = arguments.copy()
        # Accept an exact decimal spelling without asking the model to resend the same value.
        for field in ('rank', 'limit'):
            if field not in schema['properties']:
                continue
            value = arguments.get(field)
            if isinstance(value, str) and re.fullmatch(r'0|[1-9][0-9]*', value):
                maximum = schema['properties'][field]['maximum']
                if len(value) > len(str(maximum)):
                    return failure('invalid_arguments', '指令参数校验失败。', field=f'$.{field}',
                                   rule='maximum', expected=maximum)
                arguments[field] = int(value)
            elif isinstance(value, float):
                return failure('invalid_arguments', '指令参数校验失败。', field=f'$.{field}',
                               rule='type', expected='integer', repairable=True)
    if error := next(Draft202012Validator(schema).iter_errors(arguments), None):
        field = error.json_path
        if error.validator == 'required':
            field = '$.query' if anchored else '$.find'
        elif error.validator == 'additionalProperties':
            field = '$.' + next(key for key in arguments if key not in error.schema['properties'])
        return failure('invalid_arguments', '指令参数校验失败。', field=field, rule=error.validator,
                       expected=error.validator_value,
                       repairable=error.validator in ('type', 'required'))
    if any(operation not in allowed_tools for operation in operations):
        return failure('tool_not_offered', '当前工具组无法执行这条指令。')
    if practice and arguments.get('q_type') == 'objective' and 'subjective_type' in arguments:
        return failure('invalid_arguments', '客观题不能指定主观题题型。', field='$.subjective_type')

    steps = []
    if anchored:
        if type(current_course_id) is not int or current_course_id < 1:
            return failure('missing_course_context', '请从目标课程页面重新发起提问。')
        source_id = current_course_id
    else:
        first = operations[0]
        rank = None
        if 'rank' in arguments:
            rank = requested_rank(message, practice)
            if rank is not None and rank != arguments['rank']:
                return failure('rank_mismatch', '序号与用户明确指定的顺序不同。', field='$.rank', expected=rank,
                               repairable=rank <= schema['properties']['rank']['maximum'])
        first_args = {'query': arguments['find']}
        if 'subject' in arguments:
            first_args['subject'] = arguments['subject']
        if not practice:
            first_args['limit'] = rank or 2
        initial = execute(first, first_args)
        steps.append(first)
        if initial.get('error'):
            return failure('tool_failed', '第一步查询失败。', step=first, steps_executed=steps)

        rows = initial.get(collection, [])
        if rank is None and len(rows) > 1:
            reason = '匹配到多个知识点，请用户补充名称或学科。' if practice else '匹配到多门课，请用户补充课程名称或学科。'
            return failure('ambiguous_dependency', reason, step=second, steps_executed=steps)
        index = (rank or 1) - 1
        if index >= len(rows) or type(source_id := rows[index].get('id')) is not int or source_id < 1:
            return failure('missing_dependency', '第一步未返回指定结果。', step=second, steps_executed=steps)

    filters = PRACTICE_FILTERS if practice else ('limit',)
    second_args = {key: arguments[key] for key in filters if key in arguments}
    second_args[binding] = source_id
    if not practice:
        second_args['query'] = arguments['query'] if anchored else arguments.get('query', arguments['find'])
    try:
        result = execute(second, second_args)
    except PermissionDenied:
        message = '所选知识点已不可访问，练习查询已停止。' if practice else '引用课程已不可访问，讲稿查询已停止。'
        return failure(SOURCE_ACCESS_REVOKED, message, step=second, steps_executed=steps)
    steps.append(second)
    if result.get('error'):
        return failure('tool_failed', '资料查询失败。', step=second, steps_executed=steps)
    return {**result, 'steps_executed': steps, '_ulr_source_id': source_id}
