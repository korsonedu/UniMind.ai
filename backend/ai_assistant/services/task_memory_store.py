"""Durable, scoped source bindings; executable methods stay in trusted server code."""
from datetime import datetime
import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from ai_assistant.models import (ConversationProject, ProjectLearning, TaskMemoryFrame,
    TaskMemoryObject, TaskMemoryProgram, TaskMemoryState)
from users.feature_access import has_learning_feature
from . import bayesian_evidence
from . import learning_guidance
from . import public_methods
from . import method_adoption
from . import learning_continuity
from . import learning_diagnostics
from .task_memory_projection import project_source, project_view, task_packet

FAMILY = 'unimind-task-v1'
LEGACY_CODE = 'c127235660fff4054cf910a12533bfa81c631788bb1248548575300939b8f33d'
COMPATIBLE_CODES = (LEGACY_CODE, '5f7ba8d9c6e108cabd659387e25c8407094e498328eb72da827212a4554e7007',
    'd035afbcfb42361ddeda3cb501c829d2d148033aa4a07365fffa18f2a6888fe0',
    'ac5461852fb94d9b2987f2bca42b97827a25bef5f08cc548bcd5e3f93c2d2539',
    '0fe6b657568a2b906fd2105688a8298ade0208f2cff03d0a741e9bb6959a4544',
    '174699fc155aa6651e37c8ac7fae7f68cdd2426b6a8e98cfe4fb6e9fb52b205c',
    'eb7f89d658ae6b893b685cd35a5849c053f417118db2ffc310bfc88a1a54c06c',
    'fd679b676ffdddb3bcddf316bf2fc0ab8eaee9d619d7438ef43a153cb9ed5b66',
    '294e7c0e1dd74121d510550ac772f4007e4bd7cc174db238d3af9514445d4df5',
    'f9e9db0697566d75636b6aa3fbc31aa994a33ed2c932d6e78dfb39446f68e127',
    'ff5a61017adfd06c2999638acaadc775db1c44ea3022beb220688de69425eed1',
    '2ccde30b158b27e4e6b578d031a461aa2b3fe24050215fa68918cfc4942bca14')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _definition(threshold):
    if type(threshold) not in (int, float) or not 0 <= threshold <= 1:
        raise ValidationError('检查阈值需要处于0至1之间。')
    return {'family': FAMILY, 'code': CODE, 'threshold': threshold}


def _bootstrap():
    previous = TaskMemoryProgram.objects.filter(definition__family=FAMILY).order_by('-pk').first()
    if previous and previous.definition.get('code') == CODE:
        return previous
    threshold = .55
    if previous:
        if previous.definition.get('code') not in COMPATIBLE_CODES or previous.digest != digest(previous.definition):
            raise ValidationError('已有任务程序不可升级，请先核对其版本。')
        threshold = previous.definition['threshold']
        if previous.definition != {**_definition(threshold), 'code':previous.definition['code']}:
            raise ValidationError('旧任务程序包含未注册的字段，不能静默升级。')
    definition = _definition(threshold)
    return TaskMemoryProgram.objects.get_or_create(request_key='bootstrap:' + FAMILY + ':' + CODE,
        defaults={'definition': definition, 'digest': digest(definition)})[0]


def publish_policy(threshold, *, request_key):
    """Trusted server publication, not a model tool or public endpoint."""
    _bootstrap()
    definition = _definition(threshold)
    program, _ = TaskMemoryProgram.objects.get_or_create(request_key=request_key,
        defaults={'definition': definition, 'digest': digest(definition)})
    if program.definition != definition:
        raise ValidationError('重复的方法发布编号对应了不同内容。')
    return program


def _project(project, user):
    current = get_user_model().objects.filter(pk=user.pk, is_active=True).first()
    owned = ConversationProject.objects.filter(pk=project.pk, user=current).first() if current else None
    if owned is None:
        raise PermissionDenied('当前账号无法读取该项目记忆。')
    owned.user = current
    return owned


def estimate_groups(source, now, *, previous=None, dirty=None):
    groups = {}
    excluded = learning_diagnostics.excluded_tasks(source.get('diagnostic_support', {}))
    formal = [row for row in source['observations'] if row['task_id'] not in excluded]
    for row in sorted(formal + source.get('conversation_observations', []), key=lambda row: (row['at'], row['event_id'])):
        groups.setdefault(row['node_id'] + ':' + row['mode'], []).append(row)
    return {key: previous[key] if previous is not None and dirty is not None and key in previous and key not in dirty
            else bayesian_evidence.belief(rows, now) for key, rows in groups.items()}


