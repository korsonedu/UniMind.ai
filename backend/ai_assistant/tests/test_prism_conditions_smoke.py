"""Conditional fact certificates through preparation and live source checks."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from ai_assistant.models import AgentMemory
from ai_assistant.services import prism_memory as prism
from ai_assistant.services.prism_gate import bindings_for
from .test_prism_gate_smoke import conflict


def test_conditional_fact_is_checked_again_after_preparation(conflict):
    user,_,q,_,memories=conflict
    fact=AgentMemory.objects.create(user=user,key='讲解偏好',value='只在代数课用图解',source='dsh')
    binding={'key':'layout','value':'diagram','evidence':'图解','source':'fact','fact_id':fact.pk,
        'fact_scope':'conditional','conditions':[{'key':'topic','value':'algebra','operator':'eq','evidence':'代数课'}]}
    with patch('ai_assistant.services.dsh_tasks.run_structured',return_value={
            'features':[{'key':'topic','value':'algebra','evidence':'代数'}],'behavior':[],'bindings':[binding]}):
        prism.prepare(q)
    packet=prism.context(q)
    assert packet['decision']['behavior']['layout']=='diagram'
    assert packet['decision']['sources']['layout'][0]['conditions'][0]['schema_digest']
    # A different frame cannot reuse the certificate, including a missing frame.
    for frame in ({'topic':'geometry'},{}):
        rejected=prism.packet_for(q,frame,packet['bindings'])
        assert not rejected.get('bindings')
    for memory in memories:
        memory.definitions={'topic':'changed meaning'};memory.save(update_fields=['definitions'])
    assert prism.context(q)['decision']['conflicts']['layout']


def test_condition_certificate_rejects_unknown_exclusion_and_stale_sources():
    q=SimpleNamespace(content='当前代数任务',metadata={})
    fact={'id':1,'key':'讲解偏好','value':'除几何课外用图解','source':'dsh','memory_type':'preference'}
    row={'key':'layout','value':'diagram','evidence':'图解','source':'fact','fact_id':1,'fact_scope':'conditional',
        'conditions':[{'key':'topic','value':'geometry','operator':'ne','evidence':'几何课'}]}
    domains={'layout':['diagram']};schema={'topic':{'values':{'algebra','geometry'},'definitions':{'学科'}}}
    def bind(rows,frame,facts=None,codebook=None):
        return bindings_for(q,rows,domains,[fact] if facts is None else facts,frame,schema if codebook is None else codebook)
    valid=bind([row],{'topic':'algebra'});assert valid
    assert not bind([row],{}) and not bind([row],{'topic':'geometry'})
    unknown=deepcopy(row);unknown['conditions'][0]['value']='made_up'
    assert not bind([unknown],{'topic':'algebra'})
    assert not bind([row],{'topic':'algebra'},codebook={'topic':{'values':{'algebra','geometry'},'definitions':{'one','two'}}})
    assert not bind([valid[0]],{'topic':'algebra'},facts=[])
    q.content='已编辑的几何任务'
    assert not bind(valid,{'topic':'algebra'})
    assert not bind([{k:v for k,v in row.items() if k not in ('fact_scope','conditions')}],{'topic':'algebra'})


def test_alternatives_and_unknown_values_are_checked_without_a_model():
    q=SimpleNamespace(content='请讲几何。',metadata={})
    fact={'id':1,'memory_type':'preference','key':'偏好','value':'仅代数或几何用图解','source':'dsh'}
    domains={'layout':['diagram','worked_example']}
    schema={'topic':{'values':{'algebra','geometry','physics'},'definitions':{'学科'}}}
    row={'key':'layout','value':'diagram','evidence':'图解','source':'fact','fact_id':1,'fact_scope':'conditional','condition_mode':'any',
        'conditions':[{'key':'topic','value':v,'operator':'eq','evidence':e} for v,e in [('algebra','代数'),('geometry','几何')]]}
    assert bindings_for(q,[row],domains,[fact],{'topic':'geometry'},schema)
    for frame in ({},{'topic':'physics'}):assert not bindings_for(q,[row],domains,[fact],frame,schema)
    row['condition_mode']='all'
    assert not bindings_for(q,[row],domains,[fact],{'topic':'geometry'},schema)
    row['conditions']=[{**row['conditions'][0],'operator':'ne'}]
    assert not bindings_for(q,[row],domains,[fact],{'topic':'unknown_code'},schema)


def test_current_scoped_correction_uses_current_evidence_and_outranks_old_facts():
    from ai_assistant.services.prism_gate import bind_decision
    q=SimpleNamespace(content='我改了，今后只在物理课用图解。',metadata={})
    row={'key':'layout','value':'diagram','evidence':'今后只在物理课用图解','source':'question','fact_id':None,
        'fact_scope':'conditional','conditions':[{'key':'topic','value':'physics','evidence':'物理课','operator':'eq'}]}
    schema={'topic':{'values':{'physics','algebra'},'definitions':{'学科'}}}
    good=bindings_for(q,[row],{'layout':['diagram']},[],{'topic':'physics'},schema)
    assert good and good[0]['rank']==0 and good[0]['conditions']
    decision={'behavior':{'layout':'worked_example'},'sources':{'layout':[]},'conflicts':{}}
    assert bind_decision(decision,good)['behavior']['layout']=='diagram'
    shared=deepcopy(row);shared['scope_evidence']='今后只在物理课用图解'
    shared['conditions'][0].pop('evidence')
    assert bindings_for(q,[shared],{'layout':['diagram']},[],{'topic':'physics'},schema)
    shared['scope_evidence']='用户未说过的范围'
    assert not bindings_for(q,[shared],{'layout':['diagram']},[],{'topic':'physics'},schema)
    for frame in ({},{'topic':'algebra'}):assert not bindings_for(q,[row],{'layout':['diagram']},[],frame,schema)
    q.content='现在讲代数。'
    assert not bindings_for(q,good,{'layout':['diagram']},[],{'topic':'physics'},schema)
