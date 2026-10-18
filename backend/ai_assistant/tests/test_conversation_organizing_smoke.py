import uuid
from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APITestCase

from ai_assistant.models import AIChatMessage, Bot, Conversation, ConversationProject
from ai_assistant.services.title_generator import sync_generate_title
from ai_assistant.views_projects import add_project_context
from users.models import User


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class ConversationOrganizingSmokeTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='conversation_owner', is_member=True)
        self.other = User.objects.create_user(username='conversation_other', is_member=True)
        self.bot = Bot.objects.create(name='小宇')
        self.project = ConversationProject.objects.create(user=self.user, name='金融学', instructions='先讲概念')
        self.conversation = Conversation.objects.create(user=self.user, bot=self.bot, conversation_id=uuid.uuid4())
        for role in ('user', 'assistant'):
            AIChatMessage.objects.create(user=self.user, bot=self.bot, conversation_id=self.conversation.conversation_id, role=role, content='利率')
        self.url = f'/api/ai/conversations/{self.conversation.conversation_id}/'
        self.client.force_authenticate(self.user)

    def test_rename_pin_move_and_remove_assignment_preserve_messages(self):
        response = self.client.patch(self.url, {'title': '利率复习', 'is_pinned': True, 'project_id': self.project.id}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        history = self.client.get('/api/ai/history/').data
        self.assertEqual(len(history), 2)
        self.assertTrue(all(message['conversation_title'] == '利率复习' and message['conversation_pinned'] and message['conversation_project'] == self.project.id for message in history))
        self.assertIn('先讲概念', add_project_context(self.user, self.conversation.conversation_id, [])[0]['content'])
        response = self.client.patch(self.url, {'is_pinned': False, 'project_id': None}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.title, '利率复习')
        self.assertFalse(self.conversation.is_pinned)
        self.assertIsNone(self.conversation.project_id)
        self.assertEqual(add_project_context(self.user, self.conversation.conversation_id, []), [])

    def test_foreign_conversations_projects_and_invalid_titles_are_rejected(self):
        foreign_project = ConversationProject.objects.create(user=self.other, name='私人项目')
        foreign = Conversation.objects.create(user=self.other, bot=self.bot, conversation_id=uuid.uuid4(), title='私人对话')
        self.assertEqual(self.client.patch(f'/api/ai/conversations/{foreign.conversation_id}/', {'title': '修改'}).status_code, 404)
        self.assertEqual(self.client.patch(self.url, {'project_id': foreign_project.id}).status_code, 400)
        for title in (' ', '长' * 121):
            self.assertEqual(self.client.patch(self.url, {'title': title}).status_code, 400)
        self.client.force_authenticate(None)
        self.assertIn(self.client.patch(self.url, {'is_pinned': True}).status_code, (401, 403))

    def test_legacy_conversation_gets_metadata_without_changing_messages(self):
        conversation_id = uuid.uuid4()
        message = AIChatMessage.objects.create(user=self.user, bot=self.bot, conversation_id=conversation_id, role='user', content='历史对话')
        response = self.client.patch(f'/api/ai/conversations/{conversation_id}/', {'project_id': self.project.id, 'title': '历史复习'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Conversation.objects.get(conversation_id=conversation_id).project_id, self.project.id)
        self.assertTrue(AIChatMessage.objects.filter(pk=message.id, conversation_id=conversation_id).exists())

    def test_inflight_generated_title_preserves_manual_name(self):
        def rename_during_generation(**kwargs):
            Conversation.objects.filter(pk=self.conversation.pk).update(title='手动名称')
            return '自动标题'

        with patch('ai_assistant.services.title_generator.AIService') as ai:
            ai.return_value.simple_chat_text.side_effect = rename_during_generation
            self.assertIsNone(sync_generate_title(str(self.conversation.conversation_id), self.user.id, self.bot.id))
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.title, '手动名称')
