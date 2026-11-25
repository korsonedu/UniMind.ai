"""Synthetic cutover smoke: no model, external memory store or production data."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from ai_assistant.models import (AIChatMessage, AgentMemory, Bot, Conversation, ConversationProject,
    LearningStrategy, LearningStrategyUse, PrismApplication, PrismEpisode, ProjectLearningEvent)
from ai_assistant.services import memory_core as core, prism_memory as prism


@pytest.fixture
def turn(user, settings, monkeypatch):
    settings.UNIMIND_PRISM_MODE = 'active'
    monkeypatch.setattr('ai_assistant.views._can_use_learning_context', lambda user: True)
    bot = Bot.objects.create(name='小宇', bot_type='planner')
    question = AIChatMessage.objects.create(user=user, bot=bot, role='user', content='时间单位怎么换算？')
    return user, bot, question


def test_cutover_filters_legacy_instruction_copies_and_preserves_rollback(turn, settings):
    from ai_assistant.services.experience_applicator import apply_memory_experiences
    from ai_assistant.services.tool_executor import _inject_kp_chain_experiences
    user, _, _ = turn
    legacy = AgentMemory.objects.create(user=user, key='experience:1', value='旧策略', source='auto')
    manual = AgentMemory.objects.create(user=user, key='experience:2', value='用户修订', source='manual')
    assert [row['id'] for row in core.fact_snapshot(user)['items']] == [manual.pk]
    assert apply_memory_experiences(user, [SimpleNamespace(id=3, dimension='memory', title='旧策略')]) == 0
    with patch('ai_assistant.services.experience_applicator.get_applicable_experiences', side_effect=AssertionError('old router')):
        assert _inject_kp_chain_experiences([1], user) == []
    for mode in ('off', 'shadow'):
        settings.UNIMIND_PRISM_MODE = mode
        assert {row['id'] for row in core.fact_snapshot(user)['items']} == {legacy.pk, manual.pk}
    legacy.is_active = False
    legacy.save()
    # Legacy fallback must not recreate a disabled copy and hit the unique constraint.
    assert apply_memory_experiences(user, [SimpleNamespace(id=1, dimension='memory')]) == 0


def test_cutover_stops_semantic_jobs_before_store_or_model_work(turn, settings):
    from ai_assistant import tasks
    from ai_assistant.services import memory_service
    from ai_assistant.services.tenant_memory import TenantMemoryManager
    settings.UNIMIND_DSH_GENERATION_ENABLED = settings.UNIMIND_DSH_MEMORY_ENABLED = False
    account = SimpleNamespace(id=1, institution_id=42)
    manager = object.__new__(TenantMemoryManager)
    manager.memory, manager.institution_id = Mock(), 42
    with patch.object(tasks, 'USE_MEM0', True), patch.object(memory_service, 'USE_MEM0', True), \
         patch.object(tasks, '_analyze_user', side_effect=AssertionError('legacy analysis')), \
         patch('ai_assistant.services.tenant_memory.TenantMemoryManager.__init__', side_effect=AssertionError('legacy store')), \
         patch('ai_assistant.utils._THREAD_POOL.submit') as submit, \
         patch.object(memory_service, 'get_memories_for_injection', return_value='事实'):
        tasks.reflect_user_learning()
        tasks.reflect_teacher_patterns()
        tasks._store_insights(account, [{'type': 'test', 'text': '不写入'}])
        memory_service.extract_memories_with_mem0(account, [{'role': 'user', 'content': '合成'}])
        assert memory_service.build_memory_context(account, '合成') == ('事实', '')
        manager.add(1, '不写入')
        submit.assert_not_called()
        manager.memory.add.assert_not_called()
    settings.UNIMIND_PRISM_MODE = 'shadow'
    assert core.semantic_writes_allowed()
    settings.UNIMIND_DSH_MEMORY_ENABLED = True
    assert not core.semantic_writes_allowed()


def test_legacy_dispatchers_share_the_same_prism_application(turn):
    from ai_assistant.services.chat_dispatch import dispatch_bot_chat, dispatch_bot_chat_sync
    user, bot, question = turn
    identity = {'message_id': question.pk, 'bot_id': bot.pk, 'conversation_id': str(question.conversation_id)}
    profile = SimpleNamespace(executor_class=lambda **kwargs: Mock(), restore_state=None, tools_factory=lambda: [])
    with patch.object(prism, 'extract', return_value={'features': {}}) as extract, \
         patch('ai_assistant.services.chat_dispatch.get_bot_profile', return_value=profile), \
         patch('ai_assistant.services.chat_dispatch.build_system_prompt', side_effect=lambda b, u, s, m, i, a: m), \
         patch('ai_assistant.services.mutar_variants.get_variant_for_request', return_value=None), \
         patch('ai_engine.tool_permissions.filter_tools', return_value=[]), \
         patch('ai_assistant.services.experience_applicator.get_applicable_experiences', side_effect=AssertionError('old router')), \
         patch('ai_service.AIService.chat_with_assistant_agent', return_value={}) as model:
        messages, *_ = dispatch_bot_chat_sync(bot, user, question.content, [], chat_context=identity)
        assert 'prism.sdtm.v1' in messages[0]['content']
        dispatch_bot_chat(bot, user, question.content, [], chat_context=identity)
        assert 'prism.sdtm.v1' in model.call_args.kwargs['memory_context']
        extract.assert_called_once()
    assert PrismApplication.objects.filter(question=question).count() == 1
    assert prism.prepare_chat(user, bot, {**identity, 'message_id': 999999}) == {}


def test_native_and_legacy_prompts_share_the_behavior_policy_only_when_active(turn, settings):
    from ai_assistant.services.dsh_service import build_context
    from ai_assistant.services.chat_service import AssistantChatService
    user, bot, _ = turn
    assert prism.ANSWER_POLICY in build_context(user, '讲解')['system_prompt']
    assert prism.ANSWER_POLICY in AssistantChatService._build_agent_system_prompt(bot)
    settings.UNIMIND_PRISM_MODE = 'off'
    assert prism.ANSWER_POLICY not in build_context(user, '讲解')['system_prompt']
    assert prism.ANSWER_POLICY not in AssistantChatService._build_agent_system_prompt(bot)


def test_both_answer_entries_project_the_validated_packet_without_changing_it(turn):
    import copy
    from ai_assistant.services.chat_dispatch import _memory_for_chat
    from ai_assistant.services.dsh_xiaoyu import task_context
    user, bot, question = turn
    packet = {'protocol': 'prism.sdtm.v1', 'features': {'intent': 'learn'},
        'decision': {'behavior': {}, 'sources': {}, 'conflicts': {'layout': ['diagram', 'worked_example']}},
        'relation_conflicts': ['system:alias'], 'memories': [{'raw': 'reference'}],
        'episodes': [{'answer': 'unverified answer'}], 'methods': [{'method': 'unverified method'}]}
    original = copy.deepcopy(packet)
    with patch.object(prism, 'prepare_chat', return_value=packet), patch.object(prism, 'context', return_value=packet), \
            patch('ai_assistant.services.dsh_xiaoyu.task_message', return_value=question), \
            patch('ai_assistant.views._get_chat_history', return_value=[]), \
            patch('ai_assistant.services.dsh_xiaoyu.prepare_note_context', return_value=('', {})):
        legacy = _memory_for_chat(user, bot, {}, '')
        native = task_context(user, {}, question.content)
    for rendered in (legacy, native):
        assert 'unverified answer' not in rendered and 'unverified method' not in rendered
        assert 'system:alias' in rendered and 'worked_example' in rendered
    assert packet == original


def test_method_version_and_completion_use_the_existing_sidecar_evidence(turn):
    from ai_assistant.services.project_learning import completed_learning_turn
    from ai_assistant.services.teaching_sidecar import freeze_turn, record_strategy_use, current_bundle
    from ai_assistant.models import TeachingMechanismVersion
    user, bot, question = turn
    project = ConversationProject.objects.create(user=user, name='合成项目')
    Conversation.objects.create(user=user, bot=bot, project=project, conversation_id=question.conversation_id)
    source = AIChatMessage.objects.create(user=user, bot=bot, role='user', content='先统一时间单位')
    event = ProjectLearningEvent.objects.create(project=project, message=source, kind='progress', content={'strategy': '先画时间线'})
    method = LearningStrategy.objects.create(user=user, source_event=event, topic='时间')
    freeze_turn(project, question, {'synthetic': True})
    with patch.object(prism, 'extract', return_value={'features': {}}):
        prism.prepare(question)
    use = LearningStrategyUse.objects.create(strategy=method, project=project, message=question, reason='条件相近')
    record_strategy_use(use, created=True)
    use.refresh_from_db()
    assert prism.context(question)['methods'][0]['version'] == use.method_version.digest
    assert use.decision['prism']['methods'][0]['version'] == use.method_version.digest
    assert use.decision['prism']['status'] == 'retrieved_not_usage_proof'
    mechanism = TeachingMechanismVersion.objects.get(pk=current_bundle()['M']['id'])
    assert mechanism.content['role'] == 'sdtm_active'
    assert 'ai_assistant/services/prism_kernel.py' in mechanism.content['sources']
    reply = AIChatMessage.objects.create(user=user, bot=bot, conversation_id=question.conversation_id,
        role='assistant', content='合成回答')
    with patch('ai_assistant.utils._THREAD_POOL.submit') as submit:
        core.record_completed_reply(reply)
        submit.assert_not_called()
        reply.metadata = {'learning_turn': completed_learning_turn(question.pk)}
        reply.save()
        core.record_completed_reply(reply)
        submit.assert_called_once()
    use.refresh_from_db()
    assert use.exposure['status'] == 'reply_completed'
    assert PrismEpisode.objects.get(question=question).observation['status'] == 'pending'
