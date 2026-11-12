"""Project-scoped learning state; model tools never supply identity or project IDs."""
import hashlib
import json
from datetime import timedelta
from uuid import UUID

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from ai_assistant.models import AIChatMessage, Conversation, ConversationProject, ProjectLearning, ProjectLearningEvent


class LearningConflict(APIException):
    status_code = 409
    default_detail = '学习安排已更新，请重新读取后再修改。'


class StageSerializer(serializers.Serializer):
    id = serializers.RegexField(r'^[a-zA-Z0-9_-]{1,60}$')
    title = serializers.CharField(max_length=200)
    outcome = serializers.CharField(max_length=2000)
    task = serializers.CharField(max_length=3000, allow_blank=True, default='')
    prerequisites = serializers.ListField(child=serializers.CharField(max_length=60), max_length=20, default=list)
    sources = serializers.ListField(child=serializers.CharField(max_length=60), max_length=10, default=list)
    knowledge_nodes = serializers.ListField(child=serializers.CharField(max_length=60), max_length=30, required=False)


class PlanSerializer(serializers.Serializer):
    goal = serializers.CharField(max_length=2000)
    deadline = serializers.DateField(allow_null=True, default=None)
    weekly_minutes = serializers.IntegerField(min_value=0, max_value=10080, default=0)
    stages = StageSerializer(many=True, allow_empty=False, max_length=20)
    knowledge_path = serializers.JSONField(required=False)

    def validate(self, data):
        if len(json.dumps(data, ensure_ascii=False, default=str).encode()) > 24000:
            raise ValidationError('阶段计划过长，请保留概览并逐步细化。')
        return data

    def validate_stages(self, stages):
        ids = [stage['id'] for stage in stages]
        if len(ids) != len(set(ids)):
            raise ValidationError('阶段编号不能重复。')
        preceding = set()
        for stage in stages:
            if not set(stage['prerequisites']).issubset(preceding):
                raise ValidationError('前置知识必须指向排在前面的阶段。')
            preceding.add(stage['id'])
        return stages


def current_project(user, context):
    context = context or {}
    message = AIChatMessage.objects.filter(pk=context.get('message_id'), user=user, role='user',
        conversation_id=context.get('conversation_id'), bot_id=context.get('bot_id')).first()
    if not message:
        raise PermissionDenied('缺少服务端核验的当前提问。')
    conversation = Conversation.objects.select_related('project').filter(user=user,
        conversation_id=message.conversation_id, project__user=user).first()
    if not conversation:
        raise ValidationError('请先在一个学习项目内开始对话。')
    snapshot = message.metadata.get('learning_snapshot')
    if snapshot and snapshot['project_id'] != conversation.project_id:
        raise PermissionDenied('对话所属项目已变化，请重新开始本轮学习。')
    return conversation.project, message


