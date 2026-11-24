"""Local smoke: real isolated JS plus a simulated model tool-call protocol."""
from copy import deepcopy
import json
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync
import pytest

from ai_assistant.models import AIChatMessage, Bot, Conversation
from ai_assistant.services.learning_experiments import attach_to_chat
from ai_assistant.services.tool_executor import PlannerToolExecutor, set_permitted_tools


REGISTRATION = {'name': 'session_product', 'description': '计算两个数的乘积',
    'parameters': {'type': 'object', 'additionalProperties': False,
        'properties': {'a': {'type': 'number', 'minimum': 0}, 'b': {'type': 'number'}}, 'required': ['a', 'b']},
    'source': 'function run(input) { return {product: input.a * input.b}; }',
    'tests': [{'input': {'a': 6, 'b': 7}, 'expected': {'product': 42}}]}


@pytest.fixture
def tool_chat(user, settings):
    settings.DEBUG = settings.UNIMIND_LEARNING_EXPERIMENTS_PROTOTYPE = True
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    user.is_member = True
    user.save(update_fields=['is_member'])
    bot = Bot.objects.create(name='小宇', bot_type='planner', system_prompt='会话工具冒烟')
    current = AIChatMessage.objects.create(user=user, bot=bot, role='user', content='需要一个计算工具')
    return user, bot, current


def chat_executor(user, current):
    executor = PlannerToolExecutor(user)
    set_permitted_tools(executor, [])
    tools = attach_to_chat(user, current, [{'role': 'system', 'content': '小宇'}], [], executor)
    executor._allowed_tool_names = {tool['function']['name'] for tool in tools}
    return executor, tools


@pytest.mark.django_db
def test_interactive_question_tools_are_visible_together(tool_chat, settings):
    from ai_assistant.services.dsh_service import build_context
    user, bot, current = tool_chat
    claims = {'message_id': current.pk, 'conversation_id': str(current.conversation_id), 'bot_id': bot.pk}
    current.content = '给我讲一道金融硕士题目，用到交互'
    current.save(update_fields=['content'])
    context = build_context(user, current.content, chat_context=claims)
    assert context['routing']['initial_group'] == 'interactive'
    names = {tool['function']['name'] for tool in context['tools']}
    assert {'get_practice_questions', 'lookup_question', 'build_learning_experiment'} <= names
    assert len(names) <= 8
    settings.UNIMIND_LEARNING_EXPERIMENTS_PROTOTYPE = False
    assert 'interactive' not in build_context(user, current.content, chat_context=claims)['tool_groups']


