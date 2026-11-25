"""Trusted task-memory source adapter and deterministic readout, version 1."""
import json


def project_view(source, estimates, threshold):
    from .public_methods import route
    from .method_adoption import render_history
    history = {}
    if 'task_replies' in source:
        from .method_adoption import render_task_replies
        task_id = source['project']['focus_task_id'] or next((task['id'] for task in source['tasks']
            if task['is_current'] and task['status'] != 'completed'), None)
        if task_id is None and source['task_replies']['links']:
            task_id = source['task_replies']['links'][-1]['task_id']
        history = render_task_replies(source['task_replies'], task_id)
        if len(history['items']) > 2:
            history = {**history, 'items':[history['items'][0], history['items'][-1]], 'selection':'first_and_latest'}
    return {'project':source['project'],'formal_evidence':source['observations'],
            'estimates':estimates,'next_checks':[node for node,value in estimates.items()
                if value['independent_count']>=2 and value['predicted_success']<threshold],
            'reply_sources':source['replies'],'tasks':source['tasks'],'facts':source['facts'],
            'notice':'Conditional performance estimates and research-authored check policy; no mastery or teaching-effect claim.',
            **({'public_methods':route(source,estimates)} if 'public_methods' in source else {}),
            **({'method_history':render_history(source)} if 'method_history' in source else {}),
            **({'evidence_scope':source['evidence_scope']} if 'evidence_scope' in source else {}),
            **({'reply_history':history} if 'task_replies' in source else {})}


def task_packet(view):
    project=view['project'];tasks=view['tasks'];recent=view['formal_evidence'][-6:]
    recent_rows=[{key:row[key] for key in ['event_id','task_id','node_id','mode','outcome','assistance','score','max_score','at']} for row in recent]
    if 'evidence_scope' in view:
        recent_rows=[{**row,'origin_version_id':source['version_id']} for row,source in zip(recent_rows,recent)]
    task_keys=['id','title','node_id','stage_id','mode','purpose','status','assistance']
    if project.get('readout_schema') == 'task-episodes-v1':
        task_keys += ['version_id','source_task_id','created_at']
    return {'project':{key:project[key] for key in ['id','owner','status','current_stage','revision','plan','next_action','pending_plan','followup_at','resume_at']},
            'facts':view['facts'],'estimates':view['estimates'],'next_checks':view['next_checks'],
            'pending_tasks':[{key:task[key] for key in task_keys}
                             for task in tasks if task['is_current'] and task['status']!='completed'],
            'completed_tasks':sum(task['is_current'] and task['status']=='completed' for task in tasks),
            'recent_formal_evidence':recent_rows,
            'source_access':'Original task results and reply sources remain available through the same scoped inspection tools.',
            'notice':view['notice'], **({'public_methods':view['public_methods']} if 'public_methods' in view else {}),
            **({'method_history':view['method_history']} if 'method_history' in view else {}),
            **({'evidence_scope':view['evidence_scope']} if 'evidence_scope' in view else {}),
            **({'reply_history':view['reply_history']} if 'reply_history' in view else {})}


def packet_from_parts(project,facts,tasks,recent,completed,estimates,threshold):
    source={'project':project,'facts':facts,'tasks':list(tasks.values()),
            'observations':list(recent.values()),'replies':[]}
    packet=task_packet(project_view(source,estimates,threshold))
    packet['completed_tasks']=completed
    return packet


