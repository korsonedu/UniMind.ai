"""Exercise the component contract through XiaoYu and real Chromium."""
import json
import os
from time import monotonic, sleep
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
import pytest
from rest_framework.exceptions import ValidationError

from ai_assistant.models import AIChatMessage, Bot, LearningComponentTemplate
from ai_assistant.services.learning_experiments import preview
from ai_assistant.services.views.learning_components import compile_component, template_for
from users.models import CourseStudentStatus, WeeklyAIQuotaConfig


@pytest.mark.django_db(transaction=True)
def test_cross_subject_components_and_private_reuse(auth_client, user, settings):
    settings.DEBUG = True
    settings.UNIMIND_LEARNING_RUNTIME = 'ulr'
    settings.UNIMIND_LEARNING_EXPERIMENTS_ENABLED = True
    settings.UNIMIND_LEARNING_VISUAL_REVIEW_ENABLED = True
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    WeeklyAIQuotaConfig.objects.update_or_create(pk=1, defaults={'course_calls': 20})
    bot, _ = Bot.objects.get_or_create(is_xiaoyu=True, defaults={'name': '小宇'})
    examples = [
        ('同一物体换到两个星球时，让我改变质量，看重力有何差别。', {
            'sliders': [{'id': 'mass', 'label': '质量（kg）', 'min': 1, 'max': 10, 'value': 2}],
            'choices': [{'id': 'gravity', 'label': '星球', 'options': [
                {'label': '甲星（4 N/kg）', 'value': 4}, {'label': '乙星（9 N/kg）', 'value': 9}]}],
            'outputs': [{'id': 'force', 'label': '重力', 'unit': 'N',
                         'expression': {'op': 'mul', 'args': ['mass', 'gravity']}}],
        }, 3),
        ('让我把传粉昆虫移到试验花圃，并调节每只产生的种子数，总数随之变化。', {
            'sliders': [{'id': 'yield', 'label': '每只昆虫产生的种子数', 'min': 1, 'max': 12, 'value': 3}],
            'zones': [{'id': 'outside', 'label': '待入花圃'}, {'id': 'garden', 'label': '试验花圃'}],
            'items': [{'id': 'bee', 'label': '蜜蜂', 'zone': 'outside'},
                      {'id': 'fly', 'label': '食蚜蝇', 'zone': 'outside'}],
            'outputs': [{'id': 'seeds', 'label': '种子总数',
                         'expression': {'op': 'mul', 'args': ['yield', {'count': 'garden'}]}},
                        {'id': 'bee_seeds', 'label': '蜜蜂在花圃贡献的种子',
                         'expression': {'op': 'mul', 'args': ['yield', {'in_zone': ['bee', 'garden']}]}}],
        }, 3),
        ('让我分别改变溶质和水的质量，观察溶液的质量分数。', {
            'sliders': [{'id': 'solute', 'label': '溶质（g）', 'min': 0, 'max': 10, 'value': 2},
                        {'id': 'water', 'label': '水（g）', 'min': 0, 'max': 20, 'value': 8}],
            'outputs': [{'id': 'ratio', 'label': '质量分数', 'unit': '%', 'expression': {
                'op': 'div', 'args': [{'op': 'mul', 'args': [100, 'solute']},
                                      {'op': 'add', 'args': ['solute', 'water']}]}}],
        }, 3),
    ]
    specs = {message: component for message, component, _ in examples}
    reuse = '再用上次那个星球重力组件。'
    pending = []

    def tool(name, arguments):
        return {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [{
            'id': str(uuid4()), 'type': 'function',
            'function': {'name': name, 'arguments': json.dumps(arguments, ensure_ascii=False)},
        }]}}]}

    def model(messages, **kwargs):
        message = messages[1]['content']
        offered = {entry['function']['name'] for entry in kwargs['tools'] or []}
        result = json.loads(messages[-1]['content']) if messages[-1]['role'] == 'tool' else {}
        if result.get('experiment_id'):
            assert result['preview']['ok'] and result['preview']['layout_checked'], result
            assert kwargs['timeout_seconds'] > 20
            if message == examples[0][0]:
                assert not LearningComponentTemplate.objects.filter(owner=user).exists()
            pending.append(result['experiment_id'])
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': '可以开始操作了。'}}]}
        if 'build_learning_experiment' not in offered:
            return tool('find_learning_tools', {'group': 'authoring'})
        if message == reuse:
            template = LearningComponentTemplate.objects.get(owner=user)
            assert str(template.pk) in messages[0]['content']
            return tool('build_learning_experiment', {'template_id': template.pk})
        return tool('build_learning_experiment', {'title': message[:25], 'component': specs[message],
            'save_template': message == examples[0][0]})

    async def consume(response):
        return [json.loads(row[6:]) async for row in response.streaming_content if row.startswith(b'data: ')]

    with patch('ai_engine.service.AIEngine.call_provider', side_effect=model), \
            patch('ai_assistant.services.learning_experiment_review.review_screenshots',
                  side_effect=AssertionError('structured component called visual model')):
        for message, checks in [(text, count) for text, _, count in examples] + [(reuse, 3)]:
            room = str(uuid4())
            response = auth_client.post('/api/ai/chat/stream/', {'bot_id': bot.pk, 'conversation_id': room,
                'request_id': str(uuid4()), 'message': message}, format='json')
            assert response.status_code == 200
            final = async_to_sync(consume)(response)[-1]
            assert final.get('engine') == 'ulr', final
            card, = final['metadata']['dsh_cards']
            experiment_id = card['payload']['experiment_id']
            assert card['type'] == 'learning_experiment' and experiment_id == pending[-1]
            document = auth_client.get(f'/api/ai/learning-experiments/{room}/{experiment_id}/')
            assert document.status_code == 200
            stored = AIChatMessage.objects.get(conversation_id=room, role='user').metadata['learning_experiments'][experiment_id]
            assert len(stored['preview']['checks']) == checks and all(row['ok'] for row in stored['preview']['checks'])
            assert stored['component'] == specs[examples[0][0] if message == reuse else message]
            if message == reuse:
                assert stored['template_id'] == LearningComponentTemplate.objects.get(owner=user).pk
            assert document.data['state'] == {}

    author = LearningComponentTemplate.objects.get(owner=user)
    outsider = get_user_model().objects.create_user(username='unrelated-component-user')
    with pytest.raises(ValidationError):
        template_for(outsider, author.pk)