@pytest.mark.django_db
def test_dsh_registry_revision_and_scope(tool_chat, settings):
    from rest_framework.exceptions import APIException
    from ai_assistant.services.dsh_service import build_context, execute_tool
    user, bot, current = tool_chat
    claims = {'message_id': current.pk, 'conversation_id': str(current.conversation_id), 'bot_id': bot.pk}
    before = build_context(user, current.content, chat_context=claims)
    assert before['routing']['initial_group'] == 'authoring'
    assert before['model_policy']['max_requests'] == 6
    assert 'register_session_tool' in {tool['function']['name'] for tool in before['tools']}
    version = before['memory']['version']
    result = execute_tool(user, 'register_session_tool', REGISTRATION, version, chat_context=claims)
    assert result['registered'] and result['session_registry']['versions'] == {'session_product': 1}
    after = build_context(user, current.content, chat_context=claims)
    assert before['permissions_version'] == after['permissions_version']
    assert before['system_prompt'] == after['system_prompt']
    assert len(after['tool_groups']['session']['tools']) == 2
    assert execute_tool(user, 'session_product', {'a': 6, 'b': 7}, version,
                        chat_context=claims, tool_revision=1)['result']['product'] == 42
    following = AIChatMessage.objects.create(user=user, bot=bot, role='user', content='另一对话')
    foreign = {**claims, 'message_id': following.pk, 'conversation_id': str(following.conversation_id)}
    with patch('ai_assistant.services.session_tools.run_code') as worker:
        for context, revision in [(None, 1), (foreign, 1), (claims, None), (claims, 2)]:
            with pytest.raises(APIException):
                execute_tool(user, 'session_product', {'a': 6, 'b': 7}, version,
                             chat_context=context, tool_revision=revision)
        settings.UNIMIND_LEARNING_EXPERIMENTS_PROTOTYPE = False
        disabled = build_context(user, current.content, chat_context=claims)
        assert 'session_registry' not in disabled and disabled['model_policy']['max_requests'] == 4
        with pytest.raises(APIException):
            execute_tool(user, 'register_session_tool', REGISTRATION, version, chat_context=claims)
        worker.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_ulr_discards_a_calculation_if_the_tool_changes_before_reply(tool_chat, auth_client, settings):
    from users.models import WeeklyAIQuotaConfig, WeeklyAIUsage

    user, bot, anchor = tool_chat
    settings.UNIMIND_ULR_PROTOTYPE = True
    settings.UNIMIND_DSH_ENABLED = settings.UNIMIND_DSH_SITE_ENABLED = False
    Conversation.objects.create(user=user, bot=bot, conversation_id=anchor.conversation_id)
    anchor.metadata = {'session_tools': {'session_product': {**REGISTRATION, 'revision': 1}}}
    anchor.save(update_fields=['metadata'])
    WeeklyAIQuotaConfig.objects.update_or_create(pk=1, defaults={'experience_calls': 20, 'course_calls': 200})

    def provider(messages, **kwargs):
        if messages[-1]['role'] == 'tool':
            assert json.loads(messages[-1]['content'])['result']['product'] == 42
            changed = {**REGISTRATION, 'revision': 2}
            AIChatMessage.objects.filter(pk=anchor.pk).update(metadata={'session_tools': {'session_product': changed}})
            kwargs['on_text']('STALE_CALCULATION')
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': 'STALE_CALCULATION'}}]}
        assert 'session_product' in {tool['function']['name'] for tool in kwargs['tools']}
        return {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [{
            'id': 'calculate', 'type': 'function', 'function': {'name': 'session_product', 'arguments': '{"a":6,"b":7}'},
        }]}}]}

    async def consume(response):
        return [json.loads(frame[6:]) async for frame in response.streaming_content if frame.startswith(b'data: ')]

    request_id = uuid4()
    with patch('ai_engine.service.AIEngine.call_provider', side_effect=provider) as call, \
         patch('ai_assistant.services.session_tools.run_code', return_value={'ok': True, 'results': [{'product': 42}]}):
        response = auth_client.post('/api/ai/chat/stream/', {'bot_id': bot.pk, 'conversation_id': str(anchor.conversation_id),
            'request_id': str(request_id), 'message': '继续调用session_product计算6乘7。'}, format='json')
        events = async_to_sync(consume)(response)
    assert call.call_count == 2
    assert events[-1].get('is_error') and 'STALE_CALCULATION' not in json.dumps(events)
    assert auth_client.get(f'/api/ai/chat-requests/{request_id}/').data['status'] == 'failed'
    assert not AIChatMessage.objects.filter(conversation_id=anchor.conversation_id, role='assistant').exists()
    assert not WeeklyAIUsage.objects.filter(user=user, ai_calls__gt=0).exists()


@pytest.mark.django_db
def test_ulr_artifact_commit_preserves_newer_browser_state(tool_chat):
    from ai_assistant.services.learning_experiments import ExperimentConflict, anchor_for
    from ai_assistant.services.ulr_artifacts import TurnArtifacts

    user, _, anchor = tool_chat
    experiment = {'revision': 1, 'state_version': 0, 'state': {'value': 1}}
    anchor.metadata = {'learning_experiments': {'e': experiment}}
    anchor.save(update_fields=['metadata'])
    pending = TurnArtifacts()
    pending.stage(anchor, 'learning_experiments', {'e': {**experiment, 'revision': 2}})
    pending.stage(anchor, 'session_tools', {'session_product': {**REGISTRATION, 'revision': 1}})
    assert anchor_for(user, anchor.conversation_id, artifacts=pending).metadata['learning_experiments']['e']['revision'] == 2

    latest = {**experiment, 'state_version': 1, 'state': {'value': 2}}
    AIChatMessage.objects.filter(pk=anchor.pk).update(metadata={'learning_experiments': {'e': latest}})
    with pytest.raises(ExperimentConflict):
        pending.commit(user, anchor.conversation_id)
    anchor.refresh_from_db()
    assert anchor.metadata == {'learning_experiments': {'e': latest}}


