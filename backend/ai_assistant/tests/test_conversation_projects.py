import uuid
from types import SimpleNamespace
from unittest.mock import patch
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework.exceptions import PermissionDenied, ValidationError
from users.models import User
from ai_assistant.models import AIChatMessage, Bot, Conversation, ConversationProject
from ai_assistant.views_projects import add_project_context, save_new_conversation_project


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class ConversationProjectTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='project_owner', is_member=True)
        self.other = User.objects.create_user(username='project_other', is_member=True)
        self.bot = Bot.objects.create(name='小宇')
        self.project = ConversationProject.objects.create(user=self.user, name='金融学复习')
        self.foreign_project = ConversationProject.objects.create(user=self.other, name='私人项目')
        self.conversation = Conversation.objects.create(user=self.user, bot=self.bot, conversation_id=uuid.uuid4())
        self.message = AIChatMessage.objects.create(user=self.user, bot=self.bot, conversation_id=self.conversation.conversation_id, role='user', content='复习利率')
        self.url = f'/api/ai/conversations/{self.conversation.conversation_id}/project/'
        self.client.force_authenticate(self.user)

    def test_projects_are_private_and_persist_changes(self):
        response = self.client.get('/api/ai/projects/')
        self.assertEqual([project['id'] for project in response.data], [self.project.id])
        created = self.client.post('/api/ai/projects/', {'name': '数学复习', 'instructions': '先讲概率，再给练习'})
        self.assertEqual(created.status_code, 201)
        renamed = self.client.patch(f'/api/ai/projects/{created.data["id"]}/', {'name': '数学冲刺', 'instructions': '每次出三道题'})
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(self.client.get(f'/api/ai/projects/{created.data["id"]}/').data['name'], '数学冲刺')
        self.assertEqual(self.client.get(f'/api/ai/projects/{created.data["id"]}/').data['instructions'], '每次出三道题')
        self.assertEqual(self.client.patch(f'/api/ai/projects/{self.foreign_project.id}/', {'name': '不可修改'}).status_code, 404)
        self.assertEqual(self.client.delete(f'/api/ai/projects/{self.foreign_project.id}/').status_code, 404)

    def test_project_created_with_chat_is_present_in_history_and_conversation_list(self):
        self.conversation.project = self.project
        self.conversation.save()
        history = self.client.get('/api/ai/history/', {'bot_id': self.bot.id})
        self.assertEqual(history.data[0]['conversation_project'], self.project.id)
        metadata = self.client.get('/api/ai/conversations/')
        self.assertEqual(metadata.data[0]['project_id'], self.project.id)
        self.assertEqual(self.client.patch(self.url, {'project_id': None}, format='json').status_code, 404)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.project_id, self.project.id)

    def test_uncategorized_chat_cannot_be_moved(self):
        self.assertEqual(self.client.patch(self.url, {'project_id': self.project.id}).status_code, 404)
        save_new_conversation_project(SimpleNamespace(user=self.user, data={'project_id': self.project.id}), self.bot, self.conversation.conversation_id)
        self.conversation.refresh_from_db()
        self.assertIsNone(self.conversation.project_id)

    def test_deleting_project_removes_only_its_conversations_and_messages(self):
        self.conversation.project = self.project
        self.conversation.save()
        second = Conversation.objects.create(user=self.user, bot=self.bot, conversation_id=uuid.uuid4(), project=self.project)
        second_message = AIChatMessage.objects.create(user=self.user, bot=self.bot, conversation_id=second.conversation_id, role='assistant', content='项目回复')
        unrelated = AIChatMessage.objects.create(user=self.user, bot=self.bot, conversation_id=uuid.uuid4(), role='user', content='未分类对话')
        foreign = Conversation.objects.create(user=self.other, bot=self.bot, conversation_id=uuid.uuid4(), project=self.foreign_project)
        foreign_message = AIChatMessage.objects.create(user=self.other, bot=self.bot, conversation_id=foreign.conversation_id, role='user', content='其他账号')
        self.assertEqual(self.client.delete(f'/api/ai/projects/{self.project.id}/').status_code, 204)
        self.assertFalse(Conversation.objects.filter(pk__in=[self.conversation.id, second.id]).exists())
        self.assertFalse(AIChatMessage.objects.filter(pk__in=[self.message.id, second_message.id]).exists())
        self.assertTrue(AIChatMessage.objects.filter(pk=unrelated.id).exists())
        self.assertTrue(AIChatMessage.objects.filter(pk=foreign_message.id).exists())
        self.assertTrue(Conversation.objects.filter(pk=foreign.id).exists())

    def test_legacy_chat_without_metadata_stays_uncategorized(self):
        conversation_id = uuid.uuid4()
        AIChatMessage.objects.create(user=self.user, bot=self.bot, conversation_id=conversation_id, role='user', content='历史对话')
        response = self.client.patch(f'/api/ai/conversations/{conversation_id}/project/', {'project_id': self.project.id})
        self.assertEqual(response.status_code, 404)
        save_new_conversation_project(SimpleNamespace(user=self.user, data={'project_id': self.project.id}), self.bot, conversation_id)
        self.assertIsNone(Conversation.objects.get(conversation_id=conversation_id).project_id)

    def test_deleting_one_chat_preserves_project_and_siblings(self):
        self.conversation.project = self.project
        self.conversation.save()
        sibling = Conversation.objects.create(user=self.user, bot=self.bot, conversation_id=uuid.uuid4(), project=self.project)
        sibling_message = AIChatMessage.objects.create(user=self.user, bot=self.bot, conversation_id=sibling.conversation_id, role='user', content='另一个会话')
        response = self.client.post('/api/ai/delete-conversation/', {'conversation_id': str(self.conversation.conversation_id)})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Conversation.objects.filter(pk=self.conversation.id).exists())
        self.assertFalse(AIChatMessage.objects.filter(pk=self.message.id).exists())
        self.assertTrue(ConversationProject.objects.filter(pk=self.project.id).exists())
        self.assertTrue(AIChatMessage.objects.filter(pk=sibling_message.id).exists())

    def test_project_deletion_also_cascades_outside_api(self):
        self.conversation.project = self.project
        self.conversation.save()
        self.project.delete()
        self.assertFalse(Conversation.objects.filter(pk=self.conversation.id).exists())
        self.assertFalse(AIChatMessage.objects.filter(pk=self.message.id).exists())

    def test_new_uncategorized_chat_records_permanent_assignment(self):
        conversation_id = uuid.uuid4()
        save_new_conversation_project(SimpleNamespace(user=self.user, data={}), self.bot, conversation_id)
        save_new_conversation_project(SimpleNamespace(user=self.user, data={'project_id': self.project.id}), self.bot, conversation_id)
        self.assertIsNone(Conversation.objects.get(conversation_id=conversation_id).project_id)

    def test_new_chat_inherits_project_and_does_not_overwrite_existing_assignment(self):
        conversation_id = uuid.uuid4()
        request = SimpleNamespace(user=self.user, data={'project_id': self.project.id})
        save_new_conversation_project(request, self.bot, conversation_id)
        self.assertEqual(Conversation.objects.get(conversation_id=conversation_id).project_id, self.project.id)
        request.data = {'project_id': None}
        save_new_conversation_project(request, self.bot, conversation_id)
        self.assertEqual(Conversation.objects.get(conversation_id=conversation_id).project_id, self.project.id)

    def test_stream_rejects_foreign_project_before_creating_messages(self):
        conversation_id = uuid.uuid4()
        with patch('ai_assistant.views.sync_bot_prompt'), patch('users.permissions.HasQuota.has_permission', return_value=True):
            response = self.client.post('/api/ai/chat/stream/', {'bot_id': self.bot.id, 'message': '测试', 'conversation_id': str(conversation_id), 'project_id': self.foreign_project.id})
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(AIChatMessage.objects.filter(conversation_id=conversation_id).exists())

    def test_new_chat_rejects_foreign_project_and_uuid(self):
        with self.assertRaises(ValidationError):
            save_new_conversation_project(SimpleNamespace(user=self.user, data={'project_id': self.foreign_project.id}), self.bot, uuid.uuid4())
        foreign = Conversation.objects.create(user=self.other, bot=self.bot, conversation_id=uuid.uuid4())
        with self.assertRaises(PermissionDenied):
            save_new_conversation_project(SimpleNamespace(user=self.user, data={'project_id': self.project.id}), self.bot, foreign.conversation_id)

    def test_invalid_names_and_unauthenticated_access(self):
        for name in ['', '   ', '长' * 61]:
            self.assertEqual(self.client.post('/api/ai/projects/', {'name': name}).status_code, 400)
        self.client.force_authenticate(None)
        self.assertIn(self.client.get('/api/ai/projects/').status_code, (401, 403))

    def test_project_context_is_current_private_and_does_not_merge_chats(self):
        self.conversation.project = self.project
        self.conversation.save()
        self.project.instructions = '先讲利率，再用一道题检验'
        self.project.save()
        history = [{'role': 'assistant', 'content': '当前对话已有内容'}]
        contextual = add_project_context(self.user, self.conversation.conversation_id, history)
        self.assertEqual(contextual[1:], history)
        self.assertEqual(len(history), 1)
        self.assertEqual(contextual[0]['role'], 'user')
        self.assertIn('先讲利率', contextual[0]['content'])
        self.project.instructions = '改为直接出三道题'
        self.project.save()
        self.assertIn('直接出三道题', add_project_context(self.user, self.conversation.conversation_id, history)[0]['content'])
        self.assertEqual(add_project_context(self.other, self.conversation.conversation_id, history), history)
        self.conversation.project = self.foreign_project
        self.conversation.save()
        self.foreign_project.instructions = '私人要求'
        self.foreign_project.save()
        self.assertEqual(add_project_context(self.user, self.conversation.conversation_id, history), history)

    def test_project_context_is_optional_and_length_is_validated(self):
        self.assertEqual(add_project_context(self.user, uuid.uuid4(), []), [])
        response = self.client.post('/api/ai/projects/', {'name': '长度检查', 'instructions': '长' * 4001})
        self.assertEqual(response.status_code, 400)

    def test_checkin_reports_creation_only_once(self):
        with patch('users.services.achievements.check_and_unlock'):
            first = self.client.post('/api/users/me/checkin/')
            repeated = self.client.post('/api/users/me/checkin/')
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.data['created'])
        self.assertFalse(repeated.data['created'])