def _run(source, program, now, *, estimates=None):
    definition = program.definition
    if definition.get('family') != FAMILY or definition.get('code') not in (CODE, *COMPATIBLE_CODES) or program.digest != digest(definition):
        raise ValidationError('该方法版本当前不可执行，不能以其他方法解释旧读出。')
    if definition != {**_definition(definition.get('threshold')), 'code':definition['code']}:
        raise ValidationError('方法载荷包含未注册的字段。')
    if 'evidence_continuity' in source:
        source = {**source, 'evidence_scope':learning_continuity.evidence_scope(source)}
    if source['project'].get('task_scope_schema') == 'exact-definition-v1':
        current = learning_continuity.current_task_ids(source['project']['plan'], source['tasks'], source['evidence_continuity'])
        source = {**source, 'tasks':[{**task, 'is_current':task['id'] in current} for task in source['tasks']]}
    if estimates is None:
        estimates = estimate_groups(source, now)
    packet = task_packet(project_view(source, estimates, definition['threshold']))
    if 'diagnostic_support' in source:
        visible_tasks = {row['id'] for row in packet['pending_tasks']}
        visible_tasks.update(row['task_id'] for row in packet['recent_formal_evidence'])
        packet['diagnostic_support'] = learning_diagnostics.interpret({
            task_id: value for task_id, value in source['diagnostic_support'].items() if task_id in visible_tasks})
    state = SimpleNamespace(**source['project'])
    progress_at = datetime.fromisoformat(state.progress_at) if state.progress_at else None
    packet['teaching_guidance'] = learning_guidance.teaching_guidance(state,
        [task for task in source['tasks'] if task['is_current']],
        progress_at=progress_at, focus_task_id=state.focus_task_id)
    return packet


def _bindings(project, source):
    objects = {}
    def put(kind, value, **authority):
        global_fact = kind in ('fact', 'facts', 'fact_list', 'teaching_catalog')
        scope = None if global_fact else project.pk
        key = digest({'scope': scope, 'kind': kind, 'value': value})
        objects[key] = TaskMemoryObject(owner_id=project.user_id, project_id=scope,
            digest=key, kind=kind, value=value, **authority)
        return key
    def collection(keys, kind='collection'):
        level = [put(kind, {'items': keys[i:i + 32]}) for i in range(0, len(keys), 32)] or [put(kind, {'items': []})]
        while len(level) > 1:
            level = [put(kind, {'children': level[i:i + 32]}) for i in range(0, len(level), 32)]
        return level[0]
    refs = {'project': put('project', source['project'])}
    if 'diagnostic_support' in source:
        refs['diagnostic_support'] = put('diagnostic_support', source['diagnostic_support'])
    if 'task_replies' in source:
        history = source['task_replies']
        refs['task_replies'] = put('reply_history', {'unavailable':history['unavailable'],
            'links':collection([put('episode_link', row, task_id=row['task_id'],
                question_id=row['question_id'], answer_id=row['reply_id']) for row in history['links']]),
            'artifacts':collection(list(history['artifacts']))})
    if 'evidence_continuity' in source:
        proof = source['evidence_continuity']
        refs['evidence_continuity'] = put('evidence_continuity', {**proof,
            'versions':{key:put('knowledge_definition', snapshot) for key,snapshot in proof['versions'].items()}})
    if 'public_methods' in source:
        refs['public_methods'] = put('teaching_catalog',[
            {key: method[key] for key in ('id', 'digest')} for method in source['public_methods']])
    if 'method_versions' in source:
        refs['method_versions'] = put('teaching_catalog',[
            {key: method[key] for key in ('id', 'digest')} for method in source['method_versions']])
    facts = source['facts']
    refs['facts'] = put('facts', {'version': facts['version'], 'items': collection([
        put('fact', row, fact_id=row['id'], question_id=row.get('source_message_id'))
        for row in facts['items']], 'fact_list'),
        **{key: value for key, value in facts.items() if key not in ('version', 'items')}})
    for name, kind in [('tasks', 'task'), ('observations', 'observation'),
                       ('conversation_observations', 'conversation'), ('replies', 'reply'),
                       ('method_history', 'method_history')]:
        keys = []
        for row in source.get(name, []):
            if name == 'method_history':
                row = {**row, 'dependencies':dict(row['dependencies'])}
                for outcome in row['outcomes']:
                    key = put('method_outcome',outcome,task_id=row['task_id'],
                        assessment_id=outcome['result_id'],event_id=outcome['event_id'])
                    row['dependencies'][key] = digest(outcome)
            authority = ({'task_id': row['id']} if name == 'tasks' else
                {'assessment_id': row['result_id'], 'task_id': row['task_id']} if name == 'observations' else
                {'event_id': row['event_id'], 'question_id': row['message_id'], 'answer_id': row['probe_message_id']} if name == 'conversation_observations' else
                {'question_id': row['question_id'], 'answer_id': row['answer_id'], 'task_id':row['task_id']} if name == 'method_history' else
                {'question_id': row['question_id'], 'answer_id': row['reply_id']})
            value = {key: value for key, value in row.items() if key != 'is_current'} if name == 'tasks' else row
            keys.append(put(kind, value, **authority))
        refs[name] = collection(keys)
    existing = set(TaskMemoryObject.objects.filter(owner_id=project.user_id,
        digest__in=objects).values_list('digest', flat=True))
    TaskMemoryObject.objects.bulk_create([row for key, row in objects.items() if key not in existing], ignore_conflicts=True)
    return refs


