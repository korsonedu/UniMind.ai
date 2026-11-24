"""Compile model instructions into fixed, authorized ULR read operations."""
import json
import re
from collections import Counter
from unicodedata import normalize

from jsonschema import Draft202012Validator
from rest_framework.exceptions import PermissionDenied

from ai_engine.tools import GET_PRACTICE_QUESTIONS_SCHEMA, SEARCH_ASR_SCHEMA


NAME = 'run_course_tools'
PRACTICE_NAME = 'run_practice_tools'
CURRENT_COURSE_NAME = 'locate_current_course_transcript'
# Bump when the instruction grammar or its bound operation contracts change.
VERSION = 18
# Earlier versions with the same operations may still echo version and rank.
LEGACY_VERSION = 6
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
SELECTION_RULE = '内核按原话绑定明确选中的序号。只有排除或选择有歧义时，请用户确认。未指定序号时要求唯一匹配。'
MAX_RANKS = {NAME: 10, PRACTICE_NAME: 15}
_ORDINALS = ('一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '十一', '十二', '十三', '十四', '十五')
_ENGLISH_ORDINALS = ('first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'tenth',
                     'eleventh', 'twelfth', 'thirteenth', 'fourteenth', 'fifteenth')


def requested_rank(message, practice):
    message = normalize('NFKC', message)
    maximum_rank = MAX_RANKS[PRACTICE_NAME if practice else NAME]
    chinese_unit = r'(?:项|个(?:相关|匹配的?)?知识点)' if practice else r'门(?:相关|匹配的?)?课(?:程)?'
    english_unit = r'(?:knowledge point|result)' if practice else r'course'
    chinese_action = r'选(?:择)?|用|看|查(?:找)?|读(?:取)?|打开'
    english_action = r'use|choose|select|read|look up|open'
    english_exclusion = rf"skip|avoid|exclude|(?:do not|don['’]t|not)(?:\s+(?:{english_action}))?"
    chinese = re.finditer(
        rf'(?:(?P<exclude>不要|别|跳过|排除|不(?:{chinese_action}))\s*(?:先\s*)?(?:{chinese_action})?\s*'
        rf'|(?P<select>{chinese_action})\s*)?第\s*(?P<rank>[0-9]+|[零〇一二两三四五六七八九十百千万亿]+)\s*{chinese_unit}'
        rf'(?P<after>\s*(?:先)?(?:不要|跳过|不(?:{chinese_action}))(?=\s*(?:[，。；？！,.;?!]|$)))?', message)
    english = re.finditer(
        rf'\b(?:(?:(?P<exclude>{english_exclusion})'
        rf'|(?P<select>{english_action}))\s+(?:the\s+)?)?(?P<rank>{"|".join(_ENGLISH_ORDINALS)}|[0-9]+(?:st|nd|rd|th))'
        rf'\s+(?:(?:matching|relevant)\s+)?{english_unit}\b', message.lower())
    wanted, excluded = set(), set()
    explicit_choice = False
    for matches, words in ((chinese, _ORDINALS), (english, _ENGLISH_ORDINALS)):
        for match in matches:
            value = match['rank']
            if number := re.match(r'[0-9]+', value):
                digits = number[0].lstrip('0') or '0'
                rank = int(digits) if len(digits) <= len(str(maximum_rank)) else maximum_rank + 1
            else:
                rank = words.index(value) + 1 if value in words else maximum_rank + 1
            if match['exclude'] or match.groupdict().get('after'):
                excluded.add(rank)
            else:
                wanted.add(rank)
                explicit_choice |= bool(match['select'])
    needs_confirmation = len(wanted) > 1 or bool(wanted & excluded) or (bool(excluded) and not explicit_choice)
    return next(iter(wanted), None), needs_confirmation


def program_tool(name, required, properties, rules=''):
    return {'type': 'function', 'function': {
        'name': name,
        'description': f'{PROGRAM_DESCRIPTIONS[name]} 请单独提交。{rules}',
        'parameters': {'type': 'object', 'additionalProperties': False, 'required': [required], 'properties': properties},
    }}


FIND_PROPERTIES = {'find': {**TEXT, 'description': '要查找的课程或知识点'}, 'subject': TEXT}
QUERY_PROPERTY = {**TEXT, 'description': '讲稿关键词'}
LEGACY_OUTPUT = {'type': 'string', 'enum': ['card']}
TIMESTAMP_ONLY = re.compile(r'(?:^|[。！？.!?]\s*)(?:只(?:要|返回)(?:视频)?时间(?:点|戳)|'
                            r'(?:just|only) (?:the )?timestamps?)\s*[。.!！]?\s*$', re.IGNORECASE)
CURRENT_COURSE_LOCATOR = re.compile(r'\s*(?:请)?(?:帮我)?定位当前课程的(?P<query>[^。！？；，、,.!?;：:\n]+)讲稿\s*[。.!！]?\s*')
PRACTICE_ONLY = re.compile(r'(?:^|[。！？.!?]\s*)(?:只(?:要|发|返回)练习(?:题|卡)|'
                           r'(?:just|only) (?:the )?practice questions)\s*[。.!！]?\s*$', re.IGNORECASE)
_PRACTICE_COUNT = r'(?:\d+|[一二两三四五六七八九十百几]+)道'
_PRACTICE_ORDINAL = r'第[\d零〇一二两三四五六七八九十百千万亿]+项'
_PRACTICE_TOPIC = r'[^。！？；，、,.!?;：:\n]+'
PRACTICE_CARD_REQUEST = re.compile(
    rf'\s*(?:请)?(?:给我{_PRACTICE_COUNT}(?P<direct>{_PRACTICE_TOPIC})知识点的|'
    rf'先查(?P<lookup>{_PRACTICE_TOPIC})知识点[,，]\s*再根据{_PRACTICE_ORDINAL}(?:出|给我){_PRACTICE_COUNT})练习题'
    rf'(?:[。.!！,，]\s*(?:让我在卡片里作答|选择{_PRACTICE_ORDINAL}(?:[,，]\s*也选择{_PRACTICE_ORDINAL})?))?'
    r'\s*[。.!！]?\s*')
PROGRAM_TOOLS = {
    NAME: program_tool(NAME, 'find',
        {**FIND_PROPERTIES, 'query': {**QUERY_PROPERTY, 'description': '讲稿关键词，省略时沿用 find'},
         'limit': SEARCH_ASR_SCHEMA['properties']['limit']}, SELECTION_RULE),
    PRACTICE_NAME: program_tool(PRACTICE_NAME, 'find',
        {**FIND_PROPERTIES, **{field: GET_PRACTICE_QUESTIONS_SCHEMA['properties'][field]
                               for field in PRACTICE_FILTERS}}, SELECTION_RULE),
    CURRENT_COURSE_NAME: program_tool(CURRENT_COURSE_NAME, 'query',
        {'query': QUERY_PROPERTY, 'limit': SEARCH_ASR_SCHEMA['properties']['limit']}),
}


def compile_current_course_locator(message):
    delivery = TIMESTAMP_ONLY.search(message)
    if delivery and (locator := CURRENT_COURSE_LOCATOR.fullmatch(message[:delivery.start()])):
        literal = re.fullmatch(r'「([^「」]+)」', locator['query'].strip())
        if literal and (query := literal[1].strip()):
            return {'query': query}
    return None


def program_properties(name):
    properties = PROGRAM_TOOLS[name]['function']['parameters']['properties']
    return {**properties, 'output': LEGACY_OUTPUT}


def repair_program_tool(name, field):
    schema = ({'type': 'integer', 'minimum': 1, 'maximum': MAX_RANKS[name]}
              if field == 'rank' else program_properties(name)[field])
    return program_tool(name, field, {field: schema}, f'只提交修正后的 {field}，其余参数沿用原值。')


def duplicate_program_scope(name, raw_arguments, advertised):
    # Preserve every pair. A repeated field has no value until submitted again.
    try:
        pairs = json.loads(raw_arguments, object_pairs_hook=tuple)
    except (ValueError, TypeError, RecursionError):
        return None
    if not isinstance(pairs, tuple):
        return None
    if name == 'find_learning_tools':
        if sorted(field for field, _ in pairs) != ['instruction', 'program']:
            return None
        wrapper = dict(pairs)
        name, pairs = wrapper['program'], wrapper['instruction']
        if not isinstance(name, str) or name not in advertised or not isinstance(pairs, tuple):
            return None
    repeated = {field for field, count in Counter(field for field, _ in pairs).items() if count > 1}
    if 'v' in repeated:
        return name, {}, 'v'
    if len(repeated) != 1:
        return None
    field, = repeated
    if field not in program_properties(name) and not (field == 'rank' and name in MAX_RANKS):
        return None
    original = {key: value for key, value in pairs if key != field}
    if any(isinstance(value, (tuple, list)) for value in original.values()):
        return None
    return name, original, field


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
                        f'{SELECTION_RULE} '
                        '只传 program 可先查看指令契约。'),
        'parameters': {'type': 'object', 'additionalProperties': False,
            'properties': {**parameters['properties'], 'program': {'type': 'string', 'enum': program_names},
                           'instruction': {'type': 'object'}},
            'oneOf': [{'required': ['group'], 'not': {'required': ['instruction']}}, *programs]}}}


