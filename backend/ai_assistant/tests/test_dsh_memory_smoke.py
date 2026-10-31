"""Memory extraction through the server DSH structured task."""
import json
import sys
import uuid
from unittest.mock import patch

from django.test import TestCase, override_settings

from ai_assistant.models import AgentMemory, MemoryExtractionLog, Bot, Conversation, AIChatMessage
from ai_assistant.services.memory_service import _extract_memories_via_dsh, _merge_memory_candidates
from users.models import User


class DshMemorySmoke(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='memory-smoke')
        self.conversation_id = str(uuid.uuid4())
        self.history = [
            {'role': 'user', 'content': '我喜欢先看具体例子再看公式推导'},
            {'role': 'assistant', 'content': '明白，我会先用例子引入。'},
        ]
        bot = Bot.objects.create(name='小宇', bot_type='planner', system_prompt='合成记忆验证')
        self.conversation = Conversation.objects.create(user=self.user, bot=bot, conversation_id=self.conversation_id)
        AIChatMessage.objects.create(user=self.user, bot=bot, conversation_id=self.conversation_id,
            role='user', content=self.history[0]['content'])
        self.candidate = {
            'memory_type': 'preference',
            'key': '讲解风格',
            'value': '先看例子再看公式推导',
            'confidence': 0.9,
            'evidence': '我喜欢先看具体例子再看公式推导',
        }

    def _run(self, candidates):
        with patch('ai_assistant.services.dsh_tasks.run_structured', return_value={'memories': candidates}) as task, \
             patch('django.db.connections.close_all'):
            _extract_memories_via_dsh(self.user.id, self.history, self.conversation_id)
        return task

    def test_dsh_memory_requires_evidence_and_saves_once(self):
        task = self._run([self.candidate, {**self.candidate, 'key': '无证据', 'evidence': '用户没说过'}])
        task.assert_called_once()
        self.assertEqual(AgentMemory.objects.filter(user=self.user).count(), 1)
        memory = AgentMemory.objects.get(user=self.user)
        self.assertEqual(memory.source, 'dsh')
        self.assertEqual(memory.evidence, self.candidate['evidence'])
        self.assertEqual(memory.source_conversation_id, self.conversation_id)
        again = self._run([self.candidate])
        again.assert_not_called()
        self.assertEqual(AgentMemory.objects.count(), 1)
        self.assertTrue(MemoryExtractionLog.objects.filter(user=self.user, conversation_id=self.conversation_id).exists())

    def test_merge_skips_low_confidence_manual_and_disabled(self):
        self.assertEqual(_merge_memory_candidates(self.user, [{**self.candidate, 'confidence': 0.4}],
            self.history[0]['content'], self.conversation_id), 0)
        self.assertFalse(AgentMemory.objects.exists())
        manual = AgentMemory.objects.create(user=self.user, memory_type='preference', key='讲解风格',
            value='用户手动设置', source='manual', confidence=1.0)
        self.assertEqual(_merge_memory_candidates(self.user, [self.candidate],
            self.history[0]['content'], self.conversation_id), 0)
        manual.refresh_from_db()
        self.assertEqual(manual.value, '用户手动设置')
        AgentMemory.objects.filter(pk=manual.pk).update(is_active=False, source='dsh', confidence=0.1)
        self.assertEqual(_merge_memory_candidates(self.user, [self.candidate],
            self.history[0]['content'], self.conversation_id), 0)
        manual.refresh_from_db()
        self.assertFalse(manual.is_active)

    def test_deleted_memory_is_not_recreated_for_same_turn(self):
        self._run([self.candidate])
        AgentMemory.objects.filter(user=self.user).delete()
        again = self._run([self.candidate])
        again.assert_not_called()
        self.assertFalse(AgentMemory.objects.exists())

    def test_dsh_failure_does_not_write_log(self):
        with patch('ai_assistant.services.dsh_tasks.run_structured', side_effect=RuntimeError('offline')), \
             patch('django.db.connections.close_all'):
            _extract_memories_via_dsh(self.user.id, self.history, self.conversation_id)
        self.assertFalse(MemoryExtractionLog.objects.exists())

    def test_deleted_source_during_model_call_cannot_create_memories(self):
        def deleted_source(*args):
            self.conversation.delete()
            return {'memories': [self.candidate]}
        with patch('ai_assistant.services.dsh_tasks.run_structured', side_effect=deleted_source), patch('django.db.connections.close_all'):
            _extract_memories_via_dsh(self.user.id, self.history, self.conversation_id)
        self.assertFalse(AgentMemory.objects.exists())
        self.assertFalse(MemoryExtractionLog.objects.exists())

    @override_settings(UNIMIND_DSH_MEMORY_ENABLED=True)
    def test_mem0_auto_extract_is_disabled_when_dsh_memory_enabled(self):
        from ai_assistant.services.memory_service import extract_memories_with_mem0
        with patch('ai_assistant.services.memory_service.USE_MEM0', True), \
             patch('ai_assistant.utils._THREAD_POOL.submit') as submit:
            extract_memories_with_mem0(self.user, self.history)
        submit.assert_not_called()


def test_memory_task_uses_fast_single_request(settings, tmp_path, monkeypatch):
    from ai_assistant.services.dsh_tasks import run_structured
    settings.DEBUG = True
    settings.UNIMIND_DSH_PYTHON = sys.executable
    settings.UNIMIND_DSH_STATE_DIR = str(tmp_path)
    settings.UNIMIND_DSH_FIXTURE_URL = 'http://127.0.0.1:8912/v1/messages'
    monkeypatch.setenv('AI_MODEL_FAST', 'memory-fast-model')
    with patch('ai_assistant.services.dsh_tasks.subprocess.Popen') as popen:
        process = popen.return_value.__enter__.return_value
        process.returncode = 0
        process.communicate.return_value = (json.dumps({'status': 200, 'result': {'memories': []}}).encode(), b'')
        assert run_structured('assistant.memory_extract', '用户: 我喜欢先看例子') == {'memories': []}
        payload = json.loads(process.communicate.call_args.args[0])
        policy = payload['context']['model_policy']
        assert (policy['tier'], policy['model'], policy['max_requests'], policy['max_tokens']) == ('fast', 'memory-fast-model', 1, 800)
        wire = payload['context']['tools'][0]['function']['parameters']
        assert wire['properties']['memories']['type'] == 'array'
        assert '记忆' in payload['context']['task_instruction']