def lock_memory(project, user):
    # First write also serializes SQLite writers; PostgreSQL locks this memory row.
    TaskMemoryState.objects.filter(project=project).update(revision=F('revision'))
    memory, _ = TaskMemoryState.objects.get_or_create(project=project, defaults={'owner_id': project.user_id})
    memory = TaskMemoryState.objects.select_for_update().get(pk=memory.pk)
    project = _project(project, user)
    if memory.owner_id != project.user_id:
        raise PermissionDenied('项目记忆归属已变化。')
    return project, memory


def persist_readout(project, memory, source, packet, program, now):
    selected = {method['method_id'] for method in packet.get('public_methods', [])}
    source = {**source, 'public_methods': [m for m in source['public_methods'] if m['id'] in selected]}
    refs = _bindings(project, source)
    previous = TaskMemoryFrame.objects.filter(memory=memory).order_by('-revision').first()
    if previous and previous.program_id == program.pk and previous.source == refs and previous.occurred_at == now:
        frame = previous
    else:
        memory.revision += 1
        frame = TaskMemoryFrame.objects.create(memory=memory, revision=memory.revision, program=program,
            source=refs, occurred_at=now, packet_digest=digest(packet))
        memory.save(update_fields=['revision'])
    return {'packet': packet, 'frame_id': frame.pk, 'revision': frame.revision,
            'program_id': program.pk, 'program_digest': program.digest, 'observed_at': now.isoformat(),
            'task_access': has_learning_feature(project.user, 'quiz.exam')}


def prepare(project, user, *, now=None, expected_revision=None):
    project = _project(project, user)
    if isinstance(now, str):
        now = datetime.fromisoformat(now)
    with transaction.atomic():
        project, memory = lock_memory(project, user)
        state = ProjectLearning.objects.get(project=project)
        if expected_revision is not None and state.revision != expected_revision:
            from .project_learning import LearningConflict
            raise LearningConflict()
        _bootstrap()
        program = TaskMemoryProgram.objects.filter(definition__family=FAMILY).order_by('-pk').first()
        now = now or timezone.now()
        source = project_source(project, now=now)
        packet = _run(source, program, now)
        return persist_readout(project, memory, source, packet, program, now)


def preview(project, user, *, task_id=None):
    """Use the same method for a live tool read without nesting a memory write lock."""
    project = _project(project, user)
    task = get_object_or_404(project.learning_tasks, pk=task_id) if task_id is not None else None
    _bootstrap()
    program = TaskMemoryProgram.objects.filter(definition__family=FAMILY).order_by('-pk').first()
    now = timezone.now()
    source = project_source(project, now=now)
    if task is not None:
        source['tasks'] = [row for row in source['tasks'] if row['id'] == str(task.pk)]
    packet = _run(source, program, now)
    selected = {method['method_id'] for method in packet.get('public_methods', [])}
    source['public_methods'] = [method for method in source['public_methods'] if method['id'] in selected]
    return {'packet': packet, 'frame_id': None, 'revision': None, 'program_id': program.pk,
            'program_digest': program.digest, 'source_digest': digest(source),
            'observed_at': now.isoformat(),
            'task_access': has_learning_feature(project.user, 'quiz.exam')}


