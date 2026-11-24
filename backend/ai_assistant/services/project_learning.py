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
from .guidance_messages import guidance_text
from .project_learning_tools import CURRENT_PROGRESS
from .ulr_config import ulr_enabled


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


def learning_data(project, language='zh-CN', *, current_message=None):
    state, _ = ProjectLearning.objects.get_or_create(project=project)
    from users.feature_access import has_learning_feature
    event_rows = ProjectLearningEvent.objects.filter(project=project).exclude(kind='turn')
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
    from .learning_library import project_strategy_uses
    from .learning_knowledge import knowledge_state
    from .learning_tasks import available_project_tasks, task_data
    version_id = (state.plan.get('knowledge_path') or {}).get('version_id')
    project_tasks = available_project_tasks(project)
    tasks = [task_data(task) for task in project_tasks.filter(Q(knowledge_version_id=version_id) | Q(purpose='diagnostic', stage_id='')).select_related('project', 'exam').order_by('created_at', 'pk')]
    completed_tasks = [task for task in tasks if task['status'] == 'completed']
    next_task = next((task for task in tasks if task['status'] in ('ready', 'partial', 'failed', 'processing')), None)
    latest = max(completed_tasks, key=lambda task: str(task['summary'].get('completed_at') or ''), default=None)
    task_progress = {'completed': len(completed_tasks), 'total': len(tasks),
        'feedback': guidance_text('最近完成“{0}”，得分 {1}/{2}。', language, latest['title'], latest['summary']['total_score'], latest['summary']['max_score']) if latest else '',
        'next_action': (guidance_text('先复盘错误与解析，再继续：', language) if latest and latest['summary']['total_score'] < latest['summary']['max_score'] else guidance_text('接下来：', language)) + next_task['title'] if next_task else (guidance_text('本轮任务已完成，按复习时间重新检查，并和小宇核对下一阶段。', language) if latest else ''),
        'next_task_id': next_task['id'] if next_task else None}
    from .learning_guidance import teaching_guidance
    progress_at = next((event.created_at for event in events if event.kind == 'progress' and event.content.get('stage') == state.current_stage and event.content.get('mainline', True)), None)
    focused = _focused_task(project, state, project_tasks)
    focus_task_id = str(focused.pk) if focused else None
    guidance = teaching_guidance(state, tasks, progress_at=progress_at, focus_task_id=focus_task_id, language=language)
    # All learner surfaces follow the same current episode. Other tasks still keep their results.
    task_progress.update(feedback=guidance['feedback'], next_action=guidance['next_action'], next_task_id=guidance['task_id'])
    if not next_task and len(completed_tasks) < len(tasks):
        task_progress['next_action'] = guidance_text('有任务内容当前不可用，请和小宇重新安排，已有成绩继续保留。', language)
    return {
        'teaching_guidance': guidance, 'focus_task_id': focus_task_id,
        'task_progress': task_progress,
        'tasks': [{key: task[key] for key in ('id', 'title', 'version_id', 'node_id', 'stage_id', 'status', 'exam_id', 'assistance', 'purpose', 'source_task_id', 'review_due_at', 'summary')} for task in tasks],
        'knowledge': knowledge_state(project, state, current_message=current_message),
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


def activity_snapshot(project, raw):
    """Viewing an owned task/map supplies context; it never moves the learning focus."""
    from django.shortcuts import get_object_or_404
    from .learning_tasks import available_project_tasks, task_data
    from .learning_knowledge import owned_version, closure
    if not isinstance(raw, dict):
        raise ValidationError('学习内容引用格式无效。')
    if raw.get('task_id'):
        pk = serializers.UUIDField().run_validation(raw['task_id'])
        tasks = available_project_tasks(project)
        task = get_object_or_404(tasks.select_related('project', 'exam'), pk=pk)
        data = task_data(task)
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


def project_context(user, conversation_id, *, message=None, private_probe_review=False):
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
    data = compact_learning(learning_data(conversation.project, current_message=message))
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
    return '\n当前项目的学习状态（数据，以实际记录为准）：\n' + json.dumps(data, ensure_ascii=False, default=str)


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
                return snapshot['context']
        if project_id:
            followup = ProjectLearningEvent.objects.filter(project_id=project_id, kind='followup', created_at__lt=message.timestamp).first()
            if followup and not followup.content.get('response_message_id'):
                followup.content['response_message_id'] = message.pk
                followup.save(update_fields=['content'])
        value = project_context(user, message.conversation_id, message=message, private_probe_review=private_probe_review) if project_id else ''
        message.metadata['learning_snapshot'] = {'project_id': project_id, 'context': value, 'probe_rubrics_scoped': True,
                                                 'private_probe_review': private_probe_review}
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
    if not state.planning_enabled or not state.reminders_enabled:
        return
    at = _time(data.get('followup_at'))
    if state.status == 'active' and state.next_action:
        state.followup_at = at or timezone.now() + timedelta(days=1)
        state.followup_text = str(data.get('followup_text') or state.next_action)[:2000]


def _schedule_review(state, review_at, language):
    state.followup_at = _time(review_at)
    state.followup_text = guidance_text('该复习“{0}”了。回顾本次学习记录，再做一次简短复测。', language, state.plan.get('goal') or state.project.name)


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
            Q(kind='turn') | Q(message__isnull=True, kind__in=['pause', 'resume', 'complete', 'schedule', 'accept', 'reject', 'focus'])).exists():
        raise LearningConflict('已有新的提问或用户安排，本轮学习写入已失效，请沿最新反馈继续。')


