"""Official XiaoYu adapter smoke: no paid model or production data."""
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch
import pytest
from ai_assistant.models import Bot, Conversation, AIChatMessage
from users.models import WeeklyAIQuotaConfig, WeeklyAIUsage, AIUsageReservation


@pytest.mark.django_db
def test_official_turn_persists_once_and_uses_auxiliary_tasks(user, settings, tmp_path):
    from ai_assistant.services.dsh_xiaoyu import complete_turn
    settings.UNIMIND_DSH_ENABLED = settings.UNIMIND_DSH_SITE_ENABLED = settings.UNIMIND_DSH_XIAOYU_ENABLED = True
    settings.UNIMIND_DSH_TITLE_ENABLED = settings.UNIMIND_DSH_MEMORY_ENABLED = True
    settings.UNIMIND_DSH_STATE_DIR = str(tmp_path)
    WeeklyAIQuotaConfig.objects.update_or_create(pk=1, defaults={'experience_calls': 20, 'course_calls': 200})
    bot = Bot.objects.create(name='小宇', bot_type='planner', system_prompt='合成提示词')
    cid = uuid4()
    body = {'message': '我喜欢先举例', 'request_id': str(uuid4()), 'conversation_id': str(cid), 'bot_id': bot.pk}
    req = SimpleNamespace(user=user, data=body)
    native = {'finish_reason': 'completed', 'content': '合成回答',
              'session': {'id': 'a'*32, 'messages': [{'role': 'assistant', 'cards': []}]}}
    with patch('ai_assistant.services.dsh_xiaoyu.run_site_action', return_value=native) as runtime, \
            patch('ai_assistant.services.dsh_xiaoyu.sync_generate_title', return_value='学习偏好') as title, \
            patch('ai_assistant.services.dsh_xiaoyu.extract_memories_async') as memories, \
            patch('ai_assistant.services.dsh_xiaoyu.can_use_learning_context', return_value=True):
        result = complete_turn(req, bot, cid, body['message'], lambda event: None)
        assert result['done'] and result['engine'] == 'dsh'
        assert AIChatMessage.objects.filter(user=user, conversation_id=cid).count() == 2
        assert complete_turn(req, bot, cid, body['message'], lambda event: None) == result
        runtime.assert_called_once(); title.assert_called_once(); memories.assert_called_once()
        assert runtime.call_args.kwargs['chat_context']['message_id'] == result['user_message']['message_id']
    assert AIUsageReservation.objects.get(user=user).status == 'succeeded'
    assert Conversation.objects.get(user=user, conversation_id=cid).title == '学习偏好'


@pytest.mark.django_db
def test_official_turn_failure_releases_and_never_uses_legacy(user, settings, tmp_path):
    from ai_assistant.services.dsh_xiaoyu import complete_turn
    from ai_assistant.services.dsh_runtime import DshUnavailable
    settings.UNIMIND_DSH_STATE_DIR = str(tmp_path)
    bot = Bot.objects.create(name='小宇', bot_type='planner', system_prompt='合成')
    cid = uuid4()
    body = {'message': '合成失败', 'request_id': str(uuid4()), 'conversation_id': str(cid), 'bot_id': bot.pk}
    with patch('ai_assistant.services.dsh_xiaoyu.run_site_action', side_effect=DshUnavailable()), \
            patch('ai_engine.service.AIEngine.call_ai') as legacy:
        with pytest.raises(DshUnavailable):
            complete_turn(SimpleNamespace(user=user, data=body), bot, cid, body['message'], lambda event: None)
        legacy.assert_not_called()
    assert not AIChatMessage.objects.filter(conversation_id=cid).exists()
    assert AIUsageReservation.objects.get(user=user).status == 'released'
    native = {'finish_reason': 'completed', 'content': '同一请求重试完成',
              'session': {'id': 'b' * 32, 'messages': [{'role': 'assistant', 'cards': []}]}}
    with patch('ai_assistant.services.dsh_xiaoyu.run_site_action', return_value=native) as runtime:
        request = SimpleNamespace(user=user, data=body)
        result = complete_turn(request, bot, cid, body['message'], lambda event: None)
        assert complete_turn(request, bot, cid, body['message'], lambda event: None) == result
        runtime.assert_called_once()
    assert AIUsageReservation.objects.get(user=user).status == 'succeeded'
    assert WeeklyAIUsage.objects.get(user=user).ai_calls == 1
    assert AIChatMessage.objects.filter(conversation_id=cid).count() == 2


