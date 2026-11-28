"""Prototype smoke: one chat's source/state, revision updates and access boundary."""
from unittest.mock import patch
from contextlib import ExitStack
from uuid import uuid4
import asyncio
import base64
import hashlib
import json
import struct

import pytest
from rest_framework.exceptions import NotFound, PermissionDenied

from ai_assistant.models import AIChatMessage, Bot
from ai_assistant.services import learning_experiments as experiments


@pytest.mark.django_db
def test_interaction_is_discoverable_without_keywords_and_respects_text_only(user, settings):
    from ai_assistant.services.dsh_service import build_context
    settings.DEBUG = settings.UNIMIND_LEARNING_EXPERIMENTS_PROTOTYPE = True
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    user.is_member = True
    user.save(update_fields=['is_member'])
    bot = Bot.objects.create(name='小宇', bot_type='planner')
    current = AIChatMessage.objects.create(user=user, bot=bot, role='user', content='')
    claims = {'message_id': current.pk, 'conversation_id': str(current.conversation_id), 'bot_id': bot.pk}
    arguments = {'title': '合成讲解', 'html': '<button id="go">观察</button>',
        'checks': [{'selector': '#go', 'action': 'click', 'expect_selector': '#go', 'expect_text': '观察'}]}
    for text, first_round in [
        ('把动物脚印拖到对应的动物旁边', True),
        ('解答这道题时能不能让我拨动利率，看看价格怎么变', False),
        ('统计本周做题情况', False),
        ('出一道高中物理大题（带图）', False),
    ]:
        current.content = text
        current.save(update_fields=['content'])
        context = build_context(user, text, chat_context=claims)
        tools = {tool['function']['name'] for tool in context['tools']}
        assert 'find_learning_tools' in tools
        assert ('build_learning_experiment' in tools) is first_round
        assert 'build_learning_experiment' in {
            tool['function']['name'] for tool in context['tool_groups']['authoring']['tools']}
    current.content = '不要交互，解释久期'
    current.save(update_fields=['content'])
    context = build_context(user, current.content, chat_context=claims)
    assert 'interactive' not in context['tool_groups']
    assert 'build_learning_experiment' not in {tool['function']['name'] for tool in context['available_tools']}
    with patch.object(experiments, 'preview') as preview:
        with pytest.raises(PermissionDenied):
            experiments.execute(user, 'build_learning_experiment', arguments, claims)
        preview.assert_not_called()
    followup = AIChatMessage.objects.create(user=user, bot=bot, conversation_id=current.conversation_id,
        role='user', content='继续')
    assert not experiments.allows_interaction(followup)


@pytest.mark.django_db
@pytest.mark.parametrize('planning', [False, True], ids=['free-chat', 'planning-project'])
@pytest.mark.parametrize(('text', 'initial_group'), [
    ('对于中央银行的资产负债表，你可以做一个可视化的演示让我学一下吗', 'authoring'),
    ('画个图讲这道债券题', 'interactive'),
], ids=['central-bank-demo', 'question-diagram'])
def test_visual_demo_offers_experiment_on_first_request(user, settings, planning, text, initial_group):
    from ai_assistant.models import Conversation, ConversationProject, ProjectLearning
    from ai_assistant.services.dsh_service import build_context

    settings.UNIMIND_LEARNING_EXPERIMENTS_ENABLED = True
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    user.is_member = True
    user.save(update_fields=['is_member'])
    bot = Bot.objects.create(name='小宇', bot_type='planner')
    current = AIChatMessage.objects.create(user=user, bot=bot, role='user', content=text)
    if planning:
        project = ConversationProject.objects.create(user=user, name='中央银行')
        conversation = Conversation.objects.create(user=user, bot=bot, project=project,
            conversation_id=current.conversation_id)
        ProjectLearning.objects.create(project=project, planning_enabled=True, last_conversation=conversation)
    claims = {'message_id': current.pk, 'conversation_id': str(current.conversation_id), 'bot_id': bot.pk}

    assert experiments.allows_interaction(current)
    context = build_context(user, text, chat_context=claims)
    assert ('project' in context['tool_groups']) is planning
    assert context['routing']['initial_group'] == initial_group
    assert 'build_learning_experiment' in {tool['function']['name'] for tool in context['tools']}
    assert '自主交互讲解' in context['system_prompt']
    assert context['model_policy']['max_requests'] == 6
    refreshed = build_context(user, text, recent_messages=[{'role': 'assistant', 'content': '你也可以做几道练习题。'}],
        chat_context=claims)
    assert refreshed['permissions_version'] == context['permissions_version']
    assert refreshed['system_prompt'] == context['system_prompt']


