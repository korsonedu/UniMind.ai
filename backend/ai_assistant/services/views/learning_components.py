"""Validate a small declarative component and derive checks from its actions."""
from hashlib import sha256
import json
import math
from pathlib import Path

from rest_framework.exceptions import ValidationError


def fields(properties, required):
    return {'type': 'object', 'additionalProperties': False, 'properties': properties, 'required': required}


def rows(item, maximum):
    return {'type': 'array', 'minItems': 1, 'maxItems': maximum, 'items': item}


KEY = {'type': 'string', 'pattern': '^[a-z][a-z0-9_]{0,19}$'}
LABEL = {'type': 'string', 'minLength': 1, 'maxLength': 140}
INTEGER = {'type': 'integer', 'minimum': -1000000, 'maximum': 1000000}
IDENTITY = {'id': KEY, 'label': LABEL}
SPEC = fields({
    'sliders': rows(fields({**IDENTITY, 'min': INTEGER, 'max': INTEGER, 'value': INTEGER},
                           ['id', 'label', 'min', 'max', 'value']), 3),
    'choices': rows(fields({**IDENTITY, 'options': rows(fields({'label': LABEL, 'value': INTEGER},
                      ['label', 'value']), 6)}, ['id', 'label', 'options']), 3),
    'zones': rows(fields(IDENTITY, ['id', 'label']), 4),
    'items': rows(fields({**IDENTITY, 'zone': KEY}, ['id', 'label', 'zone']), 6),
    'outputs': rows(fields({**IDENTITY, 'unit': {'type': 'string', 'maxLength': 20},
        'expression': {'description': '数字、控件ID、{"count":"分区ID"}、{"in_zone":["对象ID","分区ID"]}（1或0），或 {"op":"add|sub|mul|div","args":[左,右]}。'}},
        ['id', 'label', 'expression']), 4),
}, []) | {'description': '自由组合整数滑块、按钮参数选择、分区间移动的对象、计算或计数输出。'}


def catalog(user, query=''):
    from ai_assistant.models import LearningComponentTemplate
    return list(LearningComponentTemplate.objects.filter(owner=user, title__icontains=query)
                .order_by('-id').values('id', 'title')[:8])