@pytest.mark.django_db
def test_dsh_bond_registration_diagnostics(tool_chat):
    from ai_assistant.services.dsh_service import execute_tool, memory_snapshot
    user, bot, current = tool_chat
    claims = {'message_id': current.pk, 'conversation_id': str(current.conversation_id), 'bot_id': bot.pk}
    inputs = {'face': 100, 'coupon': 2, 'years': 10, 'yield_rate': .067}
    flows = [(2 + (100 if year == 10 else 0)) / 1.067**year for year in range(1, 11)]
    price = sum(flows)
    expected = {'price': price, 'modified_duration': sum(year * pv for year, pv in enumerate(flows, 1)) / price / 1.067}
    registration = {'name': 'session_bond', 'description': '本地债券计算对照',
        'parameters': {'type': 'object', 'additionalProperties': False,
            'properties': {name: {'type': 'integer' if name == 'years' else 'number'} for name in inputs},
            'required': list(inputs)},
        'source': '''function run({face,coupon,years,yield_rate}) {
let price=0, weighted=0;
for(let t=1;t<=years;t++) {const pv=(coupon+(t===years?face:0))/Math.pow(1+yield_rate,t); price+=pv; weighted+=t*pv;}
return {price,modified_duration:weighted/price/(1+yield_rate)};
}''',
        'tests': [{'input': inputs, 'expected': {name: round(value, 2) for name, value in expected.items()}}]}
    version = memory_snapshot(user)['version']
    failed = execute_tool(user, 'register_session_tool', registration, version, chat_context=claims)
    assert '自检结果不符' in failed['error']
    assert failed['tests'][0]['actual'] == pytest.approx(expected)
    current.refresh_from_db()
    assert not current.metadata.get('session_tools')
    registration['tests'][0]['expected'] = expected
    registration['source'] = registration['source'].replace(
        'return {price,modified_duration:weighted/price/(1+yield_rate)};',
        'return {price,modified_duration:weighted/price/(1+yield_rate),macaulay_duration:weighted/price};')
    partial = execute_tool(user, 'register_session_tool', registration, version, chat_context=claims)
    assert '自检结果不符' in partial['error']
    assert partial['tests'][0]['actual']['price'] == pytest.approx(expected['price'])
    expected['macaulay_duration'] = sum(year * pv for year, pv in enumerate(flows, 1)) / price
    result = execute_tool(user, 'register_session_tool', registration, version, chat_context=claims)
    assert result['registered']
    assert execute_tool(user, 'session_bond', inputs, version,
                        chat_context=claims, tool_revision=1)['result'] == pytest.approx(expected)


@pytest.mark.django_db
def test_register_call_restore_and_update(tool_chat):
    user, bot, current = tool_chat
    executor, tools = chat_executor(user, current)
    result = json.loads(executor('register_session_tool', REGISTRATION))
    assert result['registered'] and result['revision'] == 1
    assert tools[-1]['function']['name'] == 'session_product'
    assert json.loads(executor('session_product', {'a': 6, 'b': 7}))['result'] == {'product': 42}
    following = AIChatMessage.objects.create(user=user, bot=bot, conversation_id=current.conversation_id,
        role='user', content='接着用这个工具')
    restored, offered = chat_executor(user, following)
    assert offered[-1]['function']['name'] == 'session_product'
    assert json.loads(restored('session_product', {'a': 2, 'b': 4}))['result'] == {'product': 8}
    old = json.loads(executor('read_session_tool', {'name': 'session_product'}))
    updated = deepcopy(REGISTRATION)
    updated.update(base_revision=old['revision'], source='function run(input) { return {product: input.a * input.b + input.offset}; }')
    updated['parameters']['properties']['offset'] = {'type': 'number'}
    updated['parameters']['required'].append('offset')
    updated['tests'][0] = {'input': {'a': 6, 'b': 7, 'offset': 1}, 'expected': {'product': 43}}
    assert json.loads(executor('register_session_tool', updated))['revision'] == 2
    assert 'offset' in tools[-1]['function']['parameters']['required']
    assert json.loads(executor('session_product', {'a': 6, 'b': 7, 'offset': 1}))['result']['product'] == 43
    assert '版本已变化' in json.loads(restored('session_product', {'a': 6, 'b': 7}))['error']