@pytest.mark.django_db
def test_experiment_chat_state_and_revision(user, auth_client, settings):
    settings.DEBUG = settings.UNIMIND_LEARNING_EXPERIMENTS_PROTOTYPE = True
    user.is_member = True
    user.save(update_fields=['is_member'])
    bot = Bot.objects.create(name='小宇', bot_type='planner', system_prompt='冒烟')
    message = AIChatMessage.objects.create(user=user, bot=bot, role='user', content='解释利率与价格')
    claims = {'message_id': message.pk, 'conversation_id': str(message.conversation_id), 'bot_id': bot.pk}
    source = {'title': '债券实验', 'html': '<input id="rate"><output id="price"></output>',
        'checks': [{'selector': '#rate', 'action': 'input', 'value': '5', 'expect_selector': '#price', 'expect_text': '99'}]}
    with patch.object(experiments, 'preview', return_value={'ok': True, 'checks': []}):
        result = experiments.execute(user, 'build_learning_experiment', source, claims)
        experiment_id = result['experiment_id']
        assert result['visual']['type'] == 'learning_experiment'
        url = f'/api/ai/learning-experiments/{message.conversation_id}/{experiment_id}/'
        assert auth_client.get(url).status_code == 200
        response = auth_client.patch(url, {'revision': 1, 'state_version': 0, 'state': {'rate': 5}}, format='json')
        assert response.status_code == 200 and response.json()['state_version'] == 1
        assert auth_client.patch(url, {'revision': 1, 'state_version': 0, 'state': {}}, format='json').status_code == 409
        stored = experiments.execute(user, 'read_learning_experiment', {'experiment_id': experiment_id}, claims)
        assert stored['state'] == {'rate': 5}
        updated = experiments.execute(user, 'build_learning_experiment', {
            **source, 'experiment_id': experiment_id, 'base_revision': 1, 'title': '增加票息'}, claims)
        assert updated['experiment_id'] == experiment_id and updated['revision'] == 2
        current = auth_client.get(url).json()
        assert current['state'] == {'rate': 5} and '"rate": 5' in current['document']
        assert current['revision'] == 2
    with patch.object(experiments, 'preview', return_value={'ok': False, 'errors': ['语法错误']}):
        failed = experiments.execute(user, 'build_learning_experiment', {
            **source, 'experiment_id': experiment_id, 'base_revision': 2}, claims)
        assert 'error' in failed and 'visual' not in failed
        assert auth_client.get(url).json()['revision'] == 2
    other = type(user).objects.create_user(username='experiment-other', is_member=True)
    auth_client.force_authenticate(user=other)
    assert auth_client.get(url).status_code == 404
    assert auth_client.patch(url, {'revision': 2, 'state_version': 1, 'state': {}}, format='json').status_code == 404
    settings.DEBUG = False
    auth_client.force_authenticate(user=user)
    assert auth_client.get(url).status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize('identifiers', [
    {'experiment_id': '11111111-1111-4111-8111-111111111111', 'base_revision': 1},
    {'experiment_id': '11111111-1111-4111-8111-111111111111'},
    {'base_revision': 99},
])
def test_first_experiment_ignores_caller_identifiers(user, settings, identifiers):
    settings.DEBUG = settings.UNIMIND_LEARNING_EXPERIMENTS_PROTOTYPE = True
    user.is_member = True
    user.save(update_fields=['is_member'])
    bot = Bot.objects.create(name='小宇', bot_type='planner')
    message = AIChatMessage.objects.create(user=user, bot=bot, role='user', content='解释久期')
    claims = {'message_id': message.pk, 'conversation_id': str(message.conversation_id), 'bot_id': bot.pk}
    arguments = {'title': '久期实验', 'html': '<button id="run">运行</button>', **identifiers,
        'checks': [{'selector': '#run', 'action': 'click', 'expect_selector': '#run', 'expect_text': '运行'}]}
    with patch.object(experiments, 'preview', return_value={'ok': True, 'checks': []}) as preview:
        result = experiments.execute(user, 'build_learning_experiment', arguments, claims)
    assert result['experiment_id'] != '11111111-1111-4111-8111-111111111111'
    assert result['revision'] == 1
    assert result['visual']['payload']['experiment_id'] == result['experiment_id']
    assert all(arguments[key] == value for key, value in identifiers.items())
    assert preview.call_args.args[1] == {}
    message.refresh_from_db()
    assert set(message.metadata['learning_experiments']) == {result['experiment_id']}
    assert message.metadata['learning_experiments'][result['experiment_id']]['revision'] == 1


