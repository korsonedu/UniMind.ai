"""Isolated smoke coverage; model and broker calls are mocked."""
import json
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from ai_assistant.models import Bot
from users.models import UserAccessProfile
from .awareness import content_signature, note_message_metadata, schedule_note
from .context import prepare_note_context
from .models import Note, NoteAISettings, NoteUnderstanding
from .tasks import understand_note, validated_result


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class NoteAwarenessSmoke(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='awareness-owner')
        self.other = get_user_model().objects.create_user(username='awareness-other')
        self.bot = Bot.objects.create(name='小宇', bot_type='planner', system_prompt='')
        self.other_bot = Bot.objects.create(name='课程助手', bot_type='planner', system_prompt='')
        self.note = Note.objects.create(user=self.user, title='久期', content='久期衡量利率敏感性。我不理解凸性。')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.model = patch('ai_engine.service.AIEngine.call_ai', return_value={'choices': [{'message': {'content': json.dumps({
            'topics': [{'text': '固定收益敏感性', 'evidence': '久期衡量利率敏感性'}],
            'explanations': [], 'questions': [{'text': '凸性疑问', 'evidence': '我不理解凸性'}],
        }, ensure_ascii=False)}}]}).start()
        self.queue = patch('notes.tasks.understand_note.apply_async').start()
        self.batch_queue = patch('notes.tasks.understand_user_notes.apply_async').start()
        self.addCleanup(patch.stopall)

    def enable(self):
        response = self.client.patch('/api/notes/ai-settings/', {'enabled': True}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        schedule_note(self.note)
        return NoteAISettings.objects.get(user=self.user)

    def run_understanding(self, settings):
        understand_note.run(self.note.pk, self.note.version, settings.epoch, content_signature(self.note))

    def context(self, bot=None, **kwargs):
        return prepare_note_context(self.user, bot or self.bot, uuid.uuid4(), kwargs.pop('message', '解释久期'), **kwargs)

    def test_default_acknowledgement_private_lookup_and_explicit_reference(self):
        self.assertEqual(self.client.get('/api/notes/ai-settings/').data, {'enabled': False, 'acknowledged': False})
        schedule_note(self.note)
        self.assertFalse(NoteUnderstanding.objects.exists())
        self.assertEqual(self.context(), ('', []))
        foreign = Note.objects.create(user=self.other, title='久期秘密')
        trashed = Note.objects.create(user=self.user, title='久期删除', deleted_at=timezone.now())
        found = self.client.get(f'/api/notes/lookup/?ids={self.note.pk},{foreign.pk},{trashed.pk}').data
        self.assertEqual(found, [{'id': self.note.pk, 'title': '久期', 'notebook': None, 'version': 1}])
        self.assertEqual(self.client.get('/api/notes/lookup/?q=久期').data, found)
        self.assertEqual(self.client.get('/api/notes/lookup/?ids=x').status_code, 400)
        response = self.client.patch('/api/notes/ai-settings/', {'enabled': False}, format='json')
        self.assertEqual(response.data, {'enabled': False, 'acknowledged': True})
        _, sources = self.context(note_ids=[self.note.pk])
        self.assertEqual(note_message_metadata('context', sources)['note_attachments'], [
            {'note_id': self.note.pk, 'title': '久期', 'version': 1}])
        self.model.assert_not_called()

    def test_enabled_understanding_retrieval_dedup_and_other_agent_scope(self):
        settings = self.enable()
        self.run_understanding(settings)
        context, sources = self.context(message='固定收益敏感性')
        self.assertEqual([s['note_id'] for s in sources], [self.note.pk])
        self.assertIn('后台理解线索', context)
        self.assertEqual(sources[0]['version'], 1)
        self.assertEqual(note_message_metadata(context, sources)['note_attachments'], [])
        self.assertEqual(self.context(message='今天天气怎样'), ('', []))
        self.assertEqual(self.context(bot=self.other_bot), ('', []))
        self.assertEqual(self.context(bot=self.other_bot, note_ids=[self.note.pk])[1][0]['kind'], 'temporary')
        self.note.version = 2
        self.note.save(update_fields=['version'])
        schedule_note(self.note)
        self.run_understanding(settings)
        self.assertEqual(self.model.call_count, 1)
        self.assertEqual(NoteUnderstanding.objects.get(note=self.note).version, 2)

    def test_disable_then_reenable_invalidates_late_epoch_but_at_still_works(self):
        old = self.enable()
        def disable_enable(**kwargs):
            self.client.patch('/api/notes/ai-settings/', {'enabled': False}, format='json')
            self.assertEqual(self.context(), ('', []))
            self.assertEqual(self.context(note_ids=[self.note.pk])[1][0]['kind'], 'temporary')
            self.client.patch('/api/notes/ai-settings/', {'enabled': True}, format='json')
            schedule_note(self.note)
            return self.model.return_value
        self.model.side_effect = disable_enable
        self.run_understanding(old)
        understanding = NoteUnderstanding.objects.get(note=self.note)
        self.assertEqual(understanding.status, 'pending')
        self.assertEqual(understanding.result, {})
        self.assertGreater(understanding.epoch, old.epoch)

    def test_edit_restore_race_cannot_accept_old_content_version(self):
        settings = self.enable()
        def edit_restore(**kwargs):
            Note.objects.filter(pk=self.note.pk).update(content='另一个版本', version=2)
            Note.objects.filter(pk=self.note.pk).update(content=self.note.content, version=3)
            self.note.refresh_from_db()
            schedule_note(self.note)
            return self.model.return_value
        self.model.side_effect = edit_restore
        self.run_understanding(settings)
        understanding = NoteUnderstanding.objects.get(note=self.note)
        self.assertEqual(understanding.version, 3)
        self.assertEqual(understanding.status, 'pending')
        self.assertEqual(understanding.result, {})

    def test_trash_and_permission_revocation_reject_late_result(self):
        settings = self.enable()
        def revoke(**kwargs):
            profile, _ = UserAccessProfile.objects.get_or_create(user=self.user)
            UserAccessProfile.objects.filter(pk=profile.pk).update(blocked_permissions=['ai.assistant'])
            return self.model.return_value
        self.model.side_effect = revoke
        self.run_understanding(settings)
        self.assertNotEqual(NoteUnderstanding.objects.get(note=self.note).status, 'ready')
        self.assertEqual(self.client.patch('/api/notes/ai-settings/', {'enabled': True}, format='json').status_code, 403)
        self.assertEqual(self.client.delete(f'/api/notes/items/{self.note.pk}/').status_code, 204)
        self.assertEqual(NoteUnderstanding.objects.get(note=self.note).status, 'invalid')
        self.assertEqual(self.client.get('/api/notes/lookup/').data, [])

    def test_queue_failure_does_not_fail_save_and_bad_evidence_retries(self):
        self.enable()
        self.queue.side_effect = RuntimeError('broker unavailable')
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(f'/api/notes/items/{self.note.pk}/', {'version': 1, 'content': '久期新疑问'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Note.objects.get(pk=self.note.pk).content, '久期新疑问')
        self.note.refresh_from_db()
        settings = NoteAISettings.objects.get(user=self.user)
        self.model.return_value = {'choices': [{'message': {'content': '{"topics":[{"text":"编造","evidence":"没有此句"}],"explanations":[],"questions":[]}'}}]}
        from celery.exceptions import Retry
        with patch.object(understand_note, 'retry', side_effect=Retry) as retry, self.assertRaises(Retry):
            self.run_understanding(settings)
        self.assertEqual(retry.call_args.kwargs['countdown'], 60)
        self.assertEqual(NoteUnderstanding.objects.get(note=self.note).status, 'failed')
        with self.assertRaises(ValueError):
            validated_result('{"topics":[],"explanations":[],"questions":[],"extra":[]}', '原文')