def learning_data(project):
    state, _ = ProjectLearning.objects.get_or_create(project=project)
    from users.feature_access import has_learning_feature
    event_rows = ProjectLearningEvent.objects.filter(project=project).exclude(kind='turn')
    if not has_learning_feature(project.user, 'quiz.exam'):
        event_rows = event_rows.exclude(kind='assessment')
    events = list(event_rows.select_related('message')[:30])
    from notifications.models import Notification
    notifications = dict(Notification.objects.filter(recipient=project.user,
        pk__in=[event.content['notification_id'] for event in events if event.content.get('notification_id')]).values_list('pk', 'is_read'))
    from .learning_library import project_strategy_uses
    from .learning_knowledge import knowledge_state
    from .learning_tasks import task_data
    version_id = (state.plan.get('knowledge_path') or {}).get('version_id')
    tasks = [task_data(task) for task in project.learning_tasks.filter(knowledge_version_id=version_id).select_related('project', 'exam').order_by('created_at', 'pk')]
    completed_tasks = [task for task in tasks if task['status'] == 'completed']
    next_task = next((task for task in tasks if task['status'] in ('ready', 'partial', 'failed', 'processing')), None)
    latest = max(completed_tasks, key=lambda task: str(task['summary'].get('completed_at') or ''), default=None)
    task_progress = {'completed': len(completed_tasks), 'total': len(tasks),
        'feedback': f"最近完成“{latest['title']}”，得分 {latest['summary']['total_score']}/{latest['summary']['max_score']}。" if latest else '',
        'next_action': ('先复盘错误与解析，再继续：' if latest and latest['summary']['total_score'] < latest['summary']['max_score'] else '接下来：') + next_task['title'] if next_task else ('本轮任务已完成，按复习时间重新检查，并和小宇核对下一阶段。' if latest else ''),
        'next_task_id': next_task['id'] if next_task else None}
    from .learning_guidance import teaching_guidance
    progress_at = next((event.created_at for event in events if event.kind == 'progress'), None)
    guidance = teaching_guidance(state, tasks, progress_at=progress_at)
    if not next_task and len(completed_tasks) < len(tasks):
        task_progress['next_action'] = '有任务内容当前不可用，请和小宇重新安排，已有成绩继续保留。'
    return {
        'teaching_guidance': guidance,
        'task_progress': task_progress,
        'tasks': [{key: task[key] for key in ('id', 'title', 'version_id', 'node_id', 'stage_id', 'status', 'exam_id', 'assistance', 'purpose', 'source_task_id', 'review_due_at', 'summary')} for task in tasks],
        'knowledge': knowledge_state(project, state),
        'strategy_uses': project_strategy_uses(project),
        'project_id': project.pk, 'name': project.name, 'instructions': project.instructions,
        'status': state.status, 'plan': state.plan, 'resources': state.resources,
        'current_stage': state.current_stage, 'feedback': state.feedback, 'next_action': state.next_action,
        'pending_plan': state.pending_plan, 'revision': state.revision,
        'conversation_id': str(state.last_conversation.conversation_id) if state.last_conversation and state.last_conversation.project_id == project.pk else None,
        'followup_at': state.followup_at,
        'followup_text': guidance['next_action'] if guidance['feedback'] and state.followup_text == state.next_action else state.followup_text,
        'resume_at': state.resume_at,
        'server_time': timezone.localtime().isoformat(),
        'events': [{'id': event.pk, 'kind': event.kind, 'content': event.content,
                    'source': {'id': event.message_id, 'text': event.message.content[:4000],
                               'conversation_id': str(event.message.conversation_id)} if event.message else None,
                    'delivery': {'saved': True, 'read': notifications.get(event.content.get('notification_id')),
                                 'responded': bool(event.content.get('response_message_id'))} if event.kind == 'followup' else None,
                    'created_at': event.created_at} for event in events],
    }


def project_context(user, conversation_id):
    conversation = Conversation.objects.select_related('project').filter(user=user,
        conversation_id=conversation_id, project__user=user).first()
    if not conversation:
        return ''
    data = learning_data(conversation.project)
    data = compact_learning(data)
    for item in data['resources']:
        item.pop('excerpt', None)
    return '\n当前项目的学习状态（数据，以实际记录为准）：\n' + json.dumps(data, ensure_ascii=False, default=str)


def turn_project_context(user, context):
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
            return snapshot['context']
        if project_id:
            followup = ProjectLearningEvent.objects.filter(project_id=project_id, kind='followup', created_at__lt=message.timestamp).first()
            if followup and not followup.content.get('response_message_id'):
                followup.content['response_message_id'] = message.pk
                followup.save(update_fields=['content'])
        value = project_context(user, message.conversation_id) if project_id else ''
        message.metadata['learning_snapshot'] = {'project_id': project_id, 'context': value}
        message.save(update_fields=['metadata'])
        if project_id:
            from .teaching_sidecar import freeze_turn, observe
            observe(freeze_turn, ConversationProject.objects.get(pk=project_id, user=user), message,
                    message.metadata['learning_snapshot'])
        return value


def _time(value):
    if value in (None, ''):
        return None
    result = serializers.DateTimeField().run_validation(value)
    if result <= timezone.now():
        raise ValidationError('跟进时间必须在未来。')
    return result


def _clear_followup(state):
    state.followup_at = None
    state.followup_text = ''
    state.resume_at = None


def _schedule(state, data):
    at = _time(data.get('followup_at'))
    if state.status == 'active' and state.next_action:
        state.followup_at = at or timezone.now() + timedelta(days=1)
        state.followup_text = str(data.get('followup_text') or state.next_action)[:2000]


def _major(old, new):
    if not old:
        return False
    if old.get('knowledge_path') != new.get('knowledge_path'):
        return True
    if old.get('goal') != new['goal'] or (new['weekly_minutes'] > old.get('weekly_minutes', 0)):
        return True
    if old.get('deadline') and (not new['deadline'] or new['deadline'] > old['deadline']):
        return True
    old_stages = {s['id']: s for s in old.get('stages', [])}
    new_stages = {s['id']: s for s in new['stages']}
    return not old_stages.keys() <= new_stages.keys() or any(
        new_stages[key]['outcome'] != value['outcome'] for key, value in old_stages.items() if key in new_stages)