@pytest.mark.django_db
def test_experiment_attachment_and_disabled_default(user, settings):
    from ai_assistant.services.tool_executor import PlannerToolExecutor, set_permitted_tools
    settings.DEBUG = settings.UNIMIND_LEARNING_EXPERIMENTS_PROTOTYPE = True
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    user.is_member = True
    user.save(update_fields=['is_member'])
    bot = Bot.objects.create(name='小宇', bot_type='planner', system_prompt='冒烟')
    current = AIChatMessage.objects.create(user=user, bot=bot, role='user', content='我还没理解')
    executor = PlannerToolExecutor(user)
    set_permitted_tools(executor, [])
    messages = [{'role': 'system', 'content': '小宇'}]
    tools = experiments.attach_to_chat(user, current, messages, [], executor)
    assert {item['function']['name'] for item in tools} == {
        'build_learning_experiment', 'read_learning_experiment', 'register_session_tool', 'read_session_tool'}
    assert '自主交互讲解' in messages[0]['content']
    assert executor.experiment_context['message_id'] == current.pk
    arguments = {'title': '已有实验', 'html': '<button id="run">运行</button>',
        'checks': [{'selector': '#run', 'action': 'click', 'expect_selector': 'body', 'expect_text': '运行'}]}
    with patch.object(experiments, 'preview', return_value={'ok': True, 'checks': []}):
        existing = experiments.execute(user, 'build_learning_experiment', arguments, executor.experiment_context)
    with patch.object(experiments, 'preview') as preview:
        invalid = json.loads(executor('build_learning_experiment', {
            **arguments, 'experiment_id': str(uuid4()), 'base_revision': 1}))
        preview.assert_not_called()
    assert '必须省略 experiment_id 和 base_revision' in invalid['error']
    assert not executor.pending_visuals
    current.refresh_from_db()
    assert set(current.metadata['learning_experiments']) == {existing['experiment_id']}
    current.content = '不要交互，解释久期'
    set_permitted_tools(executor, [])
    messages = [{'role': 'system', 'content': '小宇'}]
    tools = experiments.attach_to_chat(user, current, messages, [], executor)
    assert {item['function']['name'] for item in tools} == {
        'read_learning_experiment', 'register_session_tool', 'read_session_tool'}
    assert '自主交互讲解' not in messages[0]['content']
    assert '当前对话内动态计算工具' in messages[0]['content']
    settings.UNIMIND_LEARNING_EXPERIMENTS_PROTOTYPE = False
    assert not experiments.available_to(user)
    with pytest.raises(NotFound):
        experiments.anchor_for(user, current.conversation_id)


def test_experiment_document_is_opaque_and_state_is_escaped():
    document = experiments.experiment_document('<button>操作</button>', {'text': '</script><script>bad()</script>'})
    assert "connect-src 'none'" in document and "form-action 'none'" in document
    assert "default-src 'none'" in document
    assert '</script><script>bad()' not in document
    assert 'window.unimind' in document


