import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.exceptions import PermissionDenied, ValidationError

from ai_assistant.models import AIChatMessage, Bot, Conversation
from .context import prepare_note_context, conversation_uses_notes
from .models import Note, Notebook


class NoteContextSmoke(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser('notes-context', 'notes-context@example.test', 'smoke')
        self.other = get_user_model().objects.create_user('notes-other', 'notes-other@example.test', 'smoke')
        self.bot = Bot.objects.create(is_xiaoyu=True, name='笔记助手', bot_type='planner', system_prompt='')
        self.book = Notebook.objects.create(user=self.user, name='固定收益')
        self.note = Note.objects.create(user=self.user, notebook=self.book, title='久期', content='久期衡量利率敏感性。')

    def context(self, conversation_id=None, **kwargs):
        return prepare_note_context(self.user, self.bot, conversation_id or uuid.uuid4(), '解释久期', **kwargs)

    def test_temporary_scope_and_source_snapshot(self):
        conversation_id = uuid.uuid4()
        _, sources = self.context(conversation_id, note_ids=[self.note.pk])
        self.assertEqual(sources[0]['note_id'], self.note.pk)
        self.assertEqual(sources[0]['kind'], 'temporary')
        self.assertEqual(self.context(conversation_id)[1][0]['note_id'], self.note.pk)
        self.assertEqual(self.context()[1], [])
        Note.objects.filter(pk=self.note.pk).update(content='新的内容', version=2)
        self.assertEqual(sources[0]['excerpt'], '久期衡量利率敏感性。')
        self.assertEqual(self.context(conversation_id)[1][0]['version'], 2)
        self.context(conversation_id, note_ids=[])
        self.assertEqual(self.context(conversation_id)[1], [])

    def test_foreign_ids_and_conversation_are_rejected(self):
        foreign = Note.objects.create(user=self.other, title='私人')
        with self.assertRaises(ValidationError):
            self.context(note_ids=[foreign.pk])
        conversation = Conversation.objects.create(user=self.other, bot=self.bot, conversation_id=uuid.uuid4())
        with self.assertRaises(PermissionDenied):
            self.context(conversation.conversation_id, note_ids=[self.note.pk])

    def test_note_context_does_not_write_content_or_train_trajectory(self):
        conversation_id = uuid.uuid4()
        self.context(conversation_id, note_ids=[self.note.pk], selection='久期')
        self.note.refresh_from_db()
        self.assertEqual(self.note.content, '久期衡量利率敏感性。')
        AIChatMessage.objects.create(user=self.user, bot=self.bot, role='user', content='讨论',
                                     conversation_id=conversation_id, metadata={'notes_context_used': True})
        self.assertTrue(conversation_uses_notes(self.user, conversation_id))
        from ai_assistant.tasks import record_trajectory_async
        with patch('ai_assistant.models.AITrajectory.objects.create') as create:
            record_trajectory_async(self.user.pk, self.bot.pk, str(conversation_id), [], [], [])
        create.assert_not_called()