def test_component_requires_actual_worker_layout_check(settings):
    settings.UNIMIND_LEARNING_VISUAL_REVIEW_ENABLED = True
    with patch('ai_assistant.services.learning_worker.run', return_value={'ok': True, 'checks': [], 'errors': []}):
        report = preview('<main>示例</main>', {}, [], initial_selector='main')
    assert not report['ok']
    assert '尚未同步组件检查协议' in report['errors'][0]


@pytest.mark.django_db(transaction=True)
def test_authoring_stays_connected_past_original_deadline(auth_client, user, settings):
    settings.DEBUG = True
    settings.UNIMIND_LEARNING_RUNTIME = 'ulr'
    settings.UNIMIND_LEARNING_EXPERIMENTS_ENABLED = True
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    WeeklyAIQuotaConfig.objects.update_or_create(pk=1, defaults={'course_calls': 20})
    bot, _ = Bot.objects.get_or_create(is_xiaoyu=True, defaults={'name': '小宇'})
    real_wait = os.environ.get('RUN_LONG_COMPONENT_SMOKE') == '1'
    simulated_seconds = 0
    room = str(uuid4())

    def model(messages, **kwargs):
        nonlocal simulated_seconds
        assert kwargs['timeout_seconds'] >= 31
        if real_wait:
            sleep(31)
        else:
            simulated_seconds += 31
        if messages[-1]['role'] == 'tool':
            result = json.loads(messages[-1]['content'])
            assert result['preview']['layout_checked'] and result['preview']['ok'], result
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': '可以开始操作了。'}}]}
        assert 'build_learning_experiment' in {tool['function']['name'] for tool in kwargs['tools']}
        arguments = {'title': '书签计数', 'component': {
            'sliders': [{'id': 'books', 'label': '书的数量', 'min': 1, 'max': 10, 'value': 3}],
            'outputs': [{'id': 'bookmarks', 'label': '书签数量',
                         'expression': {'op': 'mul', 'args': ['books', 2]}}],
        }}
        return {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [{
            'id': str(uuid4()), 'type': 'function',
            'function': {'name': 'build_learning_experiment', 'arguments': json.dumps(arguments)},
        }]}}]}

    async def consume(response):
        return [frame async for frame in response.streaming_content]

    started = monotonic()
    with patch('ai_engine.service.AIEngine.call_provider', side_effect=model) as provider, \
            patch('ai_assistant.services.runtime.ulr_runtime.monotonic',
                  side_effect=lambda: monotonic() + simulated_seconds):
        response = auth_client.post('/api/ai/chat/stream/', {'bot_id': bot.pk, 'conversation_id': room,
            'request_id': str(uuid4()), 'message': '做个可视化演示，让我调节书的数量，每本用两张书签。'}, format='json')
        assert response.status_code == 200
        frames = async_to_sync(consume)(response)
        assert provider.call_count == 2, frames
    assert monotonic() - started + simulated_seconds > 60
    if real_wait:
        assert frames.count(b': heartbeat\n\n') >= 2
    final = json.loads(frames[-1][6:])
    assert final.get('engine') == 'ulr', final
    card, = final['metadata']['dsh_cards']
    assert card['type'] == 'learning_experiment'
    experiment_id = card['payload']['experiment_id']
    assert auth_client.get(f'/api/ai/learning-experiments/{room}/{experiment_id}/').status_code == 200