@pytest.mark.parametrize('capture_screenshots', [False, True])
def test_tall_balance_sheet_preview_and_screenshots(capture_screenshots):
    from ai_assistant.services.learning_experiment_preview import run
    html = '''
<style>
.um-controls { grid-template-columns: 1fr; gap: 16px; padding: 16px; }
.um-result-main b { display: block; }
</style>
<div class="um-layout">
  <div class="um-controls">
    <label>持有国债（亿元）<i></i>
      <input id="bonds" type="range" min="0" max="800" step="50" value="400">
    </label>
    <label>对银行贷款（亿元）<i></i>
      <input id="loans" type="range" min="0" max="800" step="50" value="200">
    </label>
    <label>外汇资产（亿元）<i></i>
      <input id="foreign-assets" type="range" min="0" max="800" step="50" value="300">
    </label>
    <label>流通中现金（亿元）<i></i>
      <input id="cash" type="range" min="0" max="800" step="50" value="500">
    </label>
    <label>银行准备金（亿元）<i></i>
      <input id="reserves" type="range" min="0" max="800" step="50" value="300">
    </label>
    <div class="um-result-main">净资产（资产减负债）<b id="result"></b></div>
  </div>
  <div class="um-stage"><div id="chart"></div></div>
</div>
<script>
const controls = [...document.querySelectorAll('input')];
function draw() {
  const [bonds, loans, foreignAssets, cash, reserves] = controls.map(control => {
    control.closest('label').querySelector('i').textContent = control.value;
    return Number(control.value);
  });
  const assets = bonds + loans + foreignAssets, liabilities = cash + reserves;
  document.querySelector('#result').textContent = `${assets - liabilities} 亿元`;
  unimind.chart(document.querySelector('#chart'), {
    type: 'bar', labels: ['资产', '负债'],
    series: [{label: '央行资产负债表', values: [assets, liabilities]}],
    yLabel: '金额（亿元）'
  });
}
controls.forEach(control => control.addEventListener('input', draw));
draw();
</script>'''
    changes = [('bonds', '500', 200), ('loans', '250', 250), ('foreign-assets', '350', 300),
        ('cash', '550', 250), ('reserves', '350', 200)]
    report = run({'document': experiments.experiment_document(html, {}), 'capture_screenshots': capture_screenshots,
        'checks': [{'selector': f'#{control}', 'action': 'input', 'value': value,
            'expect_selector': '#result', 'expect_text': f'{expected} 亿元'} for control, value, expected in changes]})
    assert report['ok'] is True, report
    assert not report['errors']
    assert report['checks'] == [{'selector': f'#{control}', 'ok': True} for control, _, _ in changes]
    if not capture_screenshots:
        assert 'screenshots' not in report
        return
    frames = report['screenshots']
    assert [(frame['id'], frame['width']) for frame in frames] == [
        ('initial-700', 700), ('initial-360', 360),
        *((f'check-{index}-700', 700) for index in range(1, 6)), ('final-360', 360),
    ]
    for frame in frames:
        assert (360 if frame['width'] == 700 else 540) < frame['height'] < 800
        raw = base64.b64decode(frame['png'], validate=True)
        assert raw.startswith(b'\x89PNG\r\n\x1a\n')
        assert struct.unpack('>II', raw[16:24]) == (frame['width'], frame['height'])
        assert hashlib.sha256(raw).hexdigest() == frame['sha256']
        assert len(raw) == frame['bytes']


def test_preview_rejects_javascript_runtime_error():
    from ai_assistant.services.learning_experiment_preview import run
    html = '''<button onclick="this.textContent = '已操作'; throw Error('运行失败')">操作</button>'''
    report = run({'document': experiments.experiment_document(html, {}), 'checks': [
        {'selector': 'button', 'action': 'click', 'expect_selector': 'button', 'expect_text': '已操作'},
    ]})
    assert report['ok'] is False
    assert report['checks'] == [{'selector': 'button', 'ok': True}]
    assert '运行失败' in report['errors']


