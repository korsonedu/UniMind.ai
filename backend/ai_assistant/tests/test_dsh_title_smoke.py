"""Title generation through the server DSH structured task."""
import json
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
        assert '标题' in payload['context']['task_instruction']