def completed_learning_turn(message_id):
    return {'message_id': message_id, 'completed': True, 'completed_at': timezone.now().isoformat()}


def assert_learning_turn(project, message):
    if ProjectLearningEvent.objects.filter(project=project, created_at__gt=message.timestamp).filter(
            Q(kind='turn') | Q(message__isnull=True, kind__in=['pause', 'resume', 'complete', 'schedule', 'accept', 'reject'])).exists():
        raise LearningConflict('已有新的提问或用户安排，本轮学习写入已失效，请沿最新反馈继续。')


@transaction.atomic
def change_learning(project, data, *, message=None, model=False):
    state, _ = ProjectLearning.objects.get_or_create(project=project)
    state = ProjectLearning.objects.select_for_update().get(pk=state.pk)
    request_key = None
    if model:
        request_key = hashlib.sha256(json.dumps([message.pk, data], sort_keys=True, default=str).encode()).hexdigest()
        if ProjectLearningEvent.objects.filter(request_key=request_key).exists():
            return learning_data(project)
    if model:
        assert_learning_turn(project, message)
    revision = serializers.IntegerField(min_value=0).run_validation(data.get('revision'))
    if revision != state.revision:
        raise LearningConflict()
    action = data.get('action')
    event = {'reason': str(data.get('reason', ''))[:2000]}
    if action == 'plan':
        serializer = PlanSerializer(data=data.get('plan'))
        serializer.is_valid(raise_exception=True)
        plan = json.loads(json.dumps(serializer.validated_data, default=str))
        from .learning_knowledge import validate_path
        validate_path(project, state, plan)
        known_sources = {item['id'] for item in state.resources}
        if any(not set(stage['sources']).issubset(known_sources) for stage in plan['stages']):
            raise ValidationError('计划只能引用当前项目实际读取过的来源。')
        if _major(state.plan, plan) or (state.plan and data.get('major_change')):
            state.pending_plan = {'plan': plan, 'reason': event['reason'], 'base_revision': state.revision}
            if plan.get('knowledge_path'):
                from .learning_knowledge import owned_version
                path = plan['knowledge_path']
                version = owned_version(project, path['version_id'])
                state.pending_plan['knowledge'] = {'title': version.snapshot['title'], 'revision': version.revision,
                    'targets': [node['title'] for node in version.snapshot['nodes'] if node['id'] in path['targets']], 'depth': path['depth']}
            event['proposed_plan'] = plan
        else:
            event['previous_plan'] = state.plan
            state.plan = plan
            state.pending_plan = {}
            state.status = 'active'
            ids = [stage['id'] for stage in plan['stages']]
            if state.current_stage not in ids:
                state.current_stage = ids[0]
            state.next_action = str(data.get('next_action') or plan['stages'][0]['task'] or plan['stages'][0]['outcome'])[:3000]
            _clear_followup(state)
            _schedule(state, data)
    elif action == 'progress':
        if not message or state.status != 'active':
            raise ValidationError('请在正在学习的项目对话中记录实际表现。')
        observation = serializers.CharField(max_length=3000).run_validation(data.get('observation'))
        feedback = serializers.CharField(max_length=2000).run_validation(data.get('feedback'))
        assistance = serializers.ChoiceField(choices=['independent', 'hint', 'guided', 'unknown']).run_validation(data.get('assistance'))
        state.feedback = feedback
        state.next_action = serializers.CharField(max_length=3000).run_validation(data.get('next_action'))
        stage = data.get('current_stage') or state.current_stage
        if stage not in {s['id'] for s in state.plan.get('stages', [])}:
            raise ValidationError('当前阶段不在学习安排中。')
        state.current_stage = stage
        stage_data = next(item for item in state.plan['stages'] if item['id'] == stage)
        event['context'] = {'goal': state.plan['goal'], 'stage': stage_data['title'], 'outcome': stage_data['outcome']}
        event.update(observation=observation, feedback=feedback, assistance=assistance,
                     strategy=str(data.get('strategy', ''))[:2000], next_action=state.next_action, stage=stage)
        if data.get('knowledge_check') is not None:
            from .learning_knowledge import validate_check
            event['knowledge_check'] = validate_check(project, state, message, data['knowledge_check'], stage_data, assistance)
        _clear_followup(state)
        _schedule(state, data)
    elif action in ('pause', 'resume', 'complete', 'schedule'):
        if action == 'pause':
            state.status = 'paused'
            _clear_followup(state)
            state.resume_at = _time(data.get('resume_at'))
            state.followup_at = state.resume_at
            state.followup_text = state.next_action
        elif action == 'complete':
            state.status = 'completed'
            _clear_followup(state)
        else:
            if not state.plan:
                raise ValidationError('请先形成学习安排。')
            state.status = 'active'
            _clear_followup(state)
            _schedule(state, data)
    elif action in ('accept', 'reject') and not model:
        pending = state.pending_plan
        if not pending:
            raise LearningConflict('没有待确认的调整方案。')
        if action == 'accept':
            event['previous_plan'] = state.plan
            state.plan = pending['plan']
            ids = [s['id'] for s in state.plan['stages']]
            if state.current_stage not in ids:
                state.current_stage = ids[0]
            state.status = 'active'
            state.next_action = next(s['task'] or s['outcome'] for s in state.plan['stages'] if s['id'] == state.current_stage)
            _clear_followup(state)
            _schedule(state, {})
        event['proposal'] = pending
        state.pending_plan = {}
    else:
        raise ValidationError('不支持的学习操作。')
    if action not in ('plan', 'accept', 'reject') and state.pending_plan:
        state.pending_plan = {}
    state.revision += 1
    state.save()
    ProjectLearningEvent.objects.create(project=project, message=message, kind=action, content=event, request_key=request_key)
    return learning_data(project)