@pytest.mark.parametrize('expected', ['已操作', ''])
def test_preview_rejects_failed_control_check(expected):
    from ai_assistant.services.learning_experiment_preview import run
    report = run({'document': experiments.experiment_document('<button>操作</button>', {}), 'checks': [
        {'selector': 'button', 'action': 'click', 'expect_selector': 'button', 'expect_text': expected},
    ]})
    assert report['ok'] is False
    assert not report['errors']
    assert report['checks'][0]['ok'] is False
    assert report['checks'][0]['observed'] == {'matches': 1, 'text': '操作'}


def test_preview_checks_a_tile_moving_between_regions():
    from ai_assistant.services.learning_experiment_preview import run
    from ai_engine.tool_run import validate_declared_arguments

    html = '''<div id="pool"><button id="first-tile">Nice to meet you!</button></div>
    <section id="order"></section><button id="reset">重置</button>
    <script>
    const tile = document.querySelector('#first-tile');
    const pool = document.querySelector('#pool');
    const order = document.querySelector('#order');
    tile.onclick = () => order.append(tile);
    document.querySelector('#reset').onclick = () => pool.append(tile);
    </script>'''
    checks = [
        {'selector': '#pool #first-tile', 'action': 'click', 'expect_selector': '#order #first-tile'},
        {'selector': '#reset', 'action': 'click', 'expect_selector': '#order', 'expect_text': ''},
    ]
    schema = experiments.EXPERIMENT_TOOLS[0]['function']['parameters']
    assert validate_declared_arguments(schema, {'title': '对话排序', 'html': html, 'checks': checks}) is None
    document = experiments.experiment_document(html, {})
    assert run({'document': document, 'checks': checks})['ok']
    already_visible = {**checks[0], 'expect_selector': '#pool #first-tile'}
    report = run({'document': document, 'checks': [already_visible]})
    assert not report['ok'] and report['checks'][0]['phase'] == 'precondition'


def test_preview_rejects_blank_render():
    from ai_assistant.services.learning_experiment_preview import run
    html = '<button style="display:none">操作</button>'
    report = run({'document': experiments.experiment_document(html, {}), 'checks': []})
    assert report['ok'] is False
    assert any('没有可见内容' in error for error in report['errors'])


