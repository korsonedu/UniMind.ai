"""L3 Decision Layer — project learning planning, scheduling, confirmation gates and tool operations.

Read-side L2 state assembly lives in `ai_assistant.services.state.project_state` and is
re-exported here for backwards compatibility.
"""
import hashlib
import json
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from ai_assistant.models import ProjectLearning, ProjectLearningEvent
from ai_assistant.services.runtime.project_learning_tools import CURRENT_PROGRESS
from ai_assistant.services.state.project_state import (
    LearningConflict,
    _focused_task,
    activity_snapshot,
    compact_learning,
    current_project,
    learning_data,
    message_receipts,
    model_event_reservation,
    model_learning_data,
    model_project_context,
    project_context,
    public_event_content,
    rank_task_methods,
    turn_project_context,
    unconfirmed_pending_plan,
    unconfirmed_plan_ids,
    unconfirmed_progress_ids,
)
from ai_assistant.services.views.guidance_messages import guidance_text


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
        from ai_assistant.services.facts.learning_tasks import available_project_tasks
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
        from ai_assistant.services.state.knowledge.learning_knowledge import validate_path
        validate_path(project, state, plan)
        known_sources = {item['id'] for item in state.resources}
        if any(not set(stage['sources']).issubset(known_sources) for stage in plan['stages']):
            raise ValidationError('计划只能引用当前项目实际读取过的来源。')
        if data.get('require_confirmation') or _major(state.plan, plan) or (state.plan and data.get('major_change')):
            state.pending_plan = {'plan': plan, 'reason': event['reason'], 'base_revision': state.revision}
            if plan.get('knowledge_path'):
                from ai_assistant.services.state.knowledge.learning_knowledge import owned_version
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
            from ai_assistant.services.state.knowledge.learning_knowledge import validate_check
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
        from ai_assistant.services.facts.learning_tasks import available_project_tasks, create_task, task_data, task_question_hash
        if arguments.get('action') == 'list':
            data = learning_data(project) if arguments.get('pending_only') else model_learning_data(project, executor.user)
            if arguments.get('pending_only'):
                data['tasks'] = [task for task in data['tasks'] if task['status'] != 'completed']
            result = {'tasks': data['tasks'], 'task_progress': data['task_progress'], 'teaching_guidance': data['teaching_guidance']}
            if data.get('memory_read'):
                result['memory_read'] = data['memory_read']
            from ai_assistant.services.state.sdtm.fact_evidence import active
            if active() and not arguments.get('pending_only'):
                from ai_assistant.services.facts.learning_tasks import task_index
                after = serializers.UUIDField().run_validation(arguments['after_task_id']) if 'after_task_id' in arguments else None
                result.update(task_index(project, query=arguments.get('query', ''), after_task_id=after))
            return result
        if arguments.get('action') == 'read':
            from django.shortcuts import get_object_or_404
            from quizzes.services.practice_results import exam_result_payload
            task_id = serializers.UUIDField().run_validation(arguments.get('task_id'))
            task = get_object_or_404(available_project_tasks(project).select_related('project', 'exam'), pk=task_id)
            data = task_data(task)
            if task.exam_id and data['status'] != 'unavailable':
                data['results'] = [item for item in exam_result_payload(task.exam)['results'] if item['status'] == 'graded']
            from ai_assistant.services.state.sdtm.fact_evidence import active
            if active() and data['status'] != 'unavailable':
                from ai_assistant.services.decision.method_adoption import read_task_replies, record_task_context, select_task_replies
                record_task_context(project, task, message)
                before = serializers.IntegerField(min_value=1).run_validation(arguments['before_reply_id']) if 'before_reply_id' in arguments else None
                data['reply_history'] = select_task_replies(read_task_replies(project, task), before)
                from ai_assistant.services.facts import learning_diagnostics
                if learning_diagnostics.active(project.pk):
                    sources = learning_diagnostics.read_sources(project, [str(task.pk)])
                    if sources:
                        data['diagnostic_support'] = learning_diagnostics.interpret(sources)[str(task.pk)]
                if data['is_current'] and data['status'] == 'ready':
                    from ai_assistant.services.state.sdtm.task_memory_store import preview
                    data['href'] = f'/xiaoyu?project={project.pk}&learning_task={task.pk}'
                    prepared = preview(project, project.user, task_id=task.pk)
                    data['public_methods'] = rank_task_methods(project, message, task.pk, prepared)
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
            from ai_assistant.services.state.sdtm.fact_evidence import active
            if active():
                from ai_assistant.services.decision.method_adoption import record_task_context
                record_task_context(project, task, message)
            return {key: data[key] for key in ('id', 'title', 'status', 'version_id', 'node_id', 'stage_id')} | {
                'href': f'/xiaoyu?project={project.pk}&learning_task={task.pk}',
                'notice': '任务已保存。用户通过任务卡片提交后，评分流程保存原作答与评价并关联知识节点；不等于正式考试成绩。本轮安排已完成，立即停止其他工具调用并简短引导到任务卡片，不再记录旧表现或设置跟进；不重复题目或评分标准，不声称只在对话评分；不得代答或自报成绩。'}
    if name == 'manage_learning_knowledge':
        from ai_assistant.services.state.knowledge.learning_knowledge import knowledge_operation
        return knowledge_operation(project, arguments, message=message,
                                   prepare_change=prepare_change, project_ticket=project_ticket)
    if name in ('manage_learning_resources', 'manage_learning_strategies'):
        from ai_assistant.services.facts.learning_library import resource_operation, strategy_operation
        if name == 'manage_learning_resources':
            return resource_operation(project, arguments, message=message)
        return strategy_operation(project, arguments, message=message,
                                  pending_progress_id=(project_ticket or {}).get('progress_event_id'))
    if name == 'read_learning_project':
        return model_learning_data(project, executor.user, current_message=message)
    if name == 'find_learning_resources':
        from ai_assistant.services.runtime.learning_resources import find_resources
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


__all__ = [
    'LearningConflict',
    'PlanSerializer',
    'StageSerializer',
    '_focused_task',
    'activity_snapshot',
    'assert_learning_turn',
    'change_learning',
    'compact_learning',
    'completed_learning_turn',
    'current_project',
    'learning_data',
    'message_receipts',
    'model_event_reservation',
    'model_learning_data',
    'model_project_context',
    'probe_assessment_key',
    'progress_prepared',
    'project_context',
    'public_event_content',
    'rank_task_methods',
    'tool_operation',
    'turn_project_context',
    'unconfirmed_pending_plan',
    'unconfirmed_plan_ids',
    'unconfirmed_progress_ids',
]
