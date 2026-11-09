"""Project-scoped learning state; model tools never supply identity or project IDs."""
import hashlib
import json
from datetime import timedelta
from uuid import UUID

from django.db import transaction
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


class PlanSerializer(serializers.Serializer):
    goal = serializers.CharField(max_length=2000)
    deadline = serializers.DateField(allow_null=True, default=None)
    weekly_minutes = serializers.IntegerField(min_value=0, max_value=10080, default=0)
    stages = StageSerializer(many=True, allow_empty=False, max_length=20)

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
    events = list(ProjectLearningEvent.objects.filter(project=project).select_related('message')[:30])
    from notifications.models import Notification
    notifications = dict(Notification.objects.filter(recipient=project.user,
        pk__in=[event.content['notification_id'] for event in events if event.content.get('notification_id')]).values_list('pk', 'is_read'))
    return {
        'project_id': project.pk, 'name': project.name, 'instructions': project.instructions,
        'status': state.status, 'plan': state.plan, 'resources': state.resources,
        'current_stage': state.current_stage, 'feedback': state.feedback, 'next_action': state.next_action,
        'pending_plan': state.pending_plan, 'revision': state.revision,
        'conversation_id': str(state.last_conversation.conversation_id) if state.last_conversation and state.last_conversation.project_id == project.pk else None,
        'followup_at': state.followup_at, 'followup_text': state.followup_text, 'resume_at': state.resume_at,
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
    if old.get('goal') != new['goal'] or (new['weekly_minutes'] > old.get('weekly_minutes', 0)):
        return True
    if old.get('deadline') and (not new['deadline'] or new['deadline'] > old['deadline']):
        return True
    old_stages = {s['id']: s for s in old.get('stages', [])}
    new_stages = {s['id']: s for s in new['stages']}
    return not old_stages.keys() <= new_stages.keys() or any(
        new_stages[key]['outcome'] != value['outcome'] for key, value in old_stages.items() if key in new_stages)


@transaction.atomic
def change_learning(project, data, *, message=None, model=False):
    state, _ = ProjectLearning.objects.get_or_create(project=project)
    state = ProjectLearning.objects.select_for_update().get(pk=state.pk)
    request_key = None
    if model:
        request_key = hashlib.sha256(json.dumps([message.pk, data], sort_keys=True, default=str).encode()).hexdigest()
        if ProjectLearningEvent.objects.filter(request_key=request_key).exists():
            return learning_data(project)
    revision = serializers.IntegerField(min_value=0).run_validation(data.get('revision'))
    if revision != state.revision:
        raise LearningConflict()
    action = data.get('action')
    event = {'reason': str(data.get('reason', ''))[:2000]}
    if action == 'plan':
        serializer = PlanSerializer(data=data.get('plan'))
        serializer.is_valid(raise_exception=True)
        plan = json.loads(json.dumps(serializer.validated_data, default=str))
        known_sources = {item['id'] for item in state.resources}
        if any(not set(stage['sources']).issubset(known_sources) for stage in plan['stages']):
            raise ValidationError('计划只能引用当前项目实际读取过的来源。')
        if _major(state.plan, plan) or (state.plan and data.get('major_change')):
            state.pending_plan = {'plan': plan, 'reason': event['reason'], 'base_revision': state.revision}
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
        event.update(observation=observation, feedback=feedback, assistance=assistance,
                     strategy=str(data.get('strategy', ''))[:2000], next_action=state.next_action, stage=stage)
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
