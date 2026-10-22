import io
import uuid
import zipfile
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient
from ai_assistant.models import AIChatMessage, Bot, Conversation
from users.models import UserAccessProfile
from .access import accessible_bot
from .models import AgentNoteBinding, ConversationNoteReference, Note, Notebook, NoteLink


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class PrivateNotesSmokeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='notes-owner')
        self.other = get_user_model().objects.create_user(username='other-owner', role='admin', institution_role='owner')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.bot = Bot.objects.create(name='笔记 Agent', system_prompt='', bot_type='planner')

    def create_note(self, **fields):
        response = self.client.post('/api/notes/items/', {'title': '原题', **fields}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_save_version_links_and_owner_isolation(self):
        target = self.create_note(title='目标')
        note = self.create_note(content=f'[目标](/notes/{target["id"]})', tags=['计量', '计量'])
        self.assertEqual(note['tags'], ['计量'])
        url = f'/api/notes/items/{note["id"]}/'
        saved = self.client.patch(url, {'version': 1, 'title': '新标题'}, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(saved.data['version'], 2)
        self.assertEqual(self.client.patch(url, {'version': 1, 'content': '覆盖', 'tags': ['错误']}, format='json').status_code, 409)
        self.assertEqual(self.client.patch(url, {'title': '遗漏版本'}, format='json').status_code, 400)
        self.assertEqual(self.client.get(f'/api/notes/items/{target["id"]}/').data['backlinks'], [{'id': note['id'], 'title': '新标题'}])
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get('/api/notes/items/').data, [])
        self.assertEqual(self.client.get(url + 'export/').status_code, 404)
        self.assertEqual(self.client.patch(url, {'version': 2, 'content': '越权'}, format='json').status_code, 404)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(url).data['tags'], ['计量'])

    def test_trash_restore_and_permanent_delete(self):
        note = self.create_note()
        url = f'/api/notes/items/{note["id"]}/'
        self.assertEqual(self.client.delete(url + '?permanent=1').status_code, 400)
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.client.get('/api/notes/items/').data, [])
        self.assertEqual(len(self.client.get('/api/notes/items/?trash=1').data), 1)
        self.assertEqual(self.client.patch(url, {'version': 2, 'content': '回收站编辑'}, format='json').status_code, 400)
        restored = self.client.post(url + 'restore/')
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.data['version'], 3)
        self.client.delete(url)
        self.assertEqual(self.client.delete(url + '?permanent=1').status_code, 204)
        self.assertFalse(Note.objects.filter(pk=note['id']).exists())

    def test_notebook_cycle_move_delete_and_foreign_target(self):
        root = Notebook.objects.create(user=self.user, name='根')
        child = Notebook.objects.create(user=self.user, parent=root, name='子')
        foreign = Notebook.objects.create(user=self.other, name='别人的目录')
        note = self.create_note(notebook=root.pk)
        self.assertEqual(self.client.patch(f'/api/notes/notebooks/{root.pk}/', {'parent': child.pk}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(f'/api/notes/notebooks/{root.pk}/', {'parent': foreign.pk}, format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/notes/items/', {'notebook': foreign.pk}, format='json').status_code, 400)
        AgentNoteBinding.objects.create(user=self.user, bot=self.bot, notebook=root)
        self.assertEqual(self.client.delete(f'/api/notes/notebooks/{root.pk}/').status_code, 204)
        child.refresh_from_db()
        self.assertIsNone(child.parent_id)
        self.assertIsNone(Note.objects.get(pk=note['id']).notebook_id)
        self.assertEqual(Note.objects.get(pk=note['id']).version, 2)
        self.assertFalse(AgentNoteBinding.objects.exists())

    def test_export_duplicate_names_and_relative_links(self):
        root = Notebook.objects.create(user=self.user, name='课程')
        child = Notebook.objects.create(user=self.user, parent=root, name='课程')
        target = self.create_note(title='同名', notebook=child.pk)
        source = self.create_note(title='同名', notebook=root.pk, tags=['金融'], content=f'[链接](/notes/{target["id"]})')
        response = self.client.get(f'/api/notes/notebooks/{root.pk}/export/')
        self.assertEqual(response.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            files = [name for name in archive.namelist() if name.endswith('.md')]
            self.assertEqual(len(files), 2)
            source_path = next(name for name in files if name.endswith(f'-{source["id"]}.md'))
            content = archive.read(source_path).decode()
            self.assertIn('tags: ["金融"]', content)
            self.assertNotIn(f'/notes/{target["id"]}', content)
            self.assertIn(f'-{target["id"]}.md)', content)
        response = self.client.get(f'/api/notes/items/{source["id"]}/export/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('notebook:', response.content.decode())

    def test_binding_union_subtree_and_target_validation(self):
        root = Notebook.objects.create(user=self.user, name='课程')
        child = Notebook.objects.create(user=self.user, parent=root, name='子课程')
        own = self.create_note(notebook=child.pk)
        foreign = Note.objects.create(user=self.other)
        url = '/api/notes/bindings/'
        for fields in ({}, {'note': own['id'], 'notebook': root.pk}, {'note': foreign.pk}):
            self.assertEqual(self.client.post(url, {'bot': self.bot.pk, **fields}, format='json').status_code, 400)
        for fields in ({'note': own['id']}, {'notebook': root.pk}):
            self.assertEqual(self.client.post(url, {'bot': self.bot.pk, **fields}, format='json').status_code, 201)
        self.assertEqual(len(self.client.get(f'/api/notes/items/?bot={self.bot.pk}').data), 1)
        self.client.delete(f'/api/notes/items/{own["id"]}/')
        self.assertEqual(self.client.get(f'/api/notes/items/?bot={self.bot.pk}').data, [])
        self.client.post(f'/api/notes/items/{own["id"]}/restore/')
        self.assertEqual(len(self.client.get(f'/api/notes/items/?bot={self.bot.pk}').data), 1)
        self.bot.is_active = False
        self.bot.save()
        self.assertEqual(self.client.get(f'{url}?bot={self.bot.pk}').status_code, 404)

    def test_reference_owner_bot_and_conversation_isolation(self):
        own = self.create_note()
        foreign = Note.objects.create(user=self.other)
        conversation_id = uuid.uuid4()
        url = f'/api/notes/references/?bot={self.bot.pk}&conversation_id={conversation_id}'
        self.assertEqual(self.client.get(url).data, {'note_ids': []})
        self.assertFalse(Conversation.objects.filter(conversation_id=conversation_id).exists())
        response = self.client.put(url, {'note_ids': [own['id']]}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data, {'note_ids': [own['id']]})
        self.assertEqual(self.client.put(url, {'note_ids': [foreign.pk]}, format='json').status_code, 400)
        self.assertEqual(self.client.get(url).data, {'note_ids': [own['id']]})
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.put(url, {'note_ids': []}, format='json').status_code, 404)
        self.assertEqual(ConversationNoteReference.objects.count(), 1)
        self.assertEqual(Conversation.objects.get(conversation_id=conversation_id).user_id, self.user.pk)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.put(url, {'note_ids': []}, format='json').data, {'note_ids': []})
        legacy_id = uuid.uuid4()
        AIChatMessage.objects.create(user=self.other, bot=self.bot, conversation_id=legacy_id, role='user', content='旧对话')
        legacy_url = f'/api/notes/references/?bot={self.bot.pk}&conversation_id={legacy_id}'
        self.assertEqual(self.client.get(legacy_url).status_code, 404)
        self.assertEqual(self.client.put(legacy_url, {'note_ids': []}, format='json').status_code, 404)
        self.assertFalse(Conversation.objects.filter(conversation_id=legacy_id).exists())

    def test_agent_permission_revoked_without_removing_private_notes_access(self):
        own = self.create_note()
        profile, _ = UserAccessProfile.objects.get_or_create(user=self.user)
        cached_profile = self.user.access_profile
        self.assertEqual(accessible_bot(self.user, self.bot.pk), self.bot)
        UserAccessProfile.objects.filter(pk=profile.pk).update(blocked_permissions=['ai.assistant'])
        self.assertEqual(cached_profile.blocked_permissions, [])
        with self.assertRaises(PermissionDenied):
            accessible_bot(self.user, self.bot.pk)
        self.assertEqual(self.client.get('/api/notes/items/').status_code, 200)
        self.assertEqual(self.client.post('/api/notes/bindings/', {'bot': self.bot.pk, 'note': own['id']}, format='json').status_code, 403)

    def test_code_examples_and_utf8_export_names(self):
        root = Notebook.objects.create(user=self.user, name='课程' * 100)
        child = Notebook.objects.create(user=self.user, parent=root, name='目录' * 100)
        target = self.create_note(title='目标' * 100, notebook=child.pk)
        example = self.create_note(title='示例目标', notebook=child.pk)
        nested = self.create_note(title='二级列表', notebook=child.pk)
        continuation = self.create_note(title='列表续行', notebook=child.pk)
        code_link = f'[示例](/notes/{example["id"]})'
        code = (f'```markdown\n{code_link}\n```\n\n'
                f'~~~text\n{code_link}\n~~~\n\n'
                f'`{code_link}` 与 ``含 ` 符号 {code_link}``\n\n'
                f'    {code_link}\n\n\t{code_link}\n')
        listing = (f'- 一级\n    - [二级](/notes/{nested["id"]})\n'
                   f'      [续行](/notes/{continuation["id"]})\n\n          {code_link}\n')
        content = f'    {code_link}\n\n[正文](/notes/{target["id"]})\n\n' + listing + '\n普通段落\n\n' + code
        source = self.create_note(title='正文' * 100, notebook=root.pk, content=content)
        self.assertEqual(set(NoteLink.objects.filter(source_id=source['id']).values_list('target_id', flat=True)), {target['id'], nested['id'], continuation['id']})
        response = self.client.get(f'/api/notes/notebooks/{root.pk}/export/')
        self.assertEqual(response.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            for path in archive.namelist():
                self.assertTrue(all(len(part.encode('utf-8')) <= 255 for part in path.split('/')))
            source_path = next(path for path in archive.namelist() if path.endswith(f'-{source["id"]}.md'))
            exported = archive.read(source_path).decode()
            self.assertIn(code, exported)
            self.assertIn(f'          {code_link}', exported)
            self.assertNotIn(f'[二级](/notes/{nested["id"]})', exported)
            self.assertNotIn(f'[续行](/notes/{continuation["id"]})', exported)
            self.assertIn(f'-{nested["id"]}.md)', exported)
            self.assertIn(f'-{continuation["id"]}.md)', exported)
            self.assertNotIn(f'[正文](/notes/{target["id"]})', exported)
            self.assertIn(f'-{target["id"]}.md)', exported)
        self.assertEqual(Note.objects.get(pk=source['id']).content, content)
