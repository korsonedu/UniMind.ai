"""Title generation through the server DSH structured task."""
import json
from datetime import timedelta
from pathlib import Path
import sys
import uuid
from unittest.mock import patch

from django.test import TestCase, override_settings

from ai_assistant.models import AIChatMessage, Bot, Conversation
from ai_assistant.services.dsh_runtime import DshUnavailable
from ai_assistant.services.title_generator import sync_generate_title
from users.models import User


class DshTitleSmoke(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='title-smoke')
        self.bot = Bot.objects.create(name='Title', bot_type='planner', system_prompt='')
        self.conversation = Conversation.objects.create(user=self.user, bot=self.bot, conversation_id=uuid.uuid4())
        AIChatMessage.objects.create(user=self.user, bot=self.bot, conversation_id=self.conversation.conversation_id,
                                     role='user', content='请解释久期的含义和影响因素')
        AIChatMessage.objects.create(user=self.user, bot=self.bot, conversation_id=self.conversation.conversation_id,
                                     role='assistant', content='久期衡量债券价格对利率变化的敏感度。')

    @override_settings(UNIMIND_DSH_TITLE_ENABLED=True)
    def test_dsh_title_is_written_once(self):
        with patch('ai_assistant.services.dsh_tasks.run_structured', return_value={'title': '久期利率敏感度'}) as task:
            self.assertEqual(sync_generate_title(str(self.conversation.conversation_id), self.user.id, self.bot.id), '久期利率敏感度')
        task.assert_called_once()
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.title, '久期利率敏感度')
        with patch('ai_assistant.services.dsh_tasks.run_structured') as again:
            self.assertIsNone(sync_generate_title(str(self.conversation.conversation_id), self.user.id, self.bot.id))
        again.assert_not_called()

    @override_settings(UNIMIND_DSH_TITLE_ENABLED=True)
    def test_dsh_failure_falls_back_to_first_message(self):
        with patch('ai_assistant.services.dsh_tasks.run_structured', side_effect=DshUnavailable('offline')):
            title = sync_generate_title(str(self.conversation.conversation_id), self.user.id, self.bot.id)
        self.assertEqual(title, '请解释久期的含义和影响因素'[:15])
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.title, title)

    def test_title_switch_off_keeps_legacy_path(self):
        with patch('ai_assistant.services.title_generator.AIService') as ai:
            ai.return_value.simple_chat_text.return_value = '旧标题'
            self.assertEqual(sync_generate_title(str(self.conversation.conversation_id), self.user.id, self.bot.id), '旧标题')
        ai.return_value.simple_chat_text.assert_called_once()

    def test_ulr_discards_title_after_rename_or_delete(self):
        conversation_id = str(self.conversation.conversation_id)
        arguments = (conversation_id, self.user.id, self.bot.id)
        response = {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [{
            'function': {'name': 'submit_title', 'arguments': json.dumps({'title': '自动标题'})},
        }]}}]}

        def rename(*args, **kwargs):
            Conversation.objects.filter(pk=self.conversation.pk).update(title='用户自定义标题')
            return response

        with patch('ai_engine.service.AIEngine.call_provider', side_effect=rename) as call:
            self.assertIsNone(sync_generate_title(*arguments, ulr=True))
        call.assert_called_once()
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.title, '用户自定义标题')

        def delete(*args, **kwargs):
            self.conversation.delete()
            return response

        with patch('ai_engine.service.AIEngine.call_provider', side_effect=delete) as call:
            self.assertIsNone(sync_generate_title(*arguments, expected_title='用户自定义标题', ulr=True))
            self.assertIsNone(sync_generate_title(*arguments, ulr=True))
        call.assert_called_once()
        self.assertFalse(Conversation.objects.filter(conversation_id=conversation_id).exists())

    def test_ulr_queued_title_uses_the_bound_exchange(self):
        messages = AIChatMessage.objects.filter(conversation_id=self.conversation.conversation_id)
        question = messages.get(role='user')
        answer = messages.get(role='assistant')
        answer.metadata = {'learning_turn': {'message_id': question.pk, 'completed': True}}
        answer.save(update_fields=['metadata'])
        later_question = AIChatMessage.objects.create(user=self.user, bot=self.bot,
            conversation_id=self.conversation.conversation_id, role='user', content='无关插入')
        messages.filter(pk=answer.pk).update(timestamp=later_question.timestamp + timedelta(seconds=1))
        args = (str(self.conversation.conversation_id), self.user.id, self.bot.id)
        with patch('ai_assistant.services.ulr_structured.run_collector', return_value={'title': '久期'}) as model:
            assert sync_generate_title(*args, ulr=True, answer_message_id=answer.pk + 1000) is None
            model.assert_not_called()
            assert sync_generate_title(*args, ulr=True, answer_message_id=answer.pk) == '久期'
            prompt = model.call_args.args[0]
            assert question.content in prompt and answer.content in prompt and '无关插入' not in prompt


    def test_ulr_title_delivery_must_match_the_pending_exchange(self):
        from ai_assistant.models import PendingConversationTitle
        from ai_assistant.tasks import generate_conversation_title

        messages = AIChatMessage.objects.filter(conversation_id=self.conversation.conversation_id)
        question, answer = messages.get(role='user'), messages.get(role='assistant')
        answer.metadata = {'learning_turn': {'message_id': question.pk, 'completed': True}}
        answer.save(update_fields=['metadata'])
        self.conversation.title = '临时标题'
        self.conversation.save(update_fields=['title'])
        job = PendingConversationTitle.objects.create(conversation=self.conversation, answer_message=answer,
                                                       expected_title=self.conversation.title)
        conversation_id = str(self.conversation.conversation_id)
        args = (conversation_id, self.user.pk, self.bot.pk)
        fields = {'expected_title': job.expected_title, 'answer_message_id': answer.pk, 'pending_job_id': job.pk}
        dispatch_after = job.dispatch_after
        with patch('ai_assistant.services.ulr_structured.run_collector', return_value={'title': '久期'}) as collect, \
                patch('django.db.connections.close_all'):
            for stale in ((str(uuid.uuid4()), *args[1:]), (conversation_id, self.user.pk + 1, self.bot.pk),
                          (conversation_id, self.user.pk, self.bot.pk + 1)):
                generate_conversation_title.run(*stale, **fields)
            for stale in ({'expected_title': '旧临时标题'}, {'answer_message_id': question.pk}):
                generate_conversation_title.run(*args, **(fields | stale))
            collect.assert_not_called()
            job.refresh_from_db()
            self.conversation.refresh_from_db()
            assert job.running_until is None and job.dispatch_after == dispatch_after
            assert self.conversation.title == job.expected_title
            generate_conversation_title.run(*args, **fields)
            generate_conversation_title.run(*args, **fields)
            collect.assert_called_once()

        self.conversation.refresh_from_db()
        assert self.conversation.title == '久期'
        assert not PendingConversationTitle.objects.filter(pk=job.pk).exists()


