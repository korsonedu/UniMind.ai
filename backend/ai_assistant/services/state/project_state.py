"""L2 State Layer — project-scoped learning state assembly, receipts, snapshots and read projections."""
import json
from uuid import UUID

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from ai_assistant.models import AIChatMessage, Conversation, ConversationProject, ProjectLearning, ProjectLearningEvent
from ai_assistant.services.runtime.ulr_config import ulr_enabled
from ai_assistant.services.views.guidance_messages import guidance_text


class LearningConflict(APIException):
    status_code = 409
    default_detail = '学习安排已更新，请重新读取后再修改。'


def model_event_reservation(event):
    """Distinguish earlier untracked events from events missing their required receipt."""
    if not event or not event.request_key:
        return False, None
    if not event.message_id:
        return True, None
    metadata = event.message.metadata
    if 'runtime_request_id' not in metadata:
        return False, None
    try:
        request_id = UUID(metadata['runtime_request_id'])
    except (ValueError, TypeError, AttributeError):
        return True, None
    from users.models import AIUsageReservation
    receipt = AIUsageReservation.objects.filter(user_id=event.message.user_id, request_id=request_id).only(
        'user_id', 'status', 'updated_at', 'response').first()
    return True, receipt


def message_receipts(user_id, rows):
    rows = rows.filter(
        message__user_id=user_id, message__role='user', message__metadata__has_key='runtime_request_id')
    origins = []
    for pk, raw in rows.values_list('pk', 'message__metadata__runtime_request_id'):
        try:
            origins.append((pk, UUID(raw)))
        except (ValueError, TypeError, AttributeError):
            continue
    if not origins:
        return {}
    from users.models import AIUsageReservation
    receipts = {row[0]: row[1:] for row in AIUsageReservation.objects.filter(user_id=user_id,
        request_id__in={request_id for _, request_id in origins}).values_list('request_id', 'status', 'response')}
    return {pk: receipts.get(request_id, (None, {})) for pk, request_id in origins}


def unconfirmed_progress_ids(user_id, project_id=None):
    if not ulr_enabled():
        return set()
    events = ProjectLearningEvent.objects.filter(project__user_id=user_id, kind='progress', request_key__isnull=False)
    if project_id is not None:
        events = events.filter(project_id=project_id)
    hidden = set()
    for pk, (status, response) in message_receipts(user_id, events).items():
        native_event = ((response.get('metadata') or {}).get('ulr_progress') or {}).get('event_id')
        if status != 'succeeded' or (response.get('engine') == 'ulr' and native_event != pk):
            hidden.add(pk)
    return hidden


def unconfirmed_plan_ids(project):
    if not ulr_enabled():
        return set()
    events = project.learning_events.filter(kind='plan', content__has_key='proposed_plan', request_key__isnull=False)
    hidden = set()
    for pk, (status, response) in message_receipts(project.user_id, events).items():
        plan = (response.get('metadata') or {}).get('ulr_plan') or {}
        if (status != 'succeeded' or response.get('deleted')
                or response.get('engine') == 'ulr' and (plan.get('pending_plan') is not True or plan.get('event_id', pk) != pk)):
            hidden.add(pk)
    return hidden


def unconfirmed_pending_plan(project, pending, hidden):
    if not pending.get('plan') or not hidden:
        return False
    proposal = project.learning_events.filter(kind='plan', content__proposed_plan=pending['plan']).values_list('pk', flat=True).first()
    return proposal in hidden


def current_project(user, context, *, require_project=True):
    context = context or {}
    message = AIChatMessage.objects.filter(pk=context.get('message_id'), user=user, role='user',
        conversation_id=context.get('conversation_id'), bot_id=context.get('bot_id')).first()
    if not message:
        raise PermissionDenied('缺少服务端核验的当前提问。')
    conversation = Conversation.objects.select_related('project').filter(user=user,
        conversation_id=message.conversation_id, project__user=user).first()
    if not conversation and require_project:
        raise ValidationError('请先在一个学习项目内开始对话。')
    snapshot = message.metadata.get('learning_snapshot')
    if snapshot and snapshot.get('project_id') != (conversation.project_id if conversation else None):
        raise PermissionDenied('对话所属项目已变化，请重新开始本轮学习。')
    return (conversation.project if conversation else None), message


