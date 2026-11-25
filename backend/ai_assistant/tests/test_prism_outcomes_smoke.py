"""Autonomous refinement from formal results; no user corrections or model calls."""
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone

from ai_assistant.models import (AIChatMessage, Bot, Conversation, ConversationProject,
    LearningKnowledgeMap, LearningKnowledgeVersion, PrismMemory, ProjectLearning)
from ai_assistant.services.prism_kernel import transfer
from ai_assistant.services.prism_outcomes import context, learn
from ai_assistant.services.learning_tasks import create_task, sync_task_result
from quizzes.models import Question, QuizExam, ExamQuestionResult
from quizzes.services.practice_results import question_snapshot


def stream():
    start=datetime(2026,11,17,tzinfo=dt_timezone.utc)
    return [{'id':str(i),'verified':True,'features':{'node':'n','mode':mode,'stage':'s'},
        'behavior':{'outcome':'success' if mode=='apply' else 'failure'},'exam_id':i,
        'task_at':(start+timedelta(minutes=i*2)).isoformat(),
        'at':(start+timedelta(minutes=i*2+1)).isoformat()} for i,mode in enumerate(['apply','transfer']*3)]


def test_future_results_select_a_distinction_and_counterexamples_cause_abstention():
    cases=stream();state=learn(cases)
    assert state['fields']==['node','mode'] and state['revisions'][0]['accepted']
    assert state['revisions'][0]['training_ids']==['0','1']
    assert state['revisions'][0]['future_ids']==['2','3']
    assert all(row['predicted']==row['observed'] for row in state['predictions'][4:])
    assert all(transfer(cases[:i],['node'],cases[i]['features'])['status']=='ambiguous' for i in (4,5))
    counter={**cases[4],'id':'counter','exam_id':7,'behavior':{'outcome':'failure'},
        'task_at':'2026-11-17T00:14:00+00:00','at':'2026-11-17T00:15:00+00:00'}
    changed=learn([*cases,counter])
    assert transfer([*cases,counter],changed['fields'],counter['features'])['status']=='ambiguous'
    # Tasks prepared before the hypothesis was frozen cannot certify it.
    prepared=[{**row,'task_at':cases[0]['task_at']} for row in cases]
    assert not learn(prepared)['revisions']
    # Delayed processing cannot pretend a hypothesis existed at grading time.
    assert not learn(cases,now=cases[-1]['at'])['revisions']


@pytest.fixture
def formal(user,settings,monkeypatch):
    settings.UNIMIND_CONTENT_INSTITUTION_ID='global';settings.UNIMIND_PRISM_MODE='active'
    monkeypatch.setattr('ai_assistant.services.learning_tasks.has_learning_feature',lambda *args:True)
    monkeypatch.setattr('ai_assistant.services.learning_task_evidence.has_learning_feature',lambda *args:True)
    project=ConversationProject.objects.create(user=user,name='synthetic-outcome-learning')
    mapping=LearningKnowledgeMap.objects.create(user=user,title='函数')
    version=LearningKnowledgeVersion.objects.create(knowledge_map=mapping,revision=1,snapshot={'nodes':[{'id':'n'}]})
    ProjectLearning.objects.create(project=project,planning_enabled=True,status='active',current_stage='s',
        plan={'knowledge_path':{'version_id':version.pk},'stages':[{'id':'s','knowledge_nodes':['n']}]})
    bot=Bot.objects.create(name='小宇',bot_type='planner');cid=uuid4()
    Conversation.objects.create(user=user,bot=bot,project=project,conversation_id=cid)
    question=AIChatMessage.objects.create(user=user,bot=bot,conversation_id=cid,role='user',content='接下来应该检查什么？')
    def record(index,mode,success=True,assistance='independent',existing=None):
        item=existing or Question.objects.create(text=f'合成独立任务 {index} 的结果是哪项？',options=['1','2'],correct_answer='A')
        task=create_task(project,{'version_id':version.pk,'node_id':'n','stage_id':'s','title':'求值','instructions':'独立计算',
            'question_ids':[item.pk],'mode':mode})
        exam=QuizExam.objects.create(user=user,status='completed',total_questions=1)
        task.exam=exam;task.assistance=assistance;task.save()
        result=ExamQuestionResult.objects.create(exam=exam,question=item,position=1,user_answer='A' if success else 'B',
            score=10 if success else 0,max_score=10,status='graded',is_correct=success,
            question_snapshot=question_snapshot(item),graded_at=timezone.now())
        sync_task_result(result)
        return result
    return user,question,record,version


def test_actual_grading_sync_learns_and_injects_private_forecasts(formal,monkeypatch):
    user,question,record,_=formal
    results=[record(i,mode,mode=='apply') for i,mode in enumerate(['apply','transfer']*3)]
    memory=PrismMemory.objects.get(owner=user)
    assert memory.fields==['node','mode']
    assert memory.provenance['state']['revisions'][0]['accepted']
    payload=context(question)
    assert {r['mode']:r['predicted_outcome'] for r in payload['forecasts']}=={'apply':'success','transfer':'failure'}
    revision=memory.revision;sync_task_result(results[-1]);memory.refresh_from_db()
    assert memory.revision==revision
    # Predictions are never teaching behaviors or clarification choices.
    from ai_assistant.services import prism_memory as prism
    from ai_assistant.services.prism_execution import execution_view
    monkeypatch.setattr('ai_assistant.views._can_use_learning_context',lambda user:True)
    with patch.object(prism,'extract',return_value={'features':{}}):prism.prepare(question)
    packet=prism.context(question)
    assert not packet['decision']['behavior'] and not packet['decision']['conflicts']
    assert execution_view(packet)['learner_patterns']['fields']==['node','mode']
    # Mutated evidence disappears on reads even without another write callback.
    results[0].user_answer='B';results[0].save(update_fields=['user_answer'])
    assert not context(question) and not prism.context(question)['learner_patterns']


def test_guided_repeated_and_other_project_results_do_not_leak(formal):
    _,question,record,_=formal
    first=record(0,'apply');record(1,'apply',existing=first.question)
    record(2,'apply',assistance='guided')
    memory=PrismMemory.objects.get()
    assert len(memory.cases)==1
    question.conversation_id=uuid4()
    assert not context(question)