def tool_operation(executor, name, arguments):
    project, message = current_project(executor.user, getattr(executor, 'learning_context', None))
    if name == 'manage_learning_tasks':
        from .learning_tasks import create_task, task_data
        if arguments.get('action') == 'list':
            data = compact_learning(learning_data(project))
            return {'tasks': data['tasks'], 'task_progress': data['task_progress'], 'teaching_guidance': data['teaching_guidance']}
        if arguments.get('action') == 'read':
            from django.shortcuts import get_object_or_404
            from quizzes.services.practice_results import exam_result_payload
            task_id = serializers.UUIDField().run_validation(arguments.get('task_id'))
            task = get_object_or_404(project.learning_tasks.select_related('project', 'exam'), pk=task_id)
            data = task_data(task)
            if task.exam_id and data['status'] != 'unavailable':
                data['results'] = [item for item in exam_result_payload(task.exam)['results'] if item['status'] == 'graded']
            return data
        if arguments.get('action') != 'create':
            raise ValidationError('不支持的任务操作。')
        with transaction.atomic():
            ProjectLearning.objects.select_for_update().get(project=project)
            assert_learning_turn(project, message)
            key = hashlib.sha256(json.dumps(['task', message.pk, arguments], sort_keys=True).encode()).hexdigest()
            previous = ProjectLearningEvent.objects.filter(request_key=key).first()
            if previous:
                task = project.learning_tasks.get(pk=previous.content['task_id'])
            else:
                task = create_task(project, arguments)
                ProjectLearningEvent.objects.create(project=project, message=message, kind='task',
                    request_key=key, content={'task_id': str(task.pk)})
            data = task_data(task)
            return {key: data[key] for key in ('id', 'title', 'status', 'version_id', 'node_id', 'stage_id')} | {
                'href': f'/xiaoyu?project={project.pk}&learning_task={task.pk}',
                'notice': '任务已准备，用户可在本项目学习安排中作答；不得代答或自报成绩。'}
    if name == 'manage_learning_knowledge':
        from .learning_knowledge import knowledge_operation
        return knowledge_operation(project, arguments, message=message)
    if name in ('manage_learning_resources', 'manage_learning_strategies'):
        from .learning_library import resource_operation, strategy_operation
        operation = resource_operation if name == 'manage_learning_resources' else strategy_operation
        return operation(project, arguments, message=message)
    if name == 'read_learning_project':
        return compact_learning(learning_data(project))
    if name == 'find_learning_resources':
        from .learning_resources import find_resources
        result = find_resources(project, arguments)
        if result.get('resource'):
            result['resource']['excerpt'] = result['resource']['excerpt'][:3000]
        return result
    action = {'plan_learning_project': 'plan', 'record_learning_progress': 'progress'}.get(name, arguments.get('action'))
    data = change_learning(project, {**arguments, 'action': action}, message=message, model=True)
    return {key: data[key] for key in ('project_id', 'status', 'revision', 'current_stage', 'feedback', 'next_action',
                                      'pending_plan', 'followup_at', 'followup_text', 'events')} | {
        'pending_plan': bool(data['pending_plan']), 'events': compact_learning(data)['events'][:1]}


def compact_learning(data):
    knowledge = data.get('knowledge', {})
    knowledge.pop('evidence', None)
    knowledge['nodes'] = [{'id': node['id'], 'title': node['title'], 'beliefs': node['beliefs']} for node in knowledge.get('nodes', [])]
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