def restore(frame_id, user):
    frame = TaskMemoryFrame.objects.select_related('memory__project', 'program').get(pk=frame_id)
    project = _project(frame.memory.project, user)
    if frame.memory.owner_id != project.user_id:
        raise PermissionDenied('当前权限无法恢复该历史学习读出。')
    visible = TaskMemoryObject.objects.filter(owner_id=project.user_id).filter(Q(project=project) | Q(project__isnull=True))
    root_rows = list(visible.filter(digest__in=frame.source.values()))
    roots = {row.digest: row.value for row in root_rows}
    kinds = {row.digest: row.kind for row in root_rows}
    if len(roots) != len(set(frame.source.values())):
        raise ValidationError('原始来源已删除，该历史读出不可恢复。')
    source = {name: roots[key] for name, key in frame.source.items()}
    if 'public_methods' in source:
        source['public_methods'] = public_methods.validate_catalogue(source['public_methods'])
    if 'method_versions' in source:
        source['method_versions'] = public_methods.validate_catalogue(source['method_versions'])
    values = dict(roots)
    def load(keys):
        missing = set(keys) - set(values)
        for row in visible.filter(digest__in=missing):
            values[row.digest] = row.value
            kinds[row.digest] = row.kind
        if set(keys) - set(values):
            raise ValidationError('原始来源已删除，该历史读出不可恢复。')
    if 'evidence_continuity' in source:
        proof = source['evidence_continuity']
        load(proof['versions'].values())
        for key in [frame.source['evidence_continuity'], *proof['versions'].values()]:
            if key != digest({'scope':project.pk,'kind':kinds[key],'value':values[key]}):
                raise ValidationError('能力映射的原始定义已变化。')
        source['evidence_continuity'] = {**proof,
            'versions':{key:values[value] for key,value in proof['versions'].items()}}
    history_roots = [source['task_replies'][key] for key in ('links','artifacts')] if 'task_replies' in source else []
    load([source['facts']['items'], *history_roots])
    collections = ['tasks', 'observations', 'conversation_observations', 'replies']
    if 'method_history' in source:
        collections.append('method_history')
    frontier = [source['facts']['items'], *history_roots, *(frame.source[name] for name in collections)]
    while frontier:
        children = [child for key in frontier for child in values[key].get('children', values[key].get('items', []))]
        load(children)
        frontier = [key for key in children if kinds[key] in ('collection', 'fact_list')]
    def rows(key):
        value = values[key]
        if 'children' in value:
            return [row for child in value['children'] for row in rows(child)]
        return [values[child] for child in value['items']]
    source['facts'] = {**source['facts'], 'items': rows(source['facts']['items'])}
    fact_dependencies = {key for entry in source['facts'].get('resolution', {}).get('claims', [])
        for key in entry['evidence']}
    evidence = list(visible.filter(digest__in=fact_dependencies).select_related('question__user', 'question__bot'))
    if len(evidence) != len(fact_dependencies):
        raise ValidationError('个人事实的原始证据已删除，该历史读出不可恢复。')
    from .prism_memory import accessible
    from ai_assistant.models import Conversation
    conversations = set(Conversation.objects.filter(user=project.user).values_list('conversation_id', flat=True))
    if any(row.question_id and (not accessible(row.question) or row.question.conversation_id not in conversations)
            for row in evidence):
        raise PermissionDenied('当前权限无法读取个人事实的原始证据。')
    for name in collections:
        source[name] = rows(frame.source[name])
    if 'task_replies' in source:
        history = source['task_replies']
        links = rows(history['links'])
        source['task_replies'] = {'links':links, 'unavailable':history['unavailable'],
            'artifacts':{row['artifact_id']:values[row['artifact_id']] for row in links}}
        method_adoption.validate_task_reply_source(project, source['task_replies'])
    if 'task_scope' in source:
        current = set(source.pop('task_scope')['current'])
        for task in source['tasks']:
            task['is_current'] = task['id'] in current
    else:
        plan = source['project']['plan']
        version_id = (plan.get('knowledge_path') or {}).get('version_id')
        stages = {stage['id'] for stage in plan.get('stages', [])}
        for task in source['tasks']:
            if 'is_current' not in task:
                task['is_current'] = task['version_id'] == version_id and task['stage_id'] in stages
    dependencies = {key:value for use in source.get('method_history', []) for key,value in use['dependencies'].items()}
    method_evidence = list(visible.filter(digest__in=dependencies).select_related('question__user','question__bot','answer'))
    if len(method_evidence) != len(dependencies) or any(digest(row.value) != dependencies[row.digest] for row in method_evidence):
        raise ValidationError('方法采用的原始记录已删除或变化。')
    if any(row.question_id and (row.question.user_id != project.user_id or row.question.role != 'user'
           or not accessible(row.question) or row.question.conversation_id not in conversations
           or (row.answer_id and (row.answer.user_id != project.user_id or row.answer.role != 'assistant'
               or row.answer.bot_id != row.question.bot_id or row.answer.conversation_id != row.question.conversation_id)))
           for row in method_evidence):
        raise PermissionDenied('当前权限无法读取方法采用的原始提问。')
    if not has_learning_feature(project.user, 'quiz.exam') and (
            source['observations'] or any(task['summary'] is not None for task in source['tasks'])):
        raise PermissionDenied('当前权限无法恢复历史练习结果。')
    if 'diagnostic_support' in source:
        key = frame.source['diagnostic_support']
        if key != digest({'scope':project.pk,'kind':kinds[key],'value':source['diagnostic_support']}):
            raise ValidationError('独立复查的历史来源已变化。')
        learning_diagnostics.validate_sources(project, source['diagnostic_support'])
    packet = _run(source, frame.program, frame.occurred_at)
    if digest(packet) != frame.packet_digest:
        raise ValidationError('历史读出与已记录的方法和来源不一致。')
    return packet


