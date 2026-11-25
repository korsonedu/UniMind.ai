"""Grounded conflicts through real preparation, cached reads and answer entries."""
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from ai_assistant.models import AIChatMessage, AgentMemory, Bot, Conversation, PrismEpisode, PrismMemory
from ai_assistant.services import prism_memory as prism
from ai_assistant.services.prism_gate import clarification
from ai_assistant.services.prism_kernel import induce


@pytest.fixture
def conflict(user, settings, monkeypatch):
    settings.UNIMIND_PRISM_MODE = 'active'
    monkeypatch.setattr('ai_assistant.views._can_use_learning_context', lambda user: True)
    bot = Bot.objects.create(name='小宇', bot_type='planner')
    conversation = Conversation.objects.create(user=user, bot=bot, conversation_id=uuid4())
    q = AIChatMessage.objects.create(user=user, bot=bot, conversation_id=conversation.conversation_id,
        role='user', content='这次用图解来讲代数。')
    memories = []
    for index, layout in enumerate(('diagram', 'worked_example')):
        cases = [{'id':f'{index}-{i}','verified':True,'features':{'topic':topic},'behavior':{'layout':layout}}
            for i, topic in enumerate(('algebra','geometry'))]
        memories.append(PrismMemory.objects.create(key=f'system:gate:{index}',scope='system',fields=['topic'],
            cases=cases,operators=induce(cases,['topic'])))
    identity = {'message_id':q.pk,'bot_id':bot.pk,'conversation_id':str(q.conversation_id)}
    return user, bot, q, identity, memories


def prepare(q, bindings=()):
    with patch('ai_assistant.services.dsh_tasks.run_structured', return_value={
            'features':[{'key':'topic','value':'algebra','evidence':'代数'}],'behavior':[],'bindings':list(bindings)}):
        prism.prepare(q)


def test_current_binding_resolves_conflict_and_changed_question_invalidates_it(conflict):
    user, bot, q, identity, _ = conflict
    prepare(q,[{'key':'layout','value':'diagram','evidence':'这次用图解','source':'question','fact_id':None}])
    assert prism.context(q)['decision']['behavior']['layout']=='diagram'
    assert clarification(user,bot,identity)==''
    q.content='讲一下代数。'
    q.save(update_fields=['content'])
    assert '图解' in clarification(user,bot,identity)
    assert prism.context(q)['decision']['conflicts']['layout']


def test_fact_binding_is_owned_and_invalidated_by_edit_disable_or_delete(conflict):
    user, bot, q, identity, _ = conflict
    q.content='请按个人设置讲代数。';q.save(update_fields=['content'])
    fact=AgentMemory.objects.create(user=user,key='呈现方式',value='图解',source='manual')
    prepare(q,[{'key':'layout','value':'diagram','evidence':'图解','source':'fact','fact_id':fact.pk}])
    assert clarification(user,bot,identity)==''
    fact.value='分步算例';fact.save(update_fields=['value'])
    assert clarification(user,bot,identity)==''
    assert prism.context(q)['decision']['behavior']['layout']=='worked_example'
    fact.value='图解';fact.is_active=False;fact.save(update_fields=['value','is_active'])
    assert clarification(user,bot,identity)
    fact.delete()
    assert clarification(user,bot,identity)


def test_canonical_fact_does_not_depend_on_a_model_repeating_the_binding(conflict):
    user,bot,q,identity,_=conflict
    q.content='继续讲代数。';q.save(update_fields=['content'])
    fact=AgentMemory.objects.create(user=user,key='呈现方式',value='图解',source='dsh')
    prepare(q)
    assert clarification(user,bot,identity)==''
    assert prism.context(q)['decision']['behavior']['layout']=='diagram'
    fact.value='仅代数课用图解';fact.save(update_fields=['value'])
    assert clarification(user,bot,identity)  # Conditional prose is not a global symbolic setting.


def test_unbound_evidence_cannot_choose_a_layout_and_withdrawn_source_clears_gate(conflict, settings):
    user, bot, q, identity, memories = conflict
    prepare(q,[{'key':'layout','value':'diagram','evidence':'不存在的原文','source':'question','fact_id':None}])
    assert clarification(user,bot,identity)
    assert clarification(user,bot,{**identity,'message_id':0})==''
    memories[1].active=False;memories[1].save(update_fields=['active'])
    assert clarification(user,bot,identity)==''
    q.refresh_from_db();assert not q.metadata.get('prism_clarification')
    settings.UNIMIND_PRISM_MODE='off'
    assert clarification(user,bot,identity)==''


def test_legacy_and_sync_gate_before_any_model_or_tool(conflict):
    from ai_assistant.services.chat_dispatch import dispatch_bot_chat, dispatch_bot_chat_sync, clarification_result
    user, bot, q, identity, _ = conflict
    prepare(q)
    profile=SimpleNamespace(executor_class=lambda **kwargs:SimpleNamespace(),restore_state=None,tools_factory=lambda:[])
    with patch('ai_assistant.services.chat_dispatch.get_bot_profile',return_value=profile), \
            patch('ai_assistant.services.chat_dispatch.build_system_prompt',return_value='system'), \
            patch('ai_assistant.services.mutar_variants.get_variant_for_request',return_value=None), \
            patch('ai_engine.tool_permissions.filter_tools',return_value=[]), \
            patch('ai_service.AIService.chat_with_assistant_agent',side_effect=AssertionError('generation must not start')):
        result=dispatch_bot_chat(bot,user,q.content,[],chat_context=identity)
        assert result['tool_executor']._prism_clarification
        assert '哪一种' in result['result']['choices'][0]['message']['content']
        _,tools,executor,*_=dispatch_bot_chat_sync(bot,user,q.content,[],chat_context=identity)
        assert tools==[] and clarification_result(bot,user,executor)['content']