def test_only_exhibits_in_gallery_contribute_power(settings):
    settings.DEBUG = True
    component = {
        'sliders': [{'id': 'a_power', 'label': '展品甲功率', 'min': 0, 'max': 100, 'value': 10},
                    {'id': 'b_power', 'label': '展品乙功率', 'min': 0, 'max': 100, 'value': 20}],
        'zones': [{'id': 'storage', 'label': '库房'}, {'id': 'gallery', 'label': '展厅'}],
        'items': [{'id': 'a', 'label': '展品甲', 'zone': 'storage'},
                  {'id': 'b', 'label': '展品乙', 'zone': 'gallery'}],
        'outputs': [{'id': 'total', 'label': '展厅总功率', 'unit': 'W', 'expression': {'op': 'add', 'args': [
            {'op': 'mul', 'args': ['a_power', {'in_zone': ['a', 'gallery']}]},
            {'op': 'mul', 'args': ['b_power', {'in_zone': ['b', 'gallery']}]},
        ]}}],
    }
    html, _, _ = compile_component(component, {})
    checks = [
        {'selector': selector, 'action': 'input' if value else 'click', 'value': value,
         'expect_selector': f'#lc-output-total[data-value="{watts}.00"]', 'expect_text': f'{watts}.00 W'}
        for selector, value, watts in [
            ('#lc-control-a_power', '60', 20),
            ('#lc-move-a-gallery', '', 80),
            ('#lc-control-a_power', '45', 65),
            ('#lc-move-a-storage', '', 20),
        ]
    ]
    checks.append({'selector': '#lc-reset', 'action': 'click',
        'expect_selector': '#lc-component:has(#lc-value-a_power[data-value="10"]) #lc-output-total',
        'expect_text': '20.00 W'})
    report = preview(html, {}, checks, initial_selector='#lc-output-total[data-value="20.00"]')
    assert report['ok'] and report['layout_checked'], report
    assert len(report['checks']) == 5