def _focused_task(project, state, tasks):
    version_id = (state.plan.get('knowledge_path') or {}).get('version_id')
    tasks = tasks.filter(knowledge_version_id=version_id, stage_id=state.current_stage)
    event = project.learning_events.filter(kind='focus', content__version_id=version_id).first()
    focused = tasks.filter(pk=event.content['task_id']).first() if event else None
    return focused or tasks.order_by('created_at', 'pk').first()


def public_event_content(event):
    content = event.content
    if event.kind == 'probe':
        return {key: value for key, value in content.items() if key != 'rubric'}
    if event.kind == 'progress' and isinstance(check := content.get('knowledge_check'), dict):
        return {**content, 'knowledge_check': {key: value for key, value in check.items() if key != 'rubric'}}
    return content


def learning_data(project, language='zh-CN', *, current_message=None, memory_read=None, diagnostic_excluded=None):
    state, _ = ProjectLearning.objects.get_or_create(project=project)
    from users.feature_access import has_learning_feature
    event_rows = ProjectLearningEvent.objects.filter(project=project).exclude(kind__in=('turn', 'knowledge_view', 'agent_checkpoint'))
    hidden_plans = unconfirmed_plan_ids(project)
    event_rows = event_rows.exclude(pk__in=hidden_plans)
    unconfirmed = unconfirmed_progress_ids(project.user_id, project.pk)
    if unconfirmed:
        progress = event_rows.filter(kind='progress').exclude(
            content__has_key='mainline', content__mainline=False)
        latest = progress.first()
        if latest and latest.pk in unconfirmed:
            prior = progress.filter(content__stage=state.current_stage).exclude(pk__in=unconfirmed).first()
            stage = next((row for row in state.plan.get('stages', []) if row['id'] == state.current_stage), {})
            if state.feedback == latest.content.get('feedback'):
                state.feedback = prior.content.get('feedback', '') if prior else ''
            if state.next_action == latest.content.get('next_action'):
                if state.followup_text == state.next_action:
                    state.followup_at, state.followup_text = None, ''
                state.next_action = prior.content.get('next_action', '') if prior else stage.get('task') or stage.get('outcome', '')
        event_rows = event_rows.exclude(pk__in=unconfirmed)
    if not has_learning_feature(project.user, 'quiz.exam'):
        event_rows = event_rows.exclude(kind='assessment')
    events = list(event_rows.select_related('message')[:30])
    from notifications.models import Notification
    notifications = dict(Notification.objects.filter(recipient=project.user,
        pk__in=[event.content['notification_id'] for event in events if event.content.get('notification_id')]).values_list('pk', 'is_read'))
    from ai_assistant.services.facts.learning_library import project_strategy_uses
    from ai_assistant.services.state.knowledge.learning_knowledge import knowledge_state
    from ai_assistant.services.facts.learning_tasks import available_project_tasks, task_data
    version_id = (state.plan.get('knowledge_path') or {}).get('version_id')
    project_tasks = available_project_tasks(project)
    if memory_read is None:
        selected = project_tasks.filter(Q(knowledge_version_id=version_id) | Q(purpose='diagnostic', stage_id=''))
        from ai_assistant.services.state.sdtm.fact_evidence import active
        scope = None
        if active():
            from ai_assistant.services.state.knowledge.learning_continuity import definition_scope, current_task_ids
            scope = definition_scope(project, version_id)
            identities = [{'id': str(row['id']), 'version_id': row['knowledge_version_id'],
                'node_id': row['node_id'], 'stage_id': row['stage_id']} for row in
                project.learning_tasks.values('id', 'knowledge_version_id', 'node_id', 'stage_id')]
            selected = project_tasks.filter(Q(pk__in=current_task_ids(state.plan, identities, scope)) | Q(purpose='diagnostic', stage_id=''))
        tasks = [task_data(task, scope=scope) for task in selected.select_related('project', 'exam').order_by('created_at', 'pk')]
        completed_tasks = [task for task in tasks if task['status'] == 'completed']
        next_task = next((task for task in tasks if task['status'] in ('ready', 'partial', 'failed', 'processing')), None)
        latest = max(completed_tasks, key=lambda task: str(task['summary'].get('completed_at') or ''), default=None)
        task_progress = {'completed': len(completed_tasks), 'total': len(tasks),
            'feedback': guidance_text('最近完成“{0}”，得分 {1}/{2}。', language, latest['title'], latest['summary']['total_score'], latest['summary']['max_score']) if latest else '',
            'next_action': (guidance_text('先复盘错误与解析，再继续：', language) if latest and latest['summary']['total_score'] < latest['summary']['max_score'] else guidance_text('接下来：', language)) + next_task['title'] if next_task else (guidance_text('本轮任务已完成，按复习时间重新检查，并和小宇核对下一阶段。', language) if latest else ''),
            'next_task_id': next_task['id'] if next_task else None}
        from ai_assistant.services.decision.learning_guidance import teaching_guidance
        progress_at = next((event.created_at for event in events if event.kind == 'progress' and event.content.get('stage') == state.current_stage and event.content.get('mainline', True)), None)
        focused = _focused_task(project, state, project_tasks)
        focus_task_id = str(focused.pk) if focused else None
        guidance = teaching_guidance(state, tasks, progress_at=progress_at, focus_task_id=focus_task_id, language=language)
        # All learner surfaces follow the same current episode. Other tasks still keep their results.
        task_progress.update(feedback=guidance['feedback'], next_action=guidance['next_action'], next_task_id=guidance['task_id'])
        if not next_task and len(completed_tasks) < len(tasks):
            task_progress['next_action'] = guidance_text('有任务内容当前不可用，请和小宇重新安排，已有成绩继续保留。', language)
    else:
        tasks = []
        task_progress = {}
        focused = project.learning_events.filter(kind='focus', content__version_id=version_id).first()
        focus_task_id = focused.content.get('task_id') if focused and project_tasks.filter(
            pk=focused.content.get('task_id'), knowledge_version_id=version_id, stage_id=state.current_stage).exists() else None
        guidance = {'next_action': state.next_action, 'feedback': state.feedback}
    data = {
        'teaching_guidance': guidance, 'focus_task_id': focus_task_id,
        'task_progress': task_progress,
        'tasks': [{key: task[key] for key in ('id', 'title', 'version_id', 'node_id', 'stage_id', 'status', 'exam_id', 'assistance', 'purpose', 'source_task_id', 'review_due_at', 'summary')} for task in tasks],
        'knowledge': knowledge_state(project, state, current_message=current_message,
            estimates=memory_read['packet']['estimates'] if memory_read and memory_read.get('task_access', True) else None,
            diagnostic_excluded=diagnostic_excluded),
        'strategy_uses': project_strategy_uses(project),
        'project_id': project.pk, 'name': project.name, 'instructions': project.instructions,
        'planning_enabled': state.planning_enabled, 'reminders_enabled': state.reminders_enabled,
        'status': state.status, 'plan': state.plan, 'resources': state.resources,
        'current_stage': state.current_stage, 'feedback': state.feedback, 'next_action': state.next_action,
        'pending_plan': {} if unconfirmed_pending_plan(project, state.pending_plan, hidden_plans) else state.pending_plan,
        'revision': state.revision,
        'conversation_id': str(state.last_conversation.conversation_id) if state.last_conversation and state.last_conversation.project_id == project.pk else None,
        'followup_at': state.followup_at,
        'followup_text': guidance['next_action'] if guidance['feedback'] and state.followup_text == state.next_action else state.followup_text,
        'resume_at': state.resume_at,
        'server_time': timezone.localtime().isoformat(),
        'events': [{'id': event.pk, 'kind': event.kind, 'content': public_event_content(event),
                    'source': {'id': event.message_id, 'text': event.message.content[:4000],
                               'conversation_id': str(event.message.conversation_id)} if event.message else None,
                    'delivery': {'saved': True, 'read': notifications.get(event.content.get('notification_id')),
                                 'responded': bool(event.content.get('response_message_id'))} if event.kind == 'followup' else None,
                    'created_at': event.created_at} for event in events],
    }
    if memory_read is not None:
        if data['revision'] != memory_read['packet']['project']['revision']:
            raise LearningConflict()
        from ai_assistant.services.state.sdtm.task_memory_store import apply_projection
        data = apply_projection(data, memory_read)
    return data


