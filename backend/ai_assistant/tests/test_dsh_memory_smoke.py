"""Memory extraction through the server DSH structured task."""
import json
import sys
import uuid
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from ai_assistant.models import AgentMemory, MemoryExtractionLog, Bot, Conversation, AIChatMessage
from ai_assistant.services.memory_service import _extract_memories_via_dsh, _merge_memory_candidates
from ai_assistant.services.ulr_memory import extract_answer_memory
from users.models import CourseStudentStatus, User
from ai_assistant.services.memory_core import fact_prompt, fact_snapshot, merge_fact
from rest_framework.test import APIClient


class DshMemorySmoke(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='memory-smoke')
        self.conversation_id = str(uuid.uuid4())
        self.history = [
            {'role': 'user', 'content': '我喜欢先看具体例子再看公式推导'},
            {'role': 'assistant', 'content': '明白，我会先用例子引入。'},
        ]
        bot = Bot.objects.create(is_xiaoyu=True, name='小宇', bot_type='planner', system_prompt='合成记忆验证')
        self.conversation = Conversation.objects.create(user=self.user, bot=bot, conversation_id=self.conversation_id)
        self.question = AIChatMessage.objects.create(user=self.user, bot=bot, conversation_id=self.conversation_id,
            role='user', content=self.history[0]['content'])
        self.answer = self.answer_for(self.question)
        self.candidate = {
            'memory_type': 'preference',
            'key': '讲解风格',
            'value': '先看例子再看公式推导',
            'confidence': 0.9,
            'evidence': '我喜欢先看具体例子再看公式推导',
        }

    def answer_for(self, question):
        return AIChatMessage.objects.create(user=self.user, bot=question.bot, conversation_id=self.conversation_id,
            role='assistant', content=self.history[1]['content'],
            metadata={'learning_turn': {'message_id': question.pk, 'completed': True}})

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

    def test_delete_during_extraction_blocks_late_write_but_allows_new_turn(self):
        fact = AgentMemory.objects.create(user=self.user, key=self.candidate['key'], value='旧偏好', source='dsh')
        def pending(*_args, **_kwargs):
            fact.delete()
            return {'memories': [self.candidate]}
        with patch('ai_assistant.services.dsh_tasks.run_structured', side_effect=pending), patch('django.db.connections.close_all'):
            _extract_memories_via_dsh(self.user.pk, self.history, self.conversation_id)
        self.assertFalse(AgentMemory.objects.filter(user=self.user).exists())
        self.assertEqual(MemoryExtractionLog.objects.get().saved_count, 0)
        self.history[0]['content'] += '，这是我的长期习惯。'
        AIChatMessage.objects.create(user=self.user, bot=self.conversation.bot, conversation_id=self.conversation_id,
            role='user', content=self.history[0]['content'])
        self._run([self.candidate])
        self.assertEqual(AgentMemory.objects.get(user=self.user).value, self.candidate['value'])

    @override_settings(UNIMIND_DSH_MEMORY_ENABLED=True)
    def test_queued_extraction_keeps_the_revision_from_before_deletion(self):
        from ai_assistant.services.memory_service import extract_memories_async
        fact = AgentMemory.objects.create(user=self.user, key=self.candidate['key'], value='旧偏好', source='dsh')
        with patch('ai_assistant.utils._THREAD_POOL.submit') as queue:
            extract_memories_async(self.user, self.history, self.conversation_id)
        function, *arguments = queue.call_args.args
        fact.delete()
        with patch('ai_assistant.services.dsh_tasks.run_structured', return_value={'memories': [self.candidate]}), \
             patch('django.db.connections.close_all'):
            function(*arguments)
        self.assertFalse(AgentMemory.objects.filter(user=self.user).exists())

    def test_user_edit_wins_for_all_readers_and_automatic_writers(self):
        self._run([self.candidate])
        memory = AgentMemory.objects.get(user=self.user)
        client = APIClient()
        client.force_authenticate(self.user)
        url = f'/api/ai/memories/{memory.pk}/'
        before = fact_snapshot(self.user)['version']
        response = client.patch(url, {'value': '先讲公式'}, format='json')
        self.assertEqual(response.status_code, 200)
        memory.refresh_from_db()
        self.assertEqual((memory.source, memory.evidence, memory.source_conversation_id), ('manual', '', ''))
        after = fact_snapshot(self.user)
        self.assertNotEqual(before, after['version'])
        self.assertEqual(after['items'][0]['value'], '先讲公式')
        self.assertIn('先讲公式', fact_prompt(self.user))
        self.assertEqual(fact_snapshot(self.user)['version'], after['version'])
        for source in ('auto', 'dsh'):
            self.assertEqual(merge_fact(self.user, memory_type='preference', key=memory.key,
                value='自动覆盖', confidence=1.0, source=source), 0)
        self.assertEqual(client.patch(url, {'is_active': False}, format='json').status_code, 200)
        self.assertEqual(fact_snapshot(self.user)['items'], [])
        self.assertEqual(fact_prompt(self.user), '')
        self.assertEqual(client.delete(url).status_code, 204)
        self.assertEqual(self._run([self.candidate]).call_count, 0)
        self.assertFalse(AgentMemory.objects.filter(user=self.user).exists())

    def test_core_snapshot_preserves_dsh_token_and_owner_scope(self):
        import hashlib
        from ai_assistant.services.dsh_service import memory_snapshot
        self._run([self.candidate])
        other = User.objects.create_user(username='private-facts')
        AgentMemory.objects.create(user=other, key='private', value='不可见')
        rows = list(AgentMemory.objects.filter(user=self.user, is_active=True).order_by(
            '-confidence', '-updated_at', 'id').values('id', 'memory_type', 'key', 'value', 'source', 'updated_at')[:20])
        expected = hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
        self.assertEqual(memory_snapshot(self.user), {'version': expected, 'items': rows})

    def test_automatic_cleanup_preserves_explicit_user_settings(self):
        from datetime import timedelta
        from django.utils import timezone
        from ai_assistant.tasks import cleanup_stale_memories
        manual = AgentMemory.objects.create(user=self.user, key='长期设置', value='用户设置', source='manual', confidence=0.1)
        automatic = AgentMemory.objects.create(user=self.user, key='旧观察', value='自动提取', source='dsh', confidence=0.1)
        AgentMemory.objects.filter(pk__in=[manual.pk, automatic.pk]).update(updated_at=timezone.now() - timedelta(days=61))
        with patch('ai_assistant.tasks.USE_MEM0', False):
            self.assertEqual(cleanup_stale_memories(), 1)
        self.assertEqual([row['id'] for row in fact_snapshot(self.user)['items']], [manual.pk])

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

    def test_ulr_discards_memory_when_entitlement_is_revoked_during_extraction(self):
        status = CourseStudentStatus.objects.create(user=self.user, is_course_student=True)

        def revoke(*args, **kwargs):
            CourseStudentStatus.objects.filter(pk=status.pk).update(is_course_student=False)
            return {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [{
                'function': {'name': 'submit_memories', 'arguments': json.dumps({'memories': [self.candidate]})},
            }]}}]}

        with patch('ai_engine.service.AIEngine.call_provider', side_effect=revoke) as call:
            extract_answer_memory(self.question.pk, self.answer.pk)
            extract_answer_memory(self.question.pk, self.answer.pk)
        call.assert_called_once()
        self.assertFalse(AgentMemory.objects.exists())
        self.assertFalse(MemoryExtractionLog.objects.exists())

    def test_ulr_repeated_text_does_not_replace_a_deleted_source(self):
        CourseStudentStatus.objects.create(user=self.user, is_course_student=True)
        question_id, answer_id = self.question.pk, self.answer.pk

        def replace_question(*_args, **_kwargs):
            AIChatMessage.objects.filter(pk=question_id).delete()
            return {'memories': [self.candidate]}

        repeated = AIChatMessage.objects.create(user=self.user, bot=self.question.bot,
            conversation_id=self.conversation_id, role='user', content=self.question.content)
        new_answer = self.answer_for(repeated)
        with patch('ai_assistant.services.ulr_memory.run_collector', side_effect=replace_question) as collect:
            self.assertEqual(extract_answer_memory(repeated.pk, answer_id), 0)
            self.assertEqual(extract_answer_memory(question_id, answer_id), 0)
            self.assertEqual(extract_answer_memory(question_id, answer_id), 0)
            collect.assert_called_once()
        self.assertFalse(AgentMemory.objects.exists())
        self.assertFalse(MemoryExtractionLog.objects.exists())
        with patch('ai_assistant.services.ulr_memory.run_collector', return_value={'memories': [self.candidate]}) as collect:
            self.assertEqual(extract_answer_memory(repeated.pk, new_answer.pk), 1)
            self.assertEqual(extract_answer_memory(repeated.pk, new_answer.pk), 0)
            collect.assert_called_once()
        log = MemoryExtractionLog.objects.get()
        self.assertEqual((log.source_message_id, log.answer_message_id), (repeated.pk, new_answer.pk))

    def test_ulr_memory_delivery_must_match_the_pending_exchange(self):
        from ai_assistant.models import PendingMemoryExtraction
        from ai_assistant.tasks import extract_memory_turn

        CourseStudentStatus.objects.create(user=self.user, is_course_student=True)
        job = PendingMemoryExtraction.objects.create(source_message=self.question, answer_message=self.answer)
        other = AIChatMessage.objects.create(user=self.user, bot=self.question.bot, conversation_id=self.conversation_id,
            role='user', content='这是另一轮提问。')
        other_answer = self.answer_for(other)
        dispatch_after = job.dispatch_after
        with patch('ai_assistant.services.ulr_memory.run_collector', return_value={'memories': [self.candidate]}) as collect, \
                patch('django.db.connections.close_all'):
            for ids in ((other.pk, self.answer.pk), (self.question.pk, other_answer.pk)):
                assert extract_memory_turn.run(*ids, pending_job_id=job.pk) == 0
            collect.assert_not_called()
            job.refresh_from_db()
            assert job.running_until is None and job.dispatch_after == dispatch_after
            assert not AgentMemory.objects.exists() and not MemoryExtractionLog.objects.exists()
            assert extract_memory_turn.run(self.question.pk, self.answer.pk, pending_job_id=job.pk) == 1
            assert extract_memory_turn.run(self.question.pk, self.answer.pk, pending_job_id=job.pk) == 0
            collect.assert_called_once()

        log = MemoryExtractionLog.objects.get()
        assert (log.source_message_id, log.answer_message_id) == (self.question.pk, self.answer.pk)
        assert AgentMemory.objects.count() == 1
        assert not PendingMemoryExtraction.objects.filter(pk=job.pk).exists()

    def test_ulr_memory_retries_transient_provider_failure_once(self):
        from ai_assistant.models import PendingMemoryExtraction
        from ai_assistant.services.ulr_memory import extract_pending_memory
        from ai_assistant.tasks import dispatch_pending_memory_extractions, extract_memory_turn
        from ai_engine.service import AICallError

        CourseStudentStatus.objects.create(user=self.user, is_course_student=True)
        unavailable = AICallError('Synthetic provider outage', retryable=True, error_category='upstream_5xx')
        valid = {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [{
            'function': {'name': 'submit_memories', 'arguments': json.dumps({'memories': [self.candidate]})},
        }]}}]}
        for second_result in (unavailable, valid):
            with self.subTest(recovered=second_result is valid):
                job = PendingMemoryExtraction.objects.create(source_message=self.question, answer_message=self.answer)
                jobs = PendingMemoryExtraction.objects.filter(pk=job.pk)
                binding = (job.pk, self.question.pk, self.answer.pk)
                with patch('ai_engine.service.AIEngine.call_provider', side_effect=[unavailable, second_result]) as provider:
                    self.assertEqual(extract_pending_memory(*binding), 0)
                    self.assertTrue(jobs.get().provider_retry_used)
                    self.assertEqual(extract_pending_memory(*binding), 0)
                    provider.assert_called_once()
                    self.assertFalse(MemoryExtractionLog.objects.exists())
                    jobs.update(running_until=timezone.now(), dispatch_after=timezone.now())
                    with patch.object(extract_memory_turn, 'apply_async') as enqueue:
                        self.assertEqual(dispatch_pending_memory_extractions.run(), 1)
                    enqueue.assert_called_once_with((self.question.pk, self.answer.pk),
                        {'pending_job_id': job.pk}, retry=False, ignore_result=True)
                    if second_result is unavailable:
                        with self.assertRaises(ValueError):
                            extract_pending_memory(*binding)
                    else:
                        self.assertEqual(extract_pending_memory(*binding), 1)
                    self.assertFalse(jobs.exists())
                    self.assertEqual(extract_pending_memory(*binding), 0)
                    self.assertEqual(provider.call_count, 2)
        log = MemoryExtractionLog.objects.get()
        self.assertEqual((log.source_message_id, log.answer_message_id), (self.question.pk, self.answer.pk))
        self.assertEqual(AgentMemory.objects.count(), 1)

    @override_settings(UNIMIND_DSH_MEMORY_ENABLED=True)
    def test_mem0_auto_extract_is_disabled_when_dsh_memory_enabled(self):
        from ai_assistant.services.memory_service import extract_memories_with_mem0
        with patch('ai_assistant.services.memory_service.USE_MEM0', True), \
             patch('ai_assistant.utils._THREAD_POOL.submit') as submit:
            extract_memories_with_mem0(self.user, self.history)
        submit.assert_not_called()

    @override_settings(UNIMIND_LEARNING_RUNTIME='ulr', UNIMIND_DSH_MEMORY_ENABLED=False,
                       UNIMIND_DSH_GENERATION_ENABLED=False)
    def test_ulr_routes_memory_extraction_and_keeps_semantic_search(self):
        from ai_assistant.models import PendingMemoryExtraction
        from ai_assistant.services.memory_service import extract_memories_async, extract_memories_with_mem0
        from ai_assistant.services.tenant_memory import TenantMemoryManager
        from ai_assistant.services.ulr_memory import extract_pending_memory, publish_memory_extraction
        from ai_assistant.tasks import dispatch_pending_memory_extractions, extract_memory_turn
        from kombu.exceptions import OperationalError

        self.user.institution_id = 1
        with (
            patch('ai_assistant.services.memory_service.USE_MEM0', True),
            patch('ai_assistant.utils._THREAD_POOL.submit') as submit,
            patch('ai_assistant.services.ulr_memory.publish_after_commit') as dispatch,
        ):
            extract_memories_async(self.user, self.history, self.conversation_id,
                                   source_message_id=self.question.pk, answer_message_id=self.answer.pk)
            extract_memories_with_mem0(self.user, self.history)
        job = PendingMemoryExtraction.objects.get(answer_message_id=self.answer.pk)
        submit.assert_not_called()
        dispatch.assert_called_once_with(publish_memory_extraction, job.pk)
        args = (self.question.pk, self.answer.pk)
        delivery = {'pending_job_id': job.pk}
        with patch.object(extract_memory_turn, 'apply_async', side_effect=OperationalError('offline')) as enqueue:
            assert not publish_memory_extraction(job.pk)
            enqueue.assert_called_once_with(args, delivery, retry=False, ignore_result=True)
        with patch.object(extract_memory_turn, 'apply_async') as enqueue:
            assert dispatch_pending_memory_extractions.run() == 1
            enqueue.assert_called_once_with(args, delivery, retry=False, ignore_result=True)
            assert PendingMemoryExtraction.objects.filter(pk=job.pk, running_until__isnull=True).exists()
            assert dispatch_pending_memory_extractions.run() == 0
        with patch('ai_assistant.services.ulr_memory.extract_answer_memory', return_value=1) as extract:
            assert extract_pending_memory(job.pk, *args) == 1
            assert extract_pending_memory(job.pk, *args) == 0
            extract.assert_called_once_with(*args, redelivered=True)
        assert not PendingMemoryExtraction.objects.exists()

        manager = object.__new__(TenantMemoryManager)
        manager.memory, manager.institution_id = Mock(), self.user.institution_id
        manager.add(self.user.pk, '我喜欢看具体例子。')
        manager.memory.add.assert_not_called()
        manager.memory.search.return_value = {'results': [{'memory': '合成学习偏好'}]}
        assert manager.search(self.user.pk, '例子') == [{'memory': '合成学习偏好'}]
        manager.memory.search.assert_called_once_with('例子', filters={'user_id': str(self.user.pk)}, top_k=5)


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