@pytest.mark.django_db
def test_failed_update_and_chat_access_boundaries(tool_chat, settings):
    user, bot, current = tool_chat
    executor, _ = chat_executor(user, current)
    assert json.loads(executor('register_session_tool', REGISTRATION))['registered']
    wrong = deepcopy(REGISTRATION)
    wrong.update(base_revision=1)
    wrong['tests'][0]['expected']['product'] = 41
    failed = json.loads(executor('register_session_tool', wrong))
    assert 'error' in failed and failed['tests'][0]['actual'] == {'product': 42}
    assert json.loads(executor('read_session_tool', {'name': 'session_product'}))['revision'] == 1
    other_chat = AIChatMessage.objects.create(user=user, bot=bot, role='user', content='另一个对话')
    foreign = type(user).objects.create_user(username='other-session-owner', is_member=True)
    foreign_message = AIChatMessage.objects.create(user=foreign, bot=bot,
        conversation_id=current.conversation_id, role='user', content='另一个账号')
    with patch('ai_assistant.services.session_tools.run_code') as worker:
        for owner, message in [(user, other_chat), (foreign, foreign_message)]:
            isolated, offered = chat_executor(owner, message)
            assert all(tool['function']['name'] != 'session_product' for tool in offered)
            assert 'error' in json.loads(isolated('session_product', {'a': 6, 'b': 7}))
        assert 'error' in json.loads(executor('session_product', {'a': -1, 'b': 7}))
        settings.UNIMIND_LEARNING_EXPERIMENTS_PROTOTYPE = False
        assert 'error' in json.loads(executor('session_product', {'a': 6, 'b': 7}))
        worker.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_model_sees_new_schema_and_calls_new_name_in_same_turn(tool_chat, monkeypatch):
    from ai_engine.service import AIEngine
    user, _, current = tool_chat
    executor, tools = chat_executor(user, current)
    snapshots = []

    class Stream:
        def __init__(self, delta, finish):
            self.delta, self.finish = delta, finish

        def raise_for_status(self):
            pass

        def iter_lines(self, **kwargs):
            yield 'data: ' + json.dumps({'choices': [{'delta': self.delta, 'finish_reason': self.finish}]})
            yield 'data: [DONE]'

    def post(*args, **kwargs):
        snapshots.append(json.loads(json.dumps(kwargs['json'])))
        names = {tool['function']['name'] for tool in snapshots[-1]['tools']}
        count = len(snapshots)
        if count == 1:
            assert 'session_product' not in names
            name, arguments = 'register_session_tool', REGISTRATION
        elif count == 2:
            assert 'session_product' in names
            name, arguments = 'session_product', {'a': 6, 'b': 7}
        else:
            output = next(message for message in reversed(snapshots[-1]['messages']) if message['role'] == 'tool')
            assert json.loads(output['content'])['result'] == {'product': 42}
            return Stream({'content': '计算结果是 42。'}, 'stop')
        return Stream({'tool_calls': [{'index': 0, 'id': f'call-{count}', 'type': 'function',
            'function': {'name': name, 'arguments': json.dumps(arguments)}}]}, 'tool_calls')

    monkeypatch.setattr('ai_engine.service._session.post', post)
    monkeypatch.setattr('ai_engine.service.get_model_for_task', lambda operation: {
        'api_key': 'synthetic', 'base_url': 'https://example.invalid/chat', 'model': 'synthetic', 'thinking': None})
    monkeypatch.setattr('ai_engine.circuit_breaker.AICircuitBreaker.check', lambda *args, **kwargs: None)
    monkeypatch.setattr('ai_engine.circuit_breaker.AICircuitBreaker.record_success', lambda *args, **kwargs: None)
    result = AIEngine.call_ai_with_streaming_tools(messages=[{'role': 'user', 'content': '创建工具并算一次'}],
        tools=tools, tool_executor=executor, max_tool_rounds=3)
    assert result['content'] == '计算结果是 42。'
    assert len(snapshots) == 3