def apply_projection(data, prepared):
    """Replace recency-truncated task state while retaining the surrounding product context."""
    packet = prepared['packet']
    permitted = prepared.get('task_access', True)
    pending = packet['pending_tasks'] if permitted else []
    data['tasks'] = pending
    current = [task for task in pending if task['stage_id'] == data['current_stage']]
    candidates = current or pending
    focused = next((task for task in candidates if task['id'] == data['focus_task_id']), None)
    first = (focused or candidates[0]) if candidates and packet['project']['status'] == 'active' else None
    action = ('继续当前待做任务：' + first['title']) if first else (
        '保留暂停状态，等待用户恢复。' if packet['project']['status'] == 'paused' else '核对实际完成记录，再决定后续安排。')
    if first and first['status'] == 'unavailable':
        action = '任务来源或权限当前不可用，先核对并重新安排任务。'
    elif first and first['status'] == 'processing':
        action = '等待当前评价完成，保留已有提交，不重复作答。'
    if not permitted:
        action = '当前无法读取练习任务与结果，保留既有计划并核对权限；不能据此判断任务已完成。'
    guidance = packet['teaching_guidance']
    if first and guidance['status'] in ('start', 'review'):
        guidance = {**guidance, 'status': 'continue', 'task_id': first['id'],
            'stage_id': first['stage_id'], 'next_action': action,
            'reason': '按当前有效任务保留未完成事项。'}
    if not permitted:
        guidance = {**guidance, 'task_id': None, 'next_action': action}
    data['task_progress'] = {'completed': packet['completed_tasks'] if permitted else None,
        'total': packet['completed_tasks'] + len(pending) if permitted else None, 'feedback': guidance['feedback'],
        'next_task_id': guidance['task_id'], 'next_action': guidance['next_action']}
    data['teaching_guidance'] = guidance
    for node in data.get('knowledge', {}).get('nodes', []):
        for mode in ['apply', 'transfer']:
            estimate = packet['estimates'].get(node['id'] + ':' + mode)
            if estimate is not None and permitted:
                node['beliefs'][mode] = estimate
    data['memory_read'] = {key: value for key, value in prepared.items() if key != 'packet'}
    data['memory_read']['context_adapter_digest'] = CONTEXT_CODE
    data['next_checks'] = packet['next_checks'] if permitted else []
    data['recent_formal_evidence'] = packet['recent_formal_evidence'] if permitted else []
    if 'public_methods' in packet:
        data['public_methods'] = packet['public_methods'] if permitted else []
    if 'method_history' in packet:
        data['method_history'] = packet['method_history'] if permitted else []
    if 'evidence_scope' in packet:
        data['evidence_scope'] = packet['evidence_scope'] if permitted else None
    if 'reply_history' in packet:
        data['reply_history'] = packet['reply_history'] if permitted else None
    if 'diagnostic_support' in packet:
        data['diagnostic_support'] = packet['diagnostic_support'] if permitted else {}
    if prepared.get('observed_at') and permitted:
        data['memory_observation'] = {'as_of': prepared['observed_at'],
            'fields': [key for key in ['tasks', 'task_progress', 'teaching_guidance',
                'next_checks', 'recent_formal_evidence', 'public_methods', 'method_history', 'evidence_scope',
                'reply_history', 'diagnostic_support'] if key in data]}
    return data


CODE = hashlib.sha256(('\n'.join(inspect.getsource(f) for f in [project_view, task_packet, _run, estimate_groups])
    + Path(bayesian_evidence.__file__).read_text() + Path(learning_guidance.__file__).read_text()
    + inspect.getsource(public_methods.route) + Path(method_adoption.__file__).read_text()
    + Path(learning_continuity.__file__).read_text()
    + '\n'.join(inspect.getsource(fn) for fn in (
        learning_diagnostics.interpret, learning_diagnostics.excluded_tasks))).encode()).hexdigest()
CONTEXT_CODE = hashlib.sha256(inspect.getsource(apply_projection).encode()).hexdigest()
