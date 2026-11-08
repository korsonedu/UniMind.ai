"""Prototype smoke: one chat's source/state, revision updates and access boundary."""
from unittest.mock import patch
from contextlib import ExitStack
from uuid import uuid4
import asyncio
import json

import pytest
from rest_framework.exceptions import NotFound

from ai_assistant.models import AIChatMessage, Bot
from ai_assistant.services import learning_experiments as experiments


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
    assert '自主交互学习实验' in messages[0]['content']
    assert executor.experiment_context['message_id'] == current.pk
    invalid = json.loads(executor('build_learning_experiment', {
        'title': '不存在的实验', 'html': '<button id="run">运行</button>',
        'experiment_id': str(uuid4()), 'base_revision': 1,
        'checks': [{'selector': '#run', 'action': 'click', 'expect_selector': 'body', 'expect_text': '运行'}]}))
    assert '必须省略 experiment_id 和 base_revision' in invalid['error']
    assert not executor.pending_visuals
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


def test_browser_failure_reaches_model_and_mount_finishes_turn(monkeypatch):
    from ai_engine.service import AIEngine
    diagnostics = {'ok': False, 'checks': [{'ok': False, 'error': 'Expected 7.99; actual 7.96'}]}
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
    bot = Bot.objects.create(name='小宇', bot_type='planner', system_prompt='冒烟')
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
