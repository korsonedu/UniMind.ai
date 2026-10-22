"""Transport smoke with a stub model; no external model or production account."""
import json
import uuid
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from ai_assistant.models import AIChatMessage, Bot
from .models import Note


@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
    CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}},
)
class NoteChatSmoke(TransactionTestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.user = get_user_model().objects.create_superuser('note-chat', 'note-chat@example.test', 'smoke')
        self.bot = Bot.objects.create(name='笔记助手', bot_type='planner', system_prompt='')
        self.note = Note.objects.create(user=self.user, title='久期', content='久期衡量利率敏感性。')
        self.conversation_id = str(uuid.uuid4())
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.payload = {'message': '解释久期', 'bot_id': self.bot.pk,
                        'conversation_id': self.conversation_id, 'note_ids': [self.note.pk]}
        self.stack.enter_context(patch('ai_assistant.views.sync_bot_prompt'))
        self.stack.enter_context(patch('ai_assistant.views._reserve_chat_request',
                                      return_value=SimpleNamespace(acquired=True)))
        self.stack.enter_context(patch('users.learning.release_ai_call'))
        self.stack.enter_context(patch('users.learning.confirm_ai_call'))
        self.stack.enter_context(patch('ai_assistant.services.memory_service.build_memory_context', return_value=('', '')))
        self.extract = self.stack.enter_context(patch('ai_assistant.services.memory_service.extract_memories_async'))
        self.stack.enter_context(patch('ai_assistant.services.memory_service.extract_memories_with_mem0'))
        self.stack.enter_context(patch('ai_assistant.services.trajectory_recorder.record_trajectory'))
        self.stack.enter_context(patch('ai_assistant.tasks.generate_conversation_title.delay'))
        self.stack.enter_context(patch('ai_assistant.services.title_generator.sync_generate_title', return_value='笔记讨论'))
        self.executor = SimpleNamespace()
        self.result = {'choices': [{'message': {'content': '结论 [N1]'}, 'finish_reason': 'stop'}]}

    def assert_saved(self):
        message = AIChatMessage.objects.get(user=self.user, role='assistant', conversation_id=self.conversation_id)
        self.assertEqual(message.metadata['note_sources'][0]['note_id'], self.note.pk)
        self.assertEqual(message.metadata['note_sources'][0]['excerpt'], self.note.content)
        self.assertTrue(AIChatMessage.objects.get(user=self.user, role='user', conversation_id=self.conversation_id).metadata['notes_context_used'])
        self.extract.assert_not_called()
        self.note.refresh_from_db()
        self.assertEqual(self.note.content, '久期衡量利率敏感性。')

    def test_polling_uses_and_persists_read_only_sources(self):
        def run(function, *args, **kwargs):
            function(*args, **kwargs)

        with patch('ai_assistant.utils._THREAD_POOL.submit', side_effect=run), patch(
            'ai_assistant.services.chat_dispatch.dispatch_bot_chat',
            return_value={'result': self.result, 'tool_executor': self.executor},
        ) as dispatch:
            response = self.client.post('/api/ai/chat/', self.payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.note.content, dispatch.call_args.kwargs['history'][-1]['content'])
        self.assert_saved()

    def test_sse_uses_and_persists_read_only_sources(self):
        profile = SimpleNamespace(use_intent_router=False)
        setup = self.stack.enter_context(patch('ai_assistant.services.chat_dispatch.dispatch_bot_chat_sync',
            return_value=([], [], self.executor, profile, 'baseline')))
        self.stack.enter_context(patch('ai_engine.service.AIEngine.call_ai_with_streaming_tools', return_value=self.result))
        response = self.client.post('/api/ai/chat/stream/', self.payload, format='json')

        async def consume():
            return [chunk async for chunk in response.streaming_content]

        output = b''.join(async_to_sync(consume)()).decode()
        self.assertIn('note_sources', output)
        self.assertIn(self.note.content, setup.call_args.kwargs['history'][-1]['content'])
        self.assert_saved()

    def test_websocket_uses_and_persists_read_only_sources(self):
        from channels.routing import URLRouter
        from channels.testing import WebsocketCommunicator
        from django.urls import re_path
        from ai_assistant.consumers import AgentChatConsumer
        self.stack.enter_context(patch('ai_assistant.services.chat_dispatch.dispatch_bot_chat',
            return_value={'result': self.result, 'tool_executor': self.executor}))

        class SmokeConsumer(AgentChatConsumer):
            async def _execute_agent(self, *args, **kwargs):
                await super()._execute_agent(*args, **kwargs)
                await self.send(text_data=json.dumps({'type': 'smoke-finished'}))

        async def communicate():
            application = URLRouter([re_path(r'^ws/(?P<bot_id>\d+)/$', SmokeConsumer.as_asgi())])
            communicator = WebsocketCommunicator(application, f'/ws/{self.bot.pk}/')
            communicator.scope['user'] = self.user
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.send_json_to(self.payload)
            event = await communicator.receive_json_from(timeout=5)
            self.assertEqual(event['type'], 'done', json.dumps(event))
            self.assertEqual(event['metadata']['note_sources'][0]['note_id'], self.note.pk)
            self.assertEqual((await communicator.receive_json_from(timeout=5))['type'], 'smoke-finished')
            await communicator.disconnect()

        async_to_sync(communicate)()
        self.assert_saved()
