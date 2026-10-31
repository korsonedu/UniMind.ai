"""Bounded teaching cards and the existing XiaoYu SSE contract, without model calls."""
import asyncio
from copy import deepcopy
import json
from unittest.mock import patch

import pytest
from rest_framework.exceptions import PermissionDenied, ValidationError

from ai_assistant.services.dsh_cards import build_learning_visual, PRESENTATION_TOOL
from ai_assistant.services.dsh_routing import grouped_tools
from ai_assistant.services.dsh_service import execute_tool, M0_TOOLS
from ai_assistant.services.dsh_xiaoyu import response


EXAMPLES = [
    {'type': 'latex_derivation', 'payload': {'title': '推导', 'steps': [{'latex': r'x<y', 'note': '说明'}]}},
    {'type': 'step_solution', 'payload': {'title': '步骤', 'steps': [{'text': '先移项', 'latex': 'x=1'}]}},
    {'type': 'function_graph', 'payload': {'expressions': [{'label': 'y=x', 'points': [{'x': 0, 'y': 0}, {'x': 1, 'y': 1}]}]}},
    {'type': 'action_cards', 'payload': {'cards': [{'title': '继续', 'description': '', 'icon': 'quiz', 'action': {'type': 'reply', 'url': '继续讲解', 'label': '继续'}}]}},
]


def test_visual_schema_and_navigation_bounds():
    for visual in EXAMPLES:
        assert build_learning_visual(visual) == visual
    invalid = []
    for mode, url in [('input', ''), ('rating', '评分：{rating}')]:
        visual = deepcopy(EXAMPLES[3])
        visual['payload']['cards'][0]['action'].update(reply_mode=mode, url=url)
        assert build_learning_visual(visual) == visual
        # The renderer only displays the first card in input/rating mode.
        for second in [deepcopy(visual['payload']['cards'][0]), {
            'title': '课程', 'description': '', 'icon': 'course',
            'action': {'type': 'navigate', 'url': '/courses', 'label': '课程'}}]:
            mixed = deepcopy(visual)
            mixed['payload']['cards'].append(second)
            invalid.append(mixed)
    for url in ('满意', '第1题评分：{rating}', '评分：5', '{rating}{rating}'):
        visual = deepcopy(EXAMPLES[3])
        visual['payload']['cards'][0]['action'].update(reply_mode='rating', url=url)
        invalid.append(visual)
    for kind, key, value in [(0, 'html', '<script>alert(1)</script>'), (2, 'formula', 'x*x')]:
        visual = deepcopy(EXAMPLES[kind])
        visual['payload'][key] = value
        invalid.append(visual)
    visual = deepcopy(EXAMPLES[2])
    visual['payload']['expressions'][0]['points'][0]['y'] = float('nan')
    invalid.append(visual)
    visual = deepcopy(EXAMPLES[2])
    visual['payload']['expressions'][0]['points'] *= 51
    invalid.append(visual)
    visual = deepcopy(EXAMPLES[0])
    visual['payload']['steps'] = [{'latex': 'x' * 1800}] * 12
    invalid.append(visual)
    for link in ('https://example.com', '//example.com', '/admin', '/course/1?redirect=//example.com'):
        visual = deepcopy(EXAMPLES[3])
        visual['payload']['cards'][0]['action'].update(type='navigate', url=link)
        invalid.append(visual)
    for formula in (r'\href{https://example.com}{x}', '<img src=x onerror=alert(1)>'):
        visual = deepcopy(EXAMPLES[0])
        visual['payload']['steps'][0]['latex'] = formula
        invalid.append(visual)
    for visual in invalid:
        with pytest.raises(ValidationError):
            build_learning_visual(visual)
    visual = deepcopy(EXAMPLES[3])
    visual['payload']['cards'][0]['action'].update(type='navigate', url='/course/1')
    assert build_learning_visual(visual) == visual


def test_discovery_is_not_business_execution():
    assert len(M0_TOOLS) == 21
    selected, groups, initial = grouped_tools([PRESENTATION_TOOL], '解释一下')
    assert initial == '' and set(groups) == {'presentation'}
    assert selected[0]['function']['name'] == 'find_learning_tools'
    with patch('ai_assistant.services.dsh_service.permitted_tools', return_value=[PRESENTATION_TOOL]), \
            patch('ai_assistant.services.dsh_service.memory_snapshot', return_value={'version': 'same'}):
        result = execute_tool(None, 'present_learning_visual', EXAMPLES[0], 'same')
        assert result == {'presented': True, 'visual': EXAMPLES[0]}
        with pytest.raises(PermissionDenied):
            execute_tool(None, 'find_learning_tools', {'group': 'presentation'}, 'same')
        with pytest.raises(PermissionDenied):
            execute_tool(None, 'save_session_note', {}, 'same')


def test_sse_steps_preserve_call_ids_failures_and_final_content(settings):
    settings.UNIMIND_DSH_ENABLED = settings.UNIMIND_DSH_SITE_ENABLED = True
    frames = [
        {'type': 'step', 'step': 2},
        {'type': 'tool_status', 'call_id': 'ok', 'name': 'present_learning_visual', 'status': 'running'},
        {'type': 'tool_status', 'call_id': 'bad', 'name': 'search_courses', 'status': 'running'},
        {'type': 'tool_status', 'call_id': 'ok', 'name': 'present_learning_visual', 'status': 'succeeded'},
        {'type': 'text_delta', 'text': '最终正文'},
        {'type': 'done', 'result': {'done': True, 'full_content': '最终正文', 'metadata': {'dsh_cards': [EXAMPLES[0]]}}},
    ]
    async def fixture(_producer):
        for frame in frames:
            yield ('data: ' + json.dumps(frame) + '\n\n').encode()
    async def read(result):
        return [json.loads(chunk[6:]) async for chunk in result.streaming_content]
    with patch('ai_assistant.services.dsh_xiaoyu.stream_events', fixture):
        events = asyncio.run(read(response(None, None, None, '合成问题')))
    steps = [e for e in events if e.get('type') == 'step']
    assert [(s['call_id'], s['status']) for s in steps] == [('ok', 'running'), ('bad', 'running'), ('ok', 'succeeded'), ('bad', 'failed')]
    assert len({s['run_id'] for s in steps}) == 1 and all(s['round'] == 2 for s in steps)
    assert events[-1]['full_content'] == '最终正文'
    assert events[-1]['metadata']['dsh_cards'] == [EXAMPLES[0]]
    assert not any(e.get('type') == 'text_reset' for e in events[1:])