def project_source(project, *, now=None):
    from ai_assistant.models import AIChatMessage,Conversation,ProjectLearning
    from ai_assistant.services.learning_continuity import formal_observations
    from ai_assistant.services.prism_memory import accessible
    from django.contrib.auth import get_user_model
    from django.db.models import Q
    from rest_framework.exceptions import PermissionDenied
    current_user=get_user_model().objects.filter(pk=project.user_id,is_active=True).first()
    if current_user is None:raise PermissionDenied('Inactive learner')
    project.user=current_user
    state=ProjectLearning.objects.get(project=project)
    version=(state.plan.get('knowledge_path') or {}).get('version_id')
    from ai_assistant.models import ProjectLearningEvent
    from quizzes.models import ExamQuestionResult
    from ai_assistant.services.learning_tasks import sync_task_result
    from rest_framework.exceptions import ValidationError
    known=[pk for pk in ProjectLearningEvent.objects.filter(project=project,kind='assessment').values_list('content__result_id',flat=True) if isinstance(pk,int)]
    missing=ExamQuestionResult.objects.filter(status='graded',exam__user_id=project.user_id,
        exam__learning_task__project=project,exam__learning_task__knowledge_version_id=version).exclude(pk__in=known).select_related('exam','question__knowledge_point')
    for result in missing:
        try:sync_task_result(result)
        except (PermissionDenied,ValidationError):continue
    observations,verified,continuity=formal_observations(project,version)
    from ai_assistant.services.learning_knowledge import verified_knowledge_events
    conversations_checked=[]
    if version is not None:
        for event,probe in verified_knowledge_events(project,version)['events']:
            conversations_checked.append({**event.content['knowledge_check'], 'event_id':event.pk,
                'message_id':event.message_id, 'probe_message_id':probe.message_id,
                'conversation_id':str(event.message.conversation_id), 'source':event.message.content,
                'at':event.created_at.isoformat(), 'evidence_type':'conversation'})
    conversations=Conversation.objects.filter(project=project,user_id=project.user_id).values('conversation_id')
    from .method_adoption import task_reply_source
    task_replies=task_reply_source(project)
    artifact_replies={row['reply_id'] for row in task_replies['links']}
    replies=[]
    for answer in AIChatMessage.objects.filter(user_id=project.user_id,conversation_id__in=conversations,
            role='assistant',metadata__learning_turn__completed=True).order_by('pk'):
        if answer.pk in artifact_replies:
            continue
        turn=answer.metadata['learning_turn']
        question=AIChatMessage.objects.filter(pk=turn.get('message_id'),user_id=project.user_id,
            conversation_id=answer.conversation_id,bot_id=answer.bot_id,role='user').first()
        if question and accessible(question) and answer.content.strip():
            replies.append({'question_id':question.pk,'reply_id':answer.pk,'question':question.content,
                            'reply':answer.content,'occurred_at':turn.get('completed_at')})
    from ai_assistant.services.learning_tasks import task_states
    from ai_assistant.services.memory_core import fact_snapshot
    tasks=task_states(project,state,scope=continuity)
    focus=project.learning_events.filter(kind='focus',content__version_id=version).first()
    progress=project.learning_events.filter(kind='progress',content__stage=state.current_stage).filter(
        Q(content__mainline=True)|Q(content__mainline__isnull=True)).first()
    source={'tasks':tasks,'task_replies':task_replies,'facts':fact_snapshot(project.user,project=project,now=now),'project':{'id':project.pk,'owner':project.user_id,'status':state.status,
            'plan':state.plan,'current_stage':state.current_stage,'revision':state.revision,
            'next_action':state.next_action,'pending_plan':state.pending_plan,'resources':state.resources,
            'followup_at':state.followup_at,'resume_at':state.resume_at,'feedback':state.feedback,
            'focus_task_id':focus.content.get('task_id') if focus else None,
            'progress_at':progress.created_at if progress else None},'observations':observations,
            'conversation_observations':conversations_checked,'replies':replies}
    source['project']['readout_schema']='task-episodes-v1'
    if continuity is not None:
        source['evidence_continuity']=continuity
        source['project']['task_scope_schema']='exact-definition-v1'
    from .public_methods import catalogue
    from .learning_knowledge import owned_version, closure
    source['public_methods']=catalogue()
    from .method_adoption import history_source
    from . import learning_diagnostics
    support = None
    if learning_diagnostics.active():
        from ai_assistant.models import TaskMemoryObject
        relevant_tasks = {task['id'] for task in tasks if task['is_current'] and task['status'] == 'ready'}
        relevant_tasks.update(row['task_id'] for row in observations)
        relevant_tasks.update(str(pk) for pk in TaskMemoryObject.objects.filter(
            project=project, owner_id=project.user_id, kind='method_use').values_list('task_id', flat=True))
        support = learning_diagnostics.read_sources(project, relevant_tasks, now=now)
        if support:
            source['diagnostic_support'] = support
    source['method_history'],source['method_versions']=history_source(
        project,verified['events'],tasks,source['public_methods'],verified['verified_versions'], diagnostic_sources=support)
    source['project']['method_history_selection']='pending-recent-v1'
    source['project']['concepts']={node['id']:node['title'] for node in closure(
        owned_version(project,version).snapshot,state.plan['knowledge_path']['targets'])} if version is not None else {}
    source=json.loads(json.dumps(source,default=str,ensure_ascii=False))
    return source