def persist_template(user, item):
    from ai_assistant.models import LearningComponentTemplate
    specification = item['component']
    digest = sha256(json.dumps(specification, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    LearningComponentTemplate.objects.get_or_create(owner=user, digest=digest,
        defaults={'title': item['title'], 'specification': specification})


def template_for(user, template_id):
    from ai_assistant.models import LearningComponentTemplate
    item = LearningComponentTemplate.objects.filter(owner=user, pk=template_id).first()
    if item is None:
        raise ValidationError('找不到当前账号可用的交互模板。')
    return {'id': item.pk, 'title': item.title, 'component': item.specification}


def value_of(expression, values, counts, locations, depth=0):
    if depth > 5:
        raise ValidationError('计算表达式最多嵌套五层。')
    if type(expression) in (int, float) and -1e10 <= expression <= 1e10:
        return float(expression)
    if isinstance(expression, str) and expression in values:
        return float(values[expression])
    if isinstance(expression, dict) and set(expression) == {'count'}:
        zone = expression['count']
        if isinstance(zone, str) and zone in counts:
            return float(counts[zone])
    if isinstance(expression, dict) and set(expression) == {'in_zone'}:
        pair = expression['in_zone']
        if isinstance(pair, list) and len(pair) == 2 and all(isinstance(key, str) for key in pair):
            item, zone = pair
            if item in locations and zone in counts:
                return float(locations[item] == zone)
    if isinstance(expression, dict) and set(expression) == {'op', 'args'}:
        op, args = expression['op'], expression['args']
        if op in ('add', 'sub', 'mul', 'div') and isinstance(args, list) and len(args) == 2:
            left, right = (value_of(arg, values, counts, locations, depth + 1) for arg in args)
            if left is None or right is None:
                return None
            if op == 'add':
                return left + right
            if op == 'sub':
                return left - right
            if op == 'mul':
                return left * right
            return left / right if right else None
    raise ValidationError('计算只能引用已有控件、对象或分区，并使用 add、sub、mul、div。')


def display(value):
    if value is None or not -1e10 <= value <= 1e10:
        return '—'
    return f'{math.floor(value * 100 + .5) / 100:.2f}'


def compile_component(specification, saved_state):
    sliders, choices, zones, items, outputs = (
        specification.get(key, []) for key in ('sliders', 'choices', 'zones', 'items', 'outputs'))
    for collection in (sliders + choices, zones, items, outputs):
        if len({row['id'] for row in collection}) != len(collection):
            raise ValidationError('同一类组件中的 ID 必须唯一。')
    if len(sliders) + len(choices) > 3 or not (sliders or choices or items):
        raise ValidationError('交互规格至少需要一个操作，数字控件合计最多三个。')
    zone_ids = {row['id'] for row in zones}
    if bool(zones) != bool(items) or (items and (len(zones) < 2 or any(row['zone'] not in zone_ids for row in items))):
        raise ValidationError('移动对象需要至少两个分区，每个对象都要指定有效的初始分区。')
    initial_values = {}
    for row in sliders:
        if not row['min'] <= row['value'] <= row['max'] or row['min'] == row['max']:
            raise ValidationError('滑块初值须在不同的最小值与最大值之间。')
        initial_values[row['id']] = row['value']
    for row in choices:
        values = {item['value'] for item in row['options']}
        if len(values) < 2 or len(values) != len(row['options']):
            raise ValidationError('选择控件至少需要两个不同值。')
        initial_values[row['id']] = row['options'][0]['value']
    initial_zones = {row['id']: row['zone'] for row in items}
    values, locations = initial_values.copy(), initial_zones.copy()
    saved_values = saved_state.get('values')
    saved_locations = saved_state.get('locations')
    saved_values = saved_values if isinstance(saved_values, dict) else {}
    saved_locations = saved_locations if isinstance(saved_locations, dict) else {}
    for row in sliders:
        previous = saved_values.get(row['id'])
        if type(previous) in (int, float) and row['min'] <= previous <= row['max'] and previous % 1 == 0:
            values[row['id']] = int(previous)
    for row in choices:
        previous = saved_values.get(row['id'])
        if type(previous) in (int, float) and previous in {opt['value'] for opt in row['options']}:
            values[row['id']] = int(previous)
    for row in items:
        previous = saved_locations.get(row['id'])
        if isinstance(previous, str) and previous in zone_ids:
            locations[row['id']] = previous

    def expected():
        counts = {zone: sum(place == zone for place in locations.values()) for zone in zone_ids}
        conditions = [f':has(#lc-value-{key}[data-value="{value}"])' for key, value in values.items()]
        conditions += [f':has(#lc-zone-{zone} #lc-item-{key})' for key, zone in locations.items()]
        for row in outputs:
            rendered = display(value_of(row['expression'], values, counts, locations))
            conditions.append(f':has(#lc-output-{row["id"]}[data-value="{rendered}"])')
        return '#lc-component' + ''.join(conditions)

    starting = expected()
    checks = []
    if values != initial_values or locations != initial_zones:
        values, locations = initial_values.copy(), initial_zones.copy()
        checks.append({'selector': '#lc-reset', 'action': 'click', 'expect_selector': expected()})
    for row in sliders:
        key = row['id']
        values[key] = row['max'] if values[key] != row['max'] else row['min']
        checks.append({'selector': f'#lc-control-{key}', 'action': 'input', 'value': str(values[key]),
                       'expect_selector': expected()})
    for row in choices:
        key = row['id']
        index, option = next((i, option) for i, option in enumerate(row['options']) if option['value'] != values[key])
        values[key] = option['value']
        checks.append({'selector': f'#lc-option-{key}-{index}', 'action': 'click', 'expect_selector': expected()})
    if items:
        key = items[0]['id']
        target = next(row['id'] for row in zones if row['id'] != locations[key])
        locations[key] = target
        checks.append({'selector': f'#lc-move-{key}-{target}', 'action': 'click', 'expect_selector': expected()})
    values, locations = initial_values, initial_zones
    reset = expected()
    if checks[0]['selector'] != '#lc-reset':
        checks.append({'selector': '#lc-reset', 'action': 'click', 'expect_selector': reset})
    # Data is parsed inside the sandbox. Escaping "<" keeps text from closing the script element.
    data = json.dumps({'specification': specification}, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c')
    renderer = Path(__file__).with_name('learning_component_renderer.js').read_text()
    html = f'<main id="lc-component"></main><script type="application/json" id="lc-spec">{data}</script><script>{renderer}</script>'
    return html, checks, starting