def activity_snapshot(project, raw):
    """Viewing an owned task/map supplies context; it never moves the learning focus."""
    from django.shortcuts import get_object_or_404
    from ai_assistant.services.facts.learning_tasks import available_project_tasks, task_data
    from ai_assistant.services.state.knowledge.learning_knowledge import owned_version, closure
    if not isinstance(raw, dict):
        raise ValidationError('学习内容引用格式无效。')
    if raw.get('task_id'):
        pk = serializers.UUIDField().run_validation(raw['task_id'])
        tasks = available_project_tasks(project)
        task = get_object_or_404(tasks.select_related('project', 'exam'), pk=pk)
        data = task_data(task)
        from ai_assistant.services.state.sdtm.fact_evidence import active
        if active() and data['status'] != 'unavailable':
            from ai_assistant.services.decision.method_adoption import read_task_replies, select_task_replies
            data['reply_history'] = select_task_replies(read_task_replies(project, task))
        result = {'kind': 'task', 'task': data, 'mainline': data['is_current'] and task.stage_id == project.learning.current_stage}
        focused = _focused_task(project, project.learning, tasks)
        if focused:
            def root(item):
                while item.source_task_id:
                    item = item.source_task
                return item.pk
            result['mainline'] = result['mainline'] and data['is_current'] and root(focused) == root(task)
        if data.get('summary') and task.exam_id:
            from quizzes.services.practice_results import exam_result_payload
            result['results'] = exam_result_payload(task.exam)
        return json.loads(json.dumps(result, default=str))
    if raw.get('resource_id') or (raw.get('stage_id') and not raw.get('version_id')):
        from django.http import Http404
        state = project.learning
        key = 'stage_id' if raw.get('stage_id') else 'resource_id'
        selected = serializers.CharField(max_length=60).run_validation(raw[key])
        items = state.plan.get('stages', []) if key == 'stage_id' else state.resources
        item = next((row for row in items if row['id'] == selected), None)
        if not item:
            raise Http404
        return {'kind': 'stage' if key == 'stage_id' else 'resource', 'content': item, 'mainline': False}
    version_id = serializers.IntegerField(min_value=1).run_validation(raw.get('version_id'))
    version = owned_version(project, version_id)
    targets = raw.get('targets') or ([raw['node_id']] if raw.get('node_id') else [])
    targets = serializers.ListField(child=serializers.CharField(max_length=60), min_length=1, max_length=30).run_validation(targets)
    return {'kind': 'knowledge', 'version_id': version.pk, 'title': version.snapshot['title'],
            'node_id': targets[0] if raw.get('node_id') else None, 'targets': targets,
            'nodes': closure(version.snapshot, targets), 'depth': raw.get('depth', 'apply'),
            'stage_id': next((stage['id'] for stage in project.learning.plan.get('stages', [])
                              if raw.get('node_id') in stage.get('knowledge_nodes', [])), None), 'mainline': False}