@pytest.mark.django_db
def test_signed_context_is_bound_and_delete_invalidates_replay(auth_client, user, settings, tmp_path):
    from datetime import date
    from rest_framework.test import APIClient
    from ai_assistant.dsh_authentication import make_task_token
    settings.UNIMIND_DSH_ENABLED = settings.UNIMIND_DSH_XIAOYU_ENABLED = True
    settings.UNIMIND_DSH_STATE_DIR = str(tmp_path)
    bot = Bot.objects.create(name='小宇', bot_type='planner', system_prompt='合成')
    cid = uuid4()
    Conversation.objects.create(user=user, bot=bot, conversation_id=cid)
    current = AIChatMessage.objects.create(user=user, bot=bot, conversation_id=cid, role='user', content='本人合成问题')
    from ai_assistant.models import ConversationProject
    project = ConversationProject.objects.create(user=user, name='合成复习项目', instructions='PROJECT_CONTEXT_MUST_SURVIVE_EIGHT_MESSAGES')
    Conversation.objects.filter(conversation_id=cid).update(project=project)
    for index in range(8):
        AIChatMessage.objects.create(user=user, bot=bot, conversation_id=cid,
            role='assistant' if index % 2 else 'user', content=f'合成历史 {index}')
    reservation = AIUsageReservation.objects.create(user=user, request_id=uuid4(), attempt_id=uuid4(), week=date(2026,10,26))
    claims = {'conversation_id': str(cid), 'bot_id': bot.pk, 'message_id': current.pk}
    callback = APIClient()
    callback.credentials(HTTP_AUTHORIZATION='DSH ' + make_task_token(user, reservation, chat_context=claims))
    response = callback.post('/api/ai/dsh/context/', {'message': current.content}, format='json')
    assert response.status_code == 200
    assert 'PROJECT_CONTEXT_MUST_SURVIVE_EIGHT_MESSAGES' in response.json()['system_prompt']
    assert callback.post('/api/ai/dsh/context/', {'message': '替换后的问题'}, format='json').status_code == 403
    other = type(user).objects.create_user(username='other-official-owner')
    foreign = AIChatMessage.objects.create(user=other, bot=bot, role='user', content='他人秘密')
    callback.credentials(HTTP_AUTHORIZATION='DSH ' + make_task_token(user, reservation, chat_context={**claims, 'message_id': foreign.pk}))
    assert callback.post('/api/ai/dsh/context/', {'message': foreign.content}, format='json').status_code == 403
    AIChatMessage.objects.create(user=user, bot=bot, conversation_id=cid, role='assistant', content='本人回答',
        metadata={'engine': 'dsh', 'dsh_session_id': 'a'*32})
    reservation.status = 'succeeded'
    reservation.response = {'engine': 'dsh', 'session_id': 'a'*32, 'full_content': '本人回答'}
    reservation.save()
    with patch('ai_assistant.services.dsh_xiaoyu.run_site_action', return_value={'deleted': True}) as runtime:
        assert auth_client.post('/api/ai/delete-conversation/', {'conversation_id': str(cid)}, format='json').status_code == 200
        runtime.assert_called_once_with(user, 'delete', session_id='a'*32)
    reservation.refresh_from_db()
    assert reservation.response == {'engine': 'dsh', 'session_id': 'a'*32, 'deleted': True}
    assert not AIChatMessage.objects.filter(user=user, conversation_id=cid).exists()