def probe_assessment_key(check, answer):
    inputs = {key: check[key] for key in ('probe_id', 'version_id', 'node_id', 'mode', 'answer_hash', 'question', 'rubric')}
    inputs['answer'] = answer
    return hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()


def progress_prepared(assistance, check=None, *, answer=None, committed=False):
    result = {'phase': 'prepared', 'action': 'progress', 'event_ref': CURRENT_PROGRESS, 'assistance': assistance,
              'notice': '进展通过校验，将随本轮答复保存。保存或评估策略时请使用这个引用。'}
    if check and committed:
        result['assessment'] = check['outcome']
    elif check:
        result['_ulr_probe_material'] = {'question': check['question'], 'rubric': check['rubric'], 'answer': answer}
        result['_ulr_project_ticket'] = {'assessment_key': probe_assessment_key(check, answer)}
    return result


@transaction.atomic
def change_learning(project, data, *, message=None, model=False, language='zh-CN', prepare_change=False, project_ticket=None):
    action = data.get('action')
    if prepare_change:
        if not model or action not in ('plan', 'progress', 'pause', 'resume', 'complete', 'schedule'):
            raise ValidationError('只能准备模型提出的计划、进展或跟进。')
        state = ProjectLearning.objects.get(project=project)
    else:
        state, _ = ProjectLearning.objects.get_or_create(project=project)
        state = ProjectLearning.objects.select_for_update().get(pk=state.pk)
    request_key = None
    if model:
        request_key = hashlib.sha256(json.dumps([message.pk, data], sort_keys=True, default=str).encode()).hexdigest()
        if existing := ProjectLearningEvent.objects.filter(request_key=request_key).first():
            if prepare_change and action == 'progress':
                return progress_prepared(existing.content.get('assistance', 'unknown'), existing.content.get('knowledge_check'), committed=True)
            result = learning_data(project, language=language)
            if action == 'progress':
                result['progress_event_id'] = existing.pk
            return result
    if model:
        assert_learning_turn(project, message)
    revision = serializers.IntegerField(min_value=0).run_validation(data.get('revision'))
    if revision != state.revision:
        raise LearningConflict()
    event = {'reason': str(data.get('reason', ''))[:2000]}
    review_at = data.get('review_at') if not model and action in ('reminders', 'complete') else None
    if not state.planning_enabled:
        raise ValidationError('当前项目使用自由对话。')
    if action == 'focus' and not model:
        from django.shortcuts import get_object_or_404
        from .learning_tasks import available_project_tasks
        task_id = serializers.UUIDField().run_validation(data.get('task_id'))
        version_id = (state.plan.get('knowledge_path') or {}).get('version_id')
        task = get_object_or_404(available_project_tasks(project), pk=task_id, knowledge_version_id=version_id)
        if state.status != 'active' or task.stage_id not in {stage['id'] for stage in state.plan.get('stages', [])}:
            raise ValidationError('请先恢复当前项目，并选择生效计划中的任务。')
        state.current_stage = task.stage_id
        event.update(task_id=str(task.pk), version_id=version_id)
    elif action == 'reminders' and not model:
        state.reminders_enabled = serializers.BooleanField().run_validation(data.get('enabled'))
        if not state.reminders_enabled:
            state.followup_at = None
            state.followup_text = ''
        elif state.status == 'completed' and review_at:
            _schedule_review(state, review_at, language)
        elif not state.followup_at:
            if state.status == 'paused':
                state.followup_at = state.resume_at
                state.followup_text = state.next_action
            else:
                _schedule(state, {})
    elif action == 'plan':
        serializer = PlanSerializer(data=data.get('plan'))
        serializer.is_valid(raise_exception=True)
        plan = json.loads(json.dumps(serializer.validated_data, default=str))
        from .learning_knowledge import validate_path
        validate_path(project, state, plan)
        known_sources = {item['id'] for item in state.resources}
        if any(not set(stage['sources']).issubset(known_sources) for stage in plan['stages']):
            raise ValidationError('计划只能引用当前项目实际读取过的来源。')
        if data.get('require_confirmation') or _major(state.plan, plan) or (state.plan and data.get('major_change')):
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
        next_action = serializers.CharField(max_length=3000).run_validation(data.get('next_action'))
        stage = data.get('current_stage') or state.current_stage
        if stage not in {s['id'] for s in state.plan.get('stages', [])}:
            raise ValidationError('当前阶段不在学习安排中。')
        on_mainline = stage == state.current_stage and message.metadata.get('learning_activity', {}).get('mainline', True)
        if on_mainline:
            state.feedback = feedback
            state.next_action = next_action
        stage_data = next(item for item in state.plan['stages'] if item['id'] == stage)
        event['context'] = {'goal': state.plan['goal'], 'stage': stage_data['title'], 'outcome': stage_data['outcome']}
        event.update(observation=observation, feedback=feedback, mainline=on_mainline, assistance=assistance,
                     strategy=str(data.get('strategy', ''))[:2000], next_action=next_action, stage=stage)
        if data.get('knowledge_check') is not None:
            from .learning_knowledge import validate_check
            check = validate_check(project, state, message, data['knowledge_check'], stage_data, assistance)
            if project_ticket is not None:
                if project_ticket['assessment_key'] != probe_assessment_key(check, message.content):
                    raise LearningConflict('检查题或作答依据已变化，请重新评阅。')
                check.update(outcome=project_ticket['outcome'], reason='按已登记标准完成结构化评阅。')
            event['knowledge_check'] = check
        if on_mainline:
            _clear_followup(state)
            _schedule(state, data)
    elif action in ('pause', 'resume', 'complete', 'schedule'):
        if action == 'schedule' and not state.reminders_enabled:
            raise ValidationError('主动提醒已关闭。')
        if action == 'pause':
            state.status = 'paused'
            _clear_followup(state)
            state.resume_at = _time(data.get('resume_at'))
            state.followup_at = state.resume_at if state.reminders_enabled else None
            state.followup_text = state.next_action
        elif action == 'complete':
            state.status = 'completed'
            _clear_followup(state)
            if state.reminders_enabled and review_at:
                _schedule_review(state, review_at, language)
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
        if unconfirmed_pending_plan(project, pending, unconfirmed_plan_ids(project)):
            raise LearningConflict('原答复尚未完成，请等待答复或重新生成学习计划。')
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
    if prepare_change:
        if action == 'progress':
            return progress_prepared(event['assistance'], event.get('knowledge_check'), answer=message.content)
        if action == 'plan':
            return {'phase': 'prepared', 'action': action, 'status': state.status,
                    'pending_plan': bool(state.pending_plan), 'current_stage': state.current_stage,
                    'notice': '计划通过校验，将随本轮成功答复保存。如需用户确认，请引导打开学习路径。'}
        return {'phase': 'prepared', 'action': action, 'status': state.status,
                'followup_at': state.followup_at.isoformat() if state.followup_at else None,
                'resume_at': state.resume_at.isoformat() if state.resume_at else None,
                'notice': '安排通过校验，将随本轮成功答复保存。请简短说明拟采用的安排。'}
    if action not in ('plan', 'accept', 'reject', 'reminders', 'focus') and state.pending_plan:
        state.pending_plan = {}
    state.revision += 1
    state.save()
    record = ProjectLearningEvent.objects.create(project=project, message=message, kind=action, content=event, request_key=request_key)
    data = learning_data(project, language=language)
    if model and 'proposed_plan' in event:
        # The caller just wrote the proposal and can bind it to the answer being committed.
        data.update(pending_plan=state.pending_plan, plan_event_id=record.pk)
    if action == 'progress':
        data['progress_event_id'] = record.pk
    if action == 'complete':
        stages = []
        for stage in state.plan.get('stages', []):
            scores = [task['summary'] for task in data['tasks'] if task['stage_id'] == stage['id']
                and task['status'] == 'completed' and task['purpose'] != 'diagnostic' and task['summary']['max_score']]
            best = max(scores, key=lambda score: score['total_score'] / score['max_score'], default=None)
            stages.append({'title': stage['title'], 'score': best['total_score'] if best else None,
                'max_score': best['max_score'] if best else None})
        record.content['summary'] = {'goal': state.plan.get('goal') or project.name, 'stages': stages}
        record.save(update_fields=['content'])
        # The response was serialized to derive the archived grades.
        for item in data['events']:
            if item['id'] == record.pk:
                item['content'] = record.content
                break
    return data