def test_browser_failure_reaches_model_and_mount_finishes_turn(monkeypatch):
    from ai_engine.service import AIEngine
    diagnostics = {'ok': False, 'errors': ['讲解卡片在 360px 宽度下没有可见内容。'], 'checks': []}
    requests, executions, events = [], [], []
    definition = {'type': 'function', 'function': {'name': 'build_learning_experiment',
        'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False}}}

    class Stream:
        def raise_for_status(self):
            pass

        def iter_lines(self, **kwargs):
            yield 'data: ' + json.dumps({'choices': [{'delta': {'tool_calls': [{
                'index': 0, 'id': f'call-{len(requests)}', 'type': 'function',
                'function': {'name': 'build_learning_experiment', 'arguments': '{}'}}]}, 'finish_reason': 'tool_calls'}]})
            yield 'data: [DONE]'

    def post(*args, **kwargs):
        requests.append(kwargs['json']['messages'])
        if len(requests) == 2:
            returned = next(message for message in reversed(requests[-1]) if message['role'] == 'tool')
            assert json.loads(returned['content'])['preview'] == diagnostics
        return Stream()

    def execute(name, args):
        executions.append(name)
        if len(executions) == 1:
            return json.dumps({'error': '实验检查失败', 'preview': diagnostics})
        return json.dumps({'visual': {'type': 'learning_experiment', 'payload': {'title': '已修正'}}})

    monkeypatch.setattr('ai_engine.service._session.post', post)
    monkeypatch.setattr('ai_engine.service.get_model_for_task', lambda operation: {
        'api_key': 'synthetic-key', 'base_url': 'https://example.invalid/chat', 'model': 'synthetic', 'thinking': None})
    monkeypatch.setattr('ai_engine.circuit_breaker.AICircuitBreaker.check', lambda *args, **kwargs: None)
    monkeypatch.setattr('ai_engine.circuit_breaker.AICircuitBreaker.record_success', lambda *args, **kwargs: None)
    result = AIEngine.call_ai_with_streaming_tools(messages=[{'role': 'user', 'content': '修复实验'}],
        tools=[definition], tool_executor=execute, on_step=events.append, max_tool_rounds=3)
    assert len(requests) == len(executions) == 2
    assert result['finish_reason'] == 'stop' and result['content'] == ''
    assert [event['status'] for event in events if event.get('status') in ('failed', 'succeeded')] == ['failed', 'succeeded']


@pytest.mark.django_db(transaction=True)
def test_existing_chat_stream_mounts_experiment(user, auth_client, settings):
    from users.models import WeeklyAIQuotaConfig, AIUsageReservation
    settings.DEBUG = settings.UNIMIND_LEARNING_EXPERIMENTS_PROTOTYPE = True
    settings.UNIMIND_DSH_XIAOYU_ENABLED = False
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    user.is_member = True
    user.save(update_fields=['is_member'])
    WeeklyAIQuotaConfig.objects.update_or_create(pk=1, defaults={'experience_calls': 20, 'course_calls': 200})
    bot = Bot.objects.create(is_xiaoyu=True, name='小宇', bot_type='planner', system_prompt='冒烟')
    conversation_id = str(uuid4())

    def model(**kwargs):
        assert kwargs['max_tokens'] == 8192
        executor = kwargs['tool_executor']
        result = json.loads(executor('build_learning_experiment', {
            'title': '对话内实验', 'html': '<button id="run">运行</button><output id="result">2</output>',
            'checks': [{'selector': '#run', 'action': 'click', 'expect_selector': '#result', 'expect_text': '2'}]}))
        assert result['visual']['type'] == 'learning_experiment'
        return {'content': '', 'finish_reason': 'stop'}

    async def read(response):
        return b''.join([chunk async for chunk in response.streaming_content]).decode()

    with ExitStack() as stack:
        for target in ('ai_assistant.services.memory_service.extract_memories_async',
                       'ai_assistant.services.memory_service.extract_memories_with_mem0',
                       'ai_assistant.services.trajectory_recorder.record_trajectory'):
            stack.enter_context(patch(target))
        stack.enter_context(patch('ai_assistant.services.memory_service.build_memory_context', return_value=('', '')))
        stack.enter_context(patch('ai_assistant.services.title_generator.sync_generate_title', return_value='实验冒烟'))
        stack.enter_context(patch('ai_engine.tool_router.route_tools', side_effect=lambda message, tools, **kwargs: tools))
        stack.enter_context(patch('ai_assistant.services.experience_applicator.get_applicable_experiences', return_value=[]))
        stack.enter_context(patch('ai_engine.service.AIEngine.call_ai_with_streaming_tools', side_effect=model))
        stack.enter_context(patch.object(experiments, 'preview', return_value={'ok': True, 'checks': []}))
        stack.enter_context(patch('requests.sessions.Session.request', side_effect=AssertionError('No external calls in smoke')))
        response = auth_client.post('/api/ai/chat/stream/', {'message': '这个关系我还没理解',
            'bot_id': bot.pk, 'conversation_id': conversation_id, 'request_id': str(uuid4())}, format='json')
        assert response.status_code == 200
        stream = asyncio.run(read(response))
    events = [json.loads(line[6:]) for line in stream.splitlines() if line.startswith('data: ')]
    done = next(event for event in events if event.get('done'))
    assert not done['is_error'] and done['metadata']['visual']['type'] == 'learning_experiment'
    assert AIChatMessage.objects.get(pk=done['message_id']).metadata['visual']['payload']['conversation_id'] == conversation_id
    assert AIUsageReservation.objects.get(user=user).status == 'succeeded'
