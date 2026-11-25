"""Shared observer and reference-preserving public encoding smoke checks."""
import copy
import json
from unittest.mock import patch
from uuid import uuid4
import pytest
from rest_framework.exceptions import ValidationError
from ai_assistant.models import AIChatMessage, AgentMemory, Bot, Conversation, MemoryExtractionLog, PrismEpisode, PrismMemory, PrismProposal
from ai_assistant.services import prism_memory as prism
from ai_assistant.services.memory_service import extract_memories_async
from ai_assistant.services.prism_kernel import induce
from ai_assistant.services.prism_mapping import memory_groups, review_mapping


@pytest.fixture
def joint(user, settings, monkeypatch):
    settings.UNIMIND_PRISM_MODE = 'active'
    monkeypatch.setattr('ai_assistant.views._can_use_learning_context', lambda user: True)
    bot = Bot.objects.create(name='小宇', bot_type='planner')
    convo = Conversation.objects.create(user=user, bot=bot, conversation_id=uuid4())
    q = AIChatMessage.objects.create(user=user, bot=bot, conversation_id=convo.conversation_id, role='user', content='我长期习惯先看例子。')
    a = AIChatMessage.objects.create(user=user, bot=bot, conversation_id=q.conversation_id, role='assistant', content='先看例子。')
    fact = {'memory_type': 'preference', 'key': '讲解顺序', 'value': '先看例子', 'confidence': .9, 'evidence': '我长期习惯先看例子', 'temporal_scope': 'enduring', 'existing_id': None}
    return user, q, a, fact


def test_joint_completion_reuses_features_and_owns_the_fact_job(joint):
    user, q, a, fact = joint
    before = {'features': [{'key': 'intent', 'value': 'learn', 'evidence': '例子'}], 'behavior': []}
    after = {'behavior': [{'key': 'style', 'value': 'example', 'evidence': '例子'}], 'memories': [fact]}
    queue = []
    with patch('ai_assistant.services.dsh_tasks.run_structured', side_effect=[before, after]) as model, patch('django.db.connections.close_all'), \
            patch('ai_assistant.utils._THREAD_POOL.submit', side_effect=lambda fn, *args: queue.append((fn, args))):
        prism.prepare(q)
        prism.schedule(q, a)
        prism.schedule(q, a)
        extract_memories_async(user, [{'role': 'user', 'content': q.content}], str(q.conversation_id))
        assert len(queue) == 1
        queue[0][0](*queue[0][1])
        assert [call.args[0] for call in model.call_args_list] == ['assistant.prism_observe', 'assistant.prism_complete']
        assert json.loads(model.call_args.args[1])['prepared_features'] == {'intent': 'learn'}
        assert model.call_args.kwargs['reuse_prepared']
        assert 'binding_facts' not in json.loads(model.call_args.args[1])
        prism.observe_completion(q.pk, a.pk)
        extract_memories_async(user, [{'role': 'user', 'content': q.content}], str(q.conversation_id))
        assert model.call_count == 2 and len(queue) == 1
    obs = PrismEpisode.objects.get(question=q).observation
    assert obs['features'] == {'intent': 'learn'} and obs['reused_features'] and obs['facts_saved'] == 1
    assert AgentMemory.objects.get(user=user).value == fact['value']
    assert MemoryExtractionLog.objects.get(user=user).saved_count == 1


def test_joint_completion_keeps_the_preparation_write_barrier(joint):
    user, q, a, fact = joint
    old = AgentMemory.objects.create(user=user, key=fact['key'], value='旧偏好')
    queue = []
    with patch('ai_assistant.services.dsh_tasks.run_structured', side_effect=[{'features': [], 'behavior': []},
            {'features': [], 'behavior': [], 'memories': [fact]}]), patch('django.db.connections.close_all'), \
            patch('ai_assistant.utils._THREAD_POOL.submit', side_effect=lambda fn, *args: queue.append((fn, args))):
        prism.prepare(q)
        old.delete()
        prism.schedule(q, a)
        queue[0][0](*queue[0][1])
    assert not AgentMemory.objects.filter(user=user).exists()
    assert PrismEpisode.objects.get(question=q).observation['facts_saved'] == 0