def valid_program_version(arguments):
    version = arguments.get('v', VERSION)
    return type(version) is int and LEGACY_VERSION <= version <= VERSION


def run_program(arguments, allowed_tools, execute, *, name=NAME, message='', current_course_id=None):
    operations = PROGRAM_OPS[name]
    second = operations[-1]
    anchored = name == CURRENT_COURSE_NAME
    practice = name == PRACTICE_NAME
    card_only = False
    collection, binding = ('results', 'knowledge_point_id') if practice else ('courses', 'course_id')

    def failure(code, message, *, repairable=False, **details):
        result = {'error': {'code': code, 'message': message, 'repairable': repairable}, 'steps_executed': [], **details}
        if card_only:
            result['_ulr_card_only'] = True
        return result

    if isinstance(arguments, dict) and not valid_program_version(arguments):
        return failure('stale_tool_version', '工具指令版本不符。', field='$.v', current_version=VERSION)
    schema = PROGRAM_TOOLS[name]['function']['parameters']
    properties = program_properties(name)
    if not anchored:
        maximum_rank = MAX_RANKS[name]
        properties = {**properties, 'rank': {'type': 'integer', 'minimum': 1, 'maximum': maximum_rank}}
    schema = {**schema, 'properties': properties}
    if isinstance(arguments, dict):
        arguments = arguments.copy()
        arguments.pop('v', None)
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

    if practice:
        card_only = PRACTICE_ONLY.search(message) is not None
        if not card_only and (request := PRACTICE_CARD_REQUEST.fullmatch(normalize('NFKC', message))):
            topic = (request['direct'] or request['lookup']).strip()
            query = normalize('NFKC', arguments['find']).strip()
            card_only = query in (topic, f'{topic}知识点')
    else:
        card_only = TIMESTAMP_ONLY.search(message) is not None
    if anchored and not card_only and (locator := CURRENT_COURSE_LOCATOR.fullmatch(message)):
        card_only = locator['query'].strip() == arguments['query'].strip()
    steps = []
    if anchored:
        if type(current_course_id) is not int or current_course_id < 1:
            return failure('missing_course_context', '请从目标课程页面重新发起提问。')
        source_id = current_course_id
    else:
        first = operations[0]
        rank, needs_confirmation = requested_rank(message, practice)
        if needs_confirmation:
            return failure('selection_needs_confirmation', '请用户确认要使用的课程或知识点。')
        if rank is not None and not 1 <= rank <= maximum_rank:
            return failure('rank_out_of_range', '用户指定的序号不在可查找的范围内。', field='$.rank',
                           minimum=1, maximum=maximum_rank)
        if rank is not None and arguments.get('rank', rank) != rank:
            return failure('rank_mismatch', '序号与用户明确指定的顺序不同。', field='$.rank', expected=rank, repairable=True)
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
    if card_only:
        result['_ulr_card_only'] = True
    return {**result, 'steps_executed': steps, '_ulr_source_id': source_id}