def test_native_gate_persists_and_replays_without_runtime_or_learning(conflict, settings, tmp_path):
    from ai_assistant.services.dsh_xiaoyu import complete_turn
    from users.models import WeeklyAIQuotaConfig
    user, bot, _, _, _ = conflict
    settings.UNIMIND_DSH_STATE_DIR=str(tmp_path)
    settings.UNIMIND_DSH_TITLE_ENABLED=True
    WeeklyAIQuotaConfig.objects.update_or_create(pk=1,defaults={'experience_calls':20,'course_calls':200})
    cid=uuid4()
    body={'message':'讲一下代数。','request_id':str(uuid4()),'conversation_id':str(cid),'bot_id':bot.pk}
    request=SimpleNamespace(user=user,headers={},data=body)
    events=[]
    with patch('ai_assistant.services.dsh_tasks.run_structured',return_value={
            'features':[{'key':'topic','value':'algebra','evidence':'代数'}],'behavior':[]}), \
            patch('ai_assistant.services.dsh_xiaoyu.run_site_action',side_effect=AssertionError('runtime must not start')), \
            patch('ai_assistant.services.dsh_xiaoyu.sync_generate_title',side_effect=AssertionError('no auxiliary model')), \
            patch('ai_assistant.utils._THREAD_POOL.submit') as submit:
        result=complete_turn(request,bot,cid,body['message'],events.append)
        assert result['metadata']['prism_clarification'] and result['metadata']['dsh_cards']==[]
        assert result['session_id'] is None and 'dsh_session_id' not in result['metadata']
        assert result==complete_turn(request,bot,cid,body['message'],events.append)
        submit.assert_not_called()
    assert [event['type'] for event in events]==['user_message']
    assert not PrismEpisode.objects.filter(question__conversation_id=cid).exists()
    # A short reply to the clarification resumes the same conversation.
    followup={**body,'message':'图解','request_id':str(uuid4())}
    def runtime(owner,action,**kwargs):
        import json
        from ai_assistant.services.dsh_xiaoyu import task_context
        rendered=task_context(owner,kwargs['chat_context'],followup['message'])
        context=json.loads(rendered[rendered.index('{'):])
        assert context['prism']['decision']['behavior']['layout']=='diagram'
        assert any('哪一种' in row['content'] for row in context['history'])
        assert kwargs['session_id'] is None
        return {'finish_reason':'completed','content':'按图解继续讲代数。',
            'session':{'id':'b'*32,'messages':[{'role':'assistant','cards':[]}]}}
    with patch('ai_assistant.services.dsh_tasks.run_structured',return_value={
            'features':[],'behavior':[],'bindings':[{'key':'layout','value':'diagram','evidence':'图解','source':'question','fact_id':None}]}), \
            patch('ai_assistant.services.dsh_xiaoyu.run_site_action',side_effect=runtime) as resume, \
            patch('ai_assistant.utils._THREAD_POOL.submit'):
        continued=complete_turn(SimpleNamespace(user=user,headers={},data=followup),bot,cid,followup['message'],lambda event:None)
        assert not continued['metadata'].get('prism_clarification')
        assert continued['session_id']=='b'*32
        resume.assert_called_once()


@pytest.mark.django_db(transaction=True)
def test_sse_gate_emits_no_teaching_content_before_clarification(conflict, auth_client, settings):
    import asyncio
    import json
    from users.models import WeeklyAIQuotaConfig
    _,bot,_,_,_=conflict
    settings.UNIMIND_DSH_XIAOYU_ENABLED=False
    settings.UNIMIND_LEARNING_EXPERIMENTS_PROTOTYPE=False
    WeeklyAIQuotaConfig.objects.update_or_create(pk=1,defaults={'experience_calls':20,'course_calls':200})
    body={'message':'讲一下代数。','bot_id':bot.pk,'conversation_id':str(uuid4()),'request_id':str(uuid4())}
    async def collect(response):
        frames=[frame async for frame in response.streaming_content] if response.is_async else list(response.streaming_content)
        return b''.join(frames).decode()
    with patch('ai_assistant.services.dsh_tasks.run_structured',return_value={
            'features':[{'key':'topic','value':'algebra','evidence':'代数'}],'behavior':[]}) as observer, \
            patch('ai_engine.service.AIEngine.call_ai_with_streaming_tools',side_effect=AssertionError('no answer model')), \
            patch('ai_engine.service.AIEngine.call_ai',side_effect=AssertionError('no intent model')) as direct_model, \
            patch('ai_assistant.services.title_generator.sync_generate_title',side_effect=AssertionError('no title model')), \
            patch('ai_assistant.services.trajectory_recorder.record_trajectory',side_effect=AssertionError('no optimization trajectory')):
        response=auth_client.post('/api/ai/chat/stream/',body,format='json')
        assert response.status_code==200
        frames=asyncio.run(collect(response))
        events=[json.loads(line[6:]) for line in frames.splitlines() if line.startswith('data: ')]
        done=next(event for event in events if event.get('done'))
        assert not done.get('is_error') and done['metadata']['prism_clarification']
        assert '哪一种' in done['full_content']
        assert all(event.get('type') not in ('step','text_delta','message') for event in events)
        assert not done['metadata'].get('visual') and not done['metadata'].get('all_visuals')
        replay=auth_client.post('/api/ai/chat/stream/',body,format='json')
        replay_events=[json.loads(line[6:]) for line in asyncio.run(collect(replay)).splitlines() if line.startswith('data: ')]
        assert next(event for event in replay_events if event.get('done'))==done
        observer.assert_called_once()
        direct_model.assert_not_called()