def project_context(user, conversation_id, *, message=None, private_probe_review=False, memory_read=None, diagnostic_excluded=None):
    conversation = Conversation.objects.select_related('project').filter(user=user,
        conversation_id=conversation_id, project__user=user).first()
    if not conversation:
        return ''
    if message is None:
        message = AIChatMessage.objects.filter(user=user, conversation_id=conversation_id, role='user').order_by('-id').first()
    if not ProjectLearning.objects.filter(project_id=conversation.project_id, planning_enabled=True).exists():
        return '\n自由对话的项目背景（查看内容不启用规划或改变项目模式）：' + json.dumps({'name': conversation.project.name,
            'instructions': conversation.project.instructions,
            'viewed_activity': message.metadata.get('learning_activity') if message else None}, ensure_ascii=False, default=str)
    from django.conf import settings
    memory_mode = getattr(settings, 'UNIMIND_SDTM_TASK_MEMORY_MODE', 'off')
    prepared = None
    if memory_mode == 'active':
        if memory_read is None:
            from ai_assistant.services.state.sdtm.task_memory_store import prepare
            prepared = prepare(conversation.project, user)
        else:
            subject = memory_read['packet']['project']
            if subject['id'] != conversation.project_id or subject['owner'] != user.pk:
                raise PermissionDenied('当前权限无法读取该项目记忆。')
            prepared = memory_read
    data = compact_learning(learning_data(conversation.project, current_message=message, memory_read=prepared,
        diagnostic_excluded=diagnostic_excluded if prepared is not None else None))
    if memory_mode == 'shadow':
        from ai_assistant.services.state.sdtm.task_memory_store import prepare
        from ai_assistant.services.facts.teaching_sidecar import observe
        observe(prepare, conversation.project, user, expected_revision=data['revision'])
    if private_probe_review:
        for probe in data['knowledge']['probes']:
            probe.pop('rubric', None)
    from users.feature_access import has_learning_feature
    if data['status'] == 'preparing' and has_learning_feature(user, 'quiz.exam'):
        recent = ProjectLearningEvent.objects.filter(project__user=user, project__learning__status='completed',
            kind='complete', content__has_key='summary').exclude(project_id=conversation.project_id)[:3]
        if summaries := [event.content['summary'] for event in recent]:
            data['recent_learning_outcomes'] = summaries
    if message and message.metadata.get('learning_activity'):
        data['viewed_activity'] = message.metadata['learning_activity']
        data['view_notice'] = '这是用户正在查看的内容。优先解释 viewed_activity.node_id 或 targets；nodes 包含前置知识，不代表用户选中了第一个节点，current_stage 仅代表学习主线。查看、讲解和旁支作答不改变学习主线，不自动推进当前阶段。讲解图可以呈现知识关系，不要把尚未校准的条件估计填作 mastery 或掌握度。'
    for item in data['resources']:
        item.pop('excerpt', None)
    value = '\n当前项目的学习状态（数据，以实际记录为准）：\n' + json.dumps(data, ensure_ascii=False, default=str)
    from ai_assistant.services.state.sdtm.memory_core import project_context_prepared
    if project_context_prepared.has_listeners():
        from ai_assistant.services.facts.teaching_sidecar import observe
        observe(project_context_prepared.send, sender=ConversationProject,
                project=conversation.project, user=user, context=value)
    return value