def test_joint_completion_reextracts_when_prepared_input_changes(joint):
    _, q, a, _ = joint
    queue = []
    with patch('ai_assistant.services.dsh_tasks.run_structured', side_effect=[{'features': [], 'behavior': []},
            {'features': [{'key': 'intent', 'value': 'practice', 'evidence': '新条件'}], 'behavior': [], 'memories': []}]) as model, \
            patch('django.db.connections.close_all'), patch('ai_assistant.utils._THREAD_POOL.submit', side_effect=lambda fn, *args: queue.append((fn, args))):
        prism.prepare(q)
        q.content += '新条件'
        q.save()
        prism.schedule(q, a)
        queue[0][0](*queue[0][1])
        assert json.loads(model.call_args.args[1])['prepared_features'] is None
        assert not model.call_args.kwargs['reuse_prepared']
    assert PrismEpisode.objects.get(question=q).observation['features'] == {'intent': 'practice'}


def test_joint_completion_respects_native_fact_switch_and_notes(joint, settings):
    user, q, a, fact = joint
    settings.UNIMIND_DSH_MEMORY_ENABLED = False
    a.metadata = {'engine': 'dsh'}
    a.save()
    queue = []
    with patch('ai_assistant.services.dsh_tasks.run_structured', return_value={'features': [], 'behavior': [], 'memories': [fact]}), \
            patch('django.db.connections.close_all'), patch('ai_assistant.utils._THREAD_POOL.submit', side_effect=lambda fn, *args: queue.append((fn, args))):
        prism.schedule(q, a)
        queue[0][0](*queue[0][1])
        assert not AgentMemory.objects.exists() and not MemoryExtractionLog.objects.exists()
        q.metadata = {'notes_context_used': True}
        q.save()
        queue.clear()
        extract_memories_async(user, [{'role': 'user', 'content': q.content}], str(q.conversation_id))
        assert queue == []


def public_memory(key, field, values):
    cases = [{'id': f'{key}-{i}', 'verified': True, 'features': {field: value}, 'behavior': {'depth': ['full', 'hint'][i]}} for i, value in enumerate(values)]
    return PrismMemory.objects.create(key=key, scope='system', fields=[field], cases=cases, operators=induce(cases, [field]))


@pytest.fixture
def mapping(joint, monkeypatch):
    user, q, _, _ = joint
    monkeypatch.setattr('users.permissions.is_platform_admin', lambda actor: actor.pk == user.pk)
    source = public_memory('system:alias', 'answer_disclosure_permission', ['可以直接回答', '只给提示'])
    target = public_memory('system:canonical', 'answer_disclosure', ['allowed', 'withheld'])
    def cases(split):
        return [{'id': f'{split}-{i}', 'group': split, 'verified': True, 'features': {'source_value': before, 'target_value': after},
            'behavior': {'depth': ['full', 'hint'][i]}} for i, (before, after) in enumerate(zip(['可以直接回答', '只给提示'], ['allowed', 'withheld']))]
    spec = {'public_system_cases': True, 'source_revision': 1, 'target_revision': 1, **{s: cases(s) for s in ('training', 'validation', 'test')}}
    return user, q, source, target, spec


def test_mapping_compiles_aliases_and_invalidates_cached_plan(mapping):
    user, q, source, target, spec = mapping
    proposal = review_mapping(source.pk, target.pk, user, spec)
    assert proposal.review['bidirectional_cases'] == 4
    assert review_mapping(source.pk, target.pk, user, spec).pk == proposal.pk
    with patch.object(prism, 'extract', return_value={'features': {source.fields[0]: '只给提示'}}):
        prism.prepare(q)
    packet = prism.context(q)
    assert [r['key'] for r in packet['memories']] == [target.key]
    assert packet['decision']['behavior'] == {'depth': 'hint'} and packet['memories'][0]['alias_count'] == 1
    from ai_assistant.services.prism_mapping import mapped_frame
    projected, conflict = mapped_frame(target, [proposal], {source.fields[0]: 'withheld'})
    assert not conflict and projected[target.fields[0]] == 'withheld'
    assert mapped_frame(target, [proposal], projected) == (projected, False)
    target.revision += 1
    target.save()
    assert prism.context(q)['decision']['behavior'] == {}
    assert {row.key for row, _ in memory_groups(user)} == {source.key, target.key}


def test_mapping_rejects_wrong_bridges_and_conflicting_views(mapping):
    user, q, source, target, spec = mapping
    for change in ('behavior', 'values', 'condition', 'revision'):
        wrong = copy.deepcopy(spec)
        if change == 'behavior': wrong['test'][0]['behavior']['depth'] = 'hint'
        if change == 'values': wrong['validation'][0]['features']['target_value'] = 'withheld'
        if change == 'condition': wrong['training'][0]['features']['course'] = 'extra'
        if change == 'revision': wrong['source_revision'] = 2
        with pytest.raises(ValidationError): review_mapping(source.pk, target.pk, user, wrong)
    assert not PrismProposal.objects.filter(kind='mapping').exists()
    review_mapping(source.pk, target.pk, user, spec)
    for frame in ({source.fields[0]: '只给提示', target.fields[0]: 'allowed'}, {source.fields[0]: '未知编码'}):
        packet = prism.packet_for(q, frame)
        assert packet['memories'] == [] and packet['relation_conflicts'] == [target.key]
    source.definitions = {source.fields[0]: 'changed without revision'}
    source.save()
    assert all(not mappings for _, mappings in memory_groups(user))