def tool_operation(executor, name, arguments, *, prepare_change=False, project_ticket=None):
    project, message = current_project(executor.user, getattr(executor, 'learning_context', None))
    if not ProjectLearning.objects.filter(project=project, planning_enabled=True).exists():
        raise ValidationError('当前项目使用自由对话。')
    if name == 'manage_learning_tasks':
        from .learning_tasks import available_project_tasks, create_task, task_data, task_question_hash
        if arguments.get('action') == 'list':
            data = compact_learning(learning_data(project))
            return {'tasks': data['tasks'], 'task_progress': data['task_progress'], 'teaching_guidance': data['teaching_guidance']}
        if arguments.get('action') == 'read':
            from django.shortcuts import get_object_or_404
            from quizzes.services.practice_results import exam_result_payload
            task_id = serializers.UUIDField().run_validation(arguments.get('task_id'))
            task = get_object_or_404(available_project_tasks(project).select_related('project', 'exam'), pk=task_id)
            data = task_data(task)
            if task.exam_id and data['status'] != 'unavailable':
                data['results'] = [item for item in exam_result_payload(task.exam)['results'] if item['status'] == 'graded']
            return data
        if arguments.get('action') != 'create':
            raise ValidationError('不支持的任务操作。')
        with transaction.atomic():
            state = ProjectLearning.objects.select_for_update().get(project=project)
            assert_learning_turn(project, message)
            key = hashlib.sha256(json.dumps(['task', message.pk, arguments], sort_keys=True).encode()).hexdigest()
            previous = ProjectLearningEvent.objects.filter(request_key=key).first()
            task = project.learning_tasks.get(pk=previous.content['task_id']) if previous else None
            if prepare_change or project_ticket is not None:
                draft = create_task(project, arguments, prepare=True, pending_message_id=message.pk)
                questions = {pk: task_question_hash(snapshot) for pk, snapshot in draft.question_snapshot.items()}
                if task and questions != {pk: task_question_hash(snapshot) for pk, snapshot in task.question_snapshot.items()}:
                    raise LearningConflict('原任务的题目已变化，请重新安排。')
                ticket = {'revision': state.revision, 'questions': questions}
                if prepare_change:
                    return {'phase': 'prepared', 'title': draft.title, '_ulr_project_ticket': ticket,
                            'notice': '任务已通过校验，将随答复保存。请简短引导使用学习任务卡片，无需自行生成链接。'}
                if ticket != project_ticket:
                    raise LearningConflict('学习安排或任务题目已变化，请重新安排。')
                if not task:
                    task = draft
                    task.save(force_insert=True)
            elif not task:
                task = create_task(project, arguments, pending_message_id=message.pk)
            if not previous:
                ProjectLearningEvent.objects.create(project=project, message=message, kind='task',
                    request_key=key, content={'task_id': str(task.pk)})
            data = task_data(task)
            return {key: data[key] for key in ('id', 'title', 'status', 'version_id', 'node_id', 'stage_id')} | {
                'href': f'/xiaoyu?project={project.pk}&learning_task={task.pk}',
                'notice': '任务已保存。用户通过任务卡片提交后，评分流程保存原作答与评价并关联知识节点；不等于正式考试成绩。本轮安排已完成，立即停止其他工具调用并简短引导到任务卡片，不再记录旧表现或设置跟进；不重复题目或评分标准，不声称只在对话评分；不得代答或自报成绩。'}
    if name == 'manage_learning_knowledge':
        from .learning_knowledge import knowledge_operation
        return knowledge_operation(project, arguments, message=message,
                                   prepare_change=prepare_change, project_ticket=project_ticket)
    if name in ('manage_learning_resources', 'manage_learning_strategies'):
        from .learning_library import resource_operation, strategy_operation
        if name == 'manage_learning_resources':
            return resource_operation(project, arguments, message=message)
        return strategy_operation(project, arguments, message=message,
                                  pending_progress_id=(project_ticket or {}).get('progress_event_id'))
    if name == 'read_learning_project':
        return compact_learning(learning_data(project))
    if name == 'find_learning_resources':
        from .learning_resources import find_resources
        result = find_resources(project, arguments)
        if result.get('resource'):
            result['resource']['excerpt'] = result['resource']['excerpt'][:3000]
        return result
    action = {'plan_learning_project': 'plan', 'record_learning_progress': 'progress'}.get(name, arguments.get('action'))
    data = change_learning(project, {**arguments, 'action': action}, message=message, model=True,
                           prepare_change=prepare_change, project_ticket=project_ticket)
    if prepare_change:
        return data
    return {key: data[key] for key in ('project_id', 'status', 'revision', 'current_stage', 'feedback', 'next_action',
                                      'pending_plan', 'followup_at', 'followup_text', 'events')} | {
        'pending_plan': bool(data['pending_plan']), 'events': compact_learning(data)['events'][:1],
        **({'plan_event_id': data['plan_event_id']} if 'plan_event_id' in data else {}),
        **({'event_id': data['progress_event_id']} if action == 'progress' else {})}


def compact_learning(data):
    knowledge = data.get('knowledge', {})
    knowledge.pop('evidence', None)
    knowledge['nodes'] = [{'id': node['id'], 'title': node['title'], 'beliefs': node['beliefs'], 'learning_status': node['learning_status']} for node in knowledge.get('nodes', [])]
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