def model_project_context(value):
    if not value.startswith('\n当前项目的学习状态'):
        return value
    lines = value.split('\n', 2)
    data = json.loads(lines[2])
    data.pop('memory_read', None)
    data.pop('diagnostic_support', None)
    if (observation := data.get('memory_observation')) and 'fields' in observation:
        observation['fields'] = [key for key in observation['fields'] if key != 'diagnostic_support']
    return '\n'.join([*lines[:2], json.dumps(data, ensure_ascii=False, default=str)])


def turn_project_context(user, context, *, private_probe_review=False):
    """Freeze teaching data for this signed question; authorization stays live."""
    if not context:
        return ''
    with transaction.atomic():
        message = AIChatMessage.objects.select_for_update().filter(pk=context.get('message_id'), user=user,
            role='user', conversation_id=context.get('conversation_id'), bot_id=context.get('bot_id')).first()
        if not message:
            raise PermissionDenied('当前学习提问已失效。')
        project_id = Conversation.objects.filter(user=user, conversation_id=message.conversation_id,
            project__user=user).values_list('project_id', flat=True).first()
        snapshot = message.metadata.get('learning_snapshot')
        if snapshot:
            if snapshot['project_id'] != project_id:
                raise PermissionDenied('对话所属项目已变化，请重新开始本轮学习。')
            if snapshot.get('probe_rubrics_scoped') and snapshot.get('private_probe_review', False) == private_probe_review:
                from ai_assistant.services.state.sdtm.fact_evidence import active
                frame = snapshot.get('memory_frame_id')
                if frame and active():
                    from ai_assistant.services.state.sdtm.task_memory_store import restore
                    restore(frame, user)
                    return snapshot['context']
                if not frame and (not active() or not project_id):
                    return snapshot['context']
        if project_id:
            followup = ProjectLearningEvent.objects.filter(project_id=project_id, kind='followup', created_at__lt=message.timestamp).first()
            if followup and not followup.content.get('response_message_id'):
                followup.content['response_message_id'] = message.pk
                followup.save(update_fields=['content'])
        value = project_context(user, message.conversation_id, message=message, private_probe_review=private_probe_review) if project_id else ''
        message.metadata['learning_snapshot'] = {'project_id': project_id, 'context': value, 'probe_rubrics_scoped': True,
                                                 'private_probe_review': private_probe_review}
        if value.startswith('\n当前项目的学习状态'):
            data = json.loads(value.split('\n', 2)[2])
            if data.get('memory_read'):
                message.metadata['learning_snapshot']['memory_frame_id'] = data['memory_read']['frame_id']
        message.save(update_fields=['metadata'])
        if project_id:
            from ai_assistant.services.facts.teaching_sidecar import freeze_turn, observe
            observe(freeze_turn, ConversationProject.objects.get(pk=project_id, user=user), message,
                    message.metadata['learning_snapshot'])
        return value


