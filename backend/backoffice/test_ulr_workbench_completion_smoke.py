import json
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.db import transaction

from ai_assistant.models import AIChatMessage, Bot
from notifications.models import Notification
from quizzes.models import ContentPipelineTask
from users.models import CourseStudentStatus

from . import teaching
from .tasks import run_teaching_task
from .teaching_executor import TeachingExecutor


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('case', ['incomplete_tool', 'incomplete_reply', 'complete', 'invalid_group'])
def test_ulr_workbench_checks_text_completion_before_publishing(case, admin_user, user, settings):
    settings.DEBUG = False
    settings.UNIMIND_LEARNING_RUNTIME = 'ulr'
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    settings.UNIMIND_DIRECTUS_ADMIN_MAP = {str(uuid4()): admin_user.pk, str(uuid4()): user.pk}
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    Bot.objects.create(name='Workbench', bot_type='exam_generator')
    conversation_id = uuid4()
    with patch('backoffice.tasks.run_teaching_task.delay') as dispatch, transaction.atomic():
        queued = teaching.chat(SimpleNamespace(user=admin_user), {'message': '给学员准备通知。',
            'conversation_id': str(conversation_id), 'request_id': str(uuid4())})
    dispatch.assert_called_once_with(queued['id'])

    def model(messages, **kwargs):
        if case == 'invalid_group':
            if messages[-2]['role'] != 'tool':
                return {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [{
                    'id': 'group', 'type': 'function', 'function': {
                        'name': 'find_teaching_tools', 'arguments': '{"group":"unknown"}'},
                }]}}]}
            error = json.loads(messages[-2]['content'])['error']
            assert (error['code'], error['field'], error['rule']) == ('invalid_arguments', '$.group', 'enum')
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': '请先确认要使用的教研分组。'}}]}
        if messages[-2]['role'] != 'tool':
            assert 'send_notification' in {tool['function']['name'] for tool in kwargs['tools']}
            if case != 'incomplete_reply':
                text = ('<function_calls><invoke name="send_notification">'
                        f'<parameter name="student_id">{user.pk}</parameter>'
                        '<parameter name="content">只准备预览</parameter></invoke>')
                if case == 'complete':
                    text += '</function_calls>'
                return {'choices': [{'finish_reason': 'stop', 'message': {'content': text}}]}
            return {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [{
                'id': 'notice', 'type': 'function', 'function': {'name': 'send_notification',
                    'arguments': json.dumps({'student_id': user.pk, 'content': '只准备预览'})},
            }]}}]}
        receipt = json.loads(messages[-2]['content'])
        assert receipt['requires_confirmation'] and 'preview_token' not in receipt['preview']
        assert '<function_calls>' not in json.dumps(messages, ensure_ascii=False)
        text = '请核对预览。' if case == 'complete' else '预览已经准备。<function_calls><invoke name="send_notification">'
        return {'choices': [{'finish_reason': 'stop', 'message': {'content': text}}]}

    with (
        patch('ai_engine.service.AIEngine.call_provider', side_effect=model) as provider,
        patch.object(TeachingExecutor, '_handle_send_notification', autospec=True,
                     side_effect=TeachingExecutor._handle_send_notification) as preview,
    ):
        run_teaching_task(queued['id'])
        run_teaching_task(queued['id'])
    assert provider.call_count == (1 if case == 'incomplete_tool' else 2)
    assert preview.call_count == int(case in ('incomplete_reply', 'complete'))
    task = ContentPipelineTask.objects.get(pk=queued['id'])
    messages = AIChatMessage.objects.filter(conversation_id=conversation_id)
    if case == 'complete':
        assert task.status == 'completed'
        confirmation, = task.result['confirmations']
        assert confirmation['payload']['preview_token'] and messages.count() == 2
    elif case == 'invalid_group':
        assert task.status == 'completed' and not task.result['confirmations'] and messages.count() == 2
    else:
        assert task.status == 'failed' and not task.result and not messages.exists()
    assert not Notification.objects.exists()