def test_mapping_collapses_searches_and_keeps_private_memory_independent(mapping):
    user, q, source, target, spec = mapping
    review_mapping(source.pk, target.pk, user, spec)
    for i in range(10):
        alias = public_memory(f'system:alias-{i}', f'alias_{i}', ['可以直接回答', '只给提示'])
        review_mapping(alias.pk, target.pk, user, spec)
    with patch('ai_assistant.services.prism_memory.transfer', wraps=prism.transfer) as search:
        packet = prism.packet_for(q, {'alias_9': '只给提示'})
        assert search.call_count == 1 and packet['memories'][0]['alias_count'] == 11
    own = PrismMemory.objects.create(owner=user, scope='student', key='own', fields=source.fields,
        cases=[{**row, 'behavior': {'depth': 'personal'}} for row in source.cases])
    own.operators = induce(own.cases, own.fields)
    own.save()
    assert prism.packet_for(q, {source.fields[0]: '只给提示'})['decision']['behavior'] == {'depth': 'personal'}
    with pytest.raises(ValidationError): review_mapping(own.pk, target.pk, user, spec)


def test_joint_facts_bind_existing_identity_and_skip_turn_only_candidates(joint):
    user, q, a, fact = joint
    existing = AgentMemory.objects.create(user=user, key='讲解顺序', value='用户设置', source='manual')
    q.content += '我现在要独立尝试。'
    q.save()
    queue = []
    rows = [{**fact, 'key': '另造同义名称', 'existing_id': existing.pk},
            {**fact, 'key': '独立偏好', 'evidence': '我现在要独立尝试', 'temporal_scope': 'turn_only'}]
    with patch('ai_assistant.services.dsh_tasks.run_structured', side_effect=[{'features': [], 'behavior': []},
            {'features': [], 'behavior': [], 'memories': rows}]), patch('django.db.connections.close_all'), \
            patch('ai_assistant.utils._THREAD_POOL.submit', side_effect=lambda fn, *args: queue.append((fn, args))):
        prism.prepare(q)
        prism.schedule(q, a)
        queue[0][0](*queue[0][1])
    assert list(AgentMemory.objects.filter(user=user).values_list('key', 'value')) == [('讲解顺序', '用户设置')]


def test_episode_view_only_compacts_text_already_in_the_actual_history():
    packet = {'episodes': [{'question_id': 1, 'answer_id': 2, 'question': '旧问题', 'answer': '旧回答', 'status': 'observed_not_verified'}]}
    history = [{'role': 'user', 'content': '旧问题'}, {'role': 'assistant', 'content': '旧回答'}]
    compact = prism.episode_view(packet, history)
    assert compact['episodes'] == [{'question_id': 1, 'answer_id': 2, 'status': 'observed_not_verified', 'already_in_history': True}]
    assert 'answer' in packet['episodes'][0]
    assert prism.episode_view(packet, history[:1]) == packet
    assert prism.episode_view(packet, [{'role': 'user', 'content': '旧问题旧回答'}]) == packet


def test_mapping_accepts_alternate_codebooks_and_rejects_ambiguous_shared_codes(mapping):
    user, q, source, target, spec = mapping
    review_mapping(source.pk, target.pk, user, spec)
    other = public_memory('system:alternate', source.fields[0], ['另外讲解', '另外独立'])
    bridge = copy.deepcopy(spec)
    for split in ('training', 'validation', 'test'):
        for i, case in enumerate(bridge[split]):
            case['features']['source_value'] = ['另外讲解', '另外独立'][i]
    review_mapping(other.pk, target.pk, user, bridge)
    assert prism.packet_for(q, {source.fields[0]: '另外独立'})['decision']['behavior'] == {'depth': 'hint'}
    reversed_memory = public_memory('system:opposite', source.fields[0], ['只给提示', '可以直接回答'])
    reversed_bridge = copy.deepcopy(spec)
    for split in ('training', 'validation', 'test'):
        for i, case in enumerate(reversed_bridge[split]):
            case['features']['source_value'] = ['只给提示', '可以直接回答'][i]
    review_mapping(reversed_memory.pk, target.pk, user, reversed_bridge)
    assert prism.packet_for(q, {source.fields[0]: '只给提示'})['decision']['behavior'] == {}