def model_learning_data(project, user, *, language='zh-CN'):
    from django.conf import settings
    prepared = None
    if getattr(settings, 'UNIMIND_SDTM_TASK_MEMORY_MODE', 'off') == 'active':
        from ai_assistant.services.state.sdtm.task_memory_store import preview
        prepared = preview(project, user)
    data = compact_learning(learning_data(project, language=language, memory_read=prepared))
    data.pop('memory_read', None)
    return data


def compact_learning(data):
    knowledge = data.get('knowledge', {})
    knowledge.pop('evidence', None)
    knowledge['nodes'] = [{'id': node['id'], 'title': node['title'], 'beliefs': node['beliefs'], 'learning_status': node['learning_status']} for node in knowledge.get('nodes', [])]
    if not data.get('memory_read'):
        data['tasks'] = data.get('tasks', [])[-15:]
    data['events'] = data['events'][:5]
    for event in data['events']:
        if event['source']:
            event['source']['text'] = event['source']['text'][:1000]
        event['content'].pop('previous_plan', None)
        event['content'].pop('proposed_plan', None)
        event['content'].pop('proposal', None)
        event['content'] = {key: value[:700] if isinstance(value, str) else value for key, value in event['content'].items()}
    data['resources'] = data['resources'][-8:]
    for item in data['resources']:
        item['excerpt'] = item.get('excerpt', '')[:1500]
    return data