def test_title_task_uses_fast_single_request(settings, tmp_path, monkeypatch):
    from ai_assistant.services.dsh_tasks import run_structured
    settings.DEBUG = True
    settings.UNIMIND_DSH_PYTHON = sys.executable
    settings.UNIMIND_DSH_STATE_DIR = str(tmp_path)
    settings.UNIMIND_DSH_FIXTURE_URL = 'http://127.0.0.1:8912/v1/messages'
    monkeypatch.setenv('AI_MODEL_FAST', 'title-fast-model')
    with patch('ai_assistant.services.dsh_tasks.subprocess.Popen') as popen:
        process = popen.return_value.__enter__.return_value
        process.returncode = 0
        process.communicate.return_value = (json.dumps({'status': 200, 'result': {'title': '久期'}}).encode(), b'')
        assert run_structured('assistant.title', '用户: 久期\n助手: 利率敏感度') == {'title': '久期'}
        payload = json.loads(process.communicate.call_args.args[0])
        policy = payload['context']['model_policy']
        assert (policy['tier'], policy['model'], policy['max_requests'], policy['max_tokens']) == ('fast', 'title-fast-model', 1, 64)
        assert payload['context']['task_instruction'] == (Path(settings.BASE_DIR) / 'prompts/ai_assistant/title_task.txt').read_text()
