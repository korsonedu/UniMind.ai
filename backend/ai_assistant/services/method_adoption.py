"""Private task replies, method assignments and sourced observations."""
from datetime import datetime

from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError

from ai_assistant.models import (AIChatMessage, Conversation, LearningStrategyUse,
    TaskMemoryObject, TaskMemoryProgram)
from .teaching_sidecar import canonical_hash as digest


def _put(project, kind, identity, value, **authority):
    row, created = TaskMemoryObject.objects.get_or_create(owner_id=project.user_id,
        digest=digest([project.pk, kind, identity]), defaults={
            'project': project, 'kind': kind, 'value': value, **authority})
    return row, created


def apply_public(project, data, message):
    from .fact_evidence import active
    from .task_memory_store import preview
    if not active() or not message or not all(data.get(key) for key in ('reason', 'task_id', 'public_method_id', 'method_digest')):
        raise ValidationError('请在开启记忆的实际项目对话中说明方法适用原因。')
    task = get_object_or_404(project.learning_tasks, pk=data['task_id'])
    if message.user_id != project.user_id or message.role != 'user' or not Conversation.objects.filter(
            user_id=project.user_id, project=project, conversation_id=message.conversation_id).exists():
        raise ValidationError('方法采用不属于当前项目提问。')
    identity = [message.pk, str(task.pk), data.get('public_method_id')]
    previous = TaskMemoryObject.objects.filter(owner_id=project.user_id,
        digest=digest([project.pk, 'method_use', identity])).first()
    if previous:
        if previous.value['method_digest'] != data.get('method_digest') or previous.value['question_hash'] != digest(message.content):
            raise ValidationError('该轮方法采用的原始内容已变化。')
        return {**read_use(project, previous.digest), 'created': False}
    if AIChatMessage.objects.filter(user_id=project.user_id, role='assistant', bot_id=message.bot_id,
            conversation_id=message.conversation_id, metadata__learning_turn__message_id=message.pk,
            metadata__learning_turn__completed=True).exists():
        raise ValidationError('不能在本轮答复完成之后补记方法采用。')
    candidate = next((row for row in preview(project, project.user, task_id=task.pk)['packet']['public_methods']
        if row['method_id'] == data.get('public_method_id') and row['method_digest'] == data.get('method_digest')
        and row['binding']['task_id'] == str(task.pk)), None)
    if candidate is None:
        raise ValidationError('方法版本或当前任务条件已变化，请先重新读取。')
    value = {'method_id': candidate['method_id'], 'method_digest': candidate['method_digest'],
        'method_key': candidate['key'], 'task_id': str(task.pk), 'binding': candidate['binding'],
        'reason': data['reason'], 'assigned_at': timezone.now().isoformat(), 'question_hash': digest(message.content)}
    row, created = _put(project, 'method_use', identity, value, question=message, task=task)
    return {'use_id': row.digest, 'created': created, 'status': 'assigned',
            'instruction': candidate['instruction'], 'method_id': candidate['method_id'], 'adherence': 'unverified'}


def record_completion(reply):
    turn = reply.metadata['learning_turn']
    completed = datetime.fromisoformat(turn['completed_at'])
    if not timezone.is_aware(completed):
        return
    uses = TaskMemoryObject.objects.filter(owner_id=reply.user_id, kind='method_use',
        question_id=turn.get('message_id')).select_related('question', 'task__project')
    task_ids = set()
    for use in uses:
        q = use.question
        if (q.user_id != reply.user_id or q.role != 'user' or q.bot_id != reply.bot_id or q.conversation_id != reply.conversation_id
                or use.value['question_hash'] != digest(q.content)
                or completed < datetime.fromisoformat(use.value['assigned_at'])):
            continue
        value = {'use_digest': use.digest, 'reply_hash': digest(reply.content),
                 'completed_at': turn['completed_at'], 'saved_at': reply.timestamp.isoformat()}
        _put(use.task.project, 'method_reply', [use.digest, reply.pk], value,
            question=q, answer=reply, task=use.task)
        task_ids.add(str(use.task_id))
    record_task_reply(reply, task_ids)


def record_task_context(project, task, question):
    if not AIChatMessage.objects.filter(user_id=question.user_id, role='assistant',
            metadata__learning_turn__message_id=question.pk, metadata__learning_turn__completed=True).exists():
        _put(project, 'task_context', [question.pk, str(task.pk)],
            {'origin_version_id': task.knowledge_version_id}, question=question, task=task)


def record_task_reply(reply, task_ids):
    """Link a committed reply to its actual task context."""
    turn = reply.metadata['learning_turn']
    question = AIChatMessage.objects.filter(pk=turn['message_id'], user_id=reply.user_id,
        role='user', bot_id=reply.bot_id, conversation_id=reply.conversation_id).first()
    room = Conversation.objects.select_related('project').filter(user_id=reply.user_id,
        conversation_id=reply.conversation_id, project__user_id=reply.user_id).first()
    if not question or not room or not room.project_id:
        return
    task_ids.update(str(pk) for pk in TaskMemoryObject.objects.filter(owner_id=reply.user_id,
        project=room.project, kind='task_context', question=question).values_list('task_id', flat=True))
    activity = question.metadata.get('learning_activity') or {}
    if activity.get('kind') == 'task':
        task_ids.add(activity['task']['id'])
    cards = reply.metadata.get('dsh_cards', [])
    tasks = list(room.project.learning_tasks.filter(pk__in=task_ids))
    if not tasks:
        return
    value = {'question': question.content, 'reply': reply.content, 'cards': cards,
        'completed_at': turn['completed_at'], 'saved_at': reply.timestamp.isoformat(),
        'snapshot_hash': digest(question.metadata.get('learning_snapshot'))}
    artifact, _ = _put(room.project, 'reply_artifact', reply.pk, value, question=question, answer=reply)
    for task in tasks:
        _put(room.project, 'task_reply', [reply.pk, str(task.pk)],
            {'artifact': artifact.digest, 'artifact_hash': digest(artifact.value),
             'origin_version_id': task.knowledge_version_id}, question=question, answer=reply, task=task)


def task_reply_source(project, task=None):
    """Load task links and shared artifacts with their current source checks."""
    from .prism_memory import accessible
    from users.feature_access import has_learning_feature
    if not has_learning_feature(project.user, 'quiz.exam'):
        return {'links': [], 'artifacts': {}, 'unavailable': {}}
    query = TaskMemoryObject.objects.filter(owner=project.user, project=project, kind='task_reply')
    if task is not None:
        query = query.filter(task=task)
    records = list(query.select_related('question__user', 'question__bot', 'answer').order_by('answer__timestamp', 'answer_id', 'pk'))
    artifacts = {row.digest: row for row in TaskMemoryObject.objects.filter(owner=project.user,
        project=project, kind='reply_artifact', digest__in=[row.value['artifact'] for row in records])}
    rooms = set(Conversation.objects.filter(user=project.user, project=project).values_list('conversation_id', flat=True))
    links, kept, unavailable, permissions = [], {}, {}, {}
    for record in records:
        task_id = str(record.task_id)
        unavailable[task_id] = unavailable.get(task_id, 0) + 1
        artifact = artifacts.get(record.value['artifact'])
        if not artifact or digest(artifact.value) != record.value['artifact_hash']:
            continue
        question, reply = record.question, record.answer
        value = artifact.value
        permission = (question.user_id, question.role, question.bot_id, question.conversation_id,
                      digest(question.metadata.get('course_context')))
        if permission not in permissions:
            permissions[permission] = accessible(question)
        if (artifact.question_id != question.pk or artifact.answer_id != reply.pk
                or question.user_id != project.user_id or reply.user_id != project.user_id
                or question.role != 'user' or reply.role != 'assistant' or question.bot_id != reply.bot_id
                or question.conversation_id != reply.conversation_id or question.conversation_id not in rooms
                or not permissions[permission] or question.content != value['question'] or reply.content != value['reply']
                or reply.metadata.get('dsh_cards', []) != value['cards']
                or digest(question.metadata.get('learning_snapshot')) != value['snapshot_hash']
                or reply.metadata.get('learning_turn', {}).get('message_id') != question.pk
                or not reply.metadata['learning_turn'].get('completed')
                or reply.metadata['learning_turn'].get('completed_at') != value['completed_at']
                or reply.timestamp.isoformat() != value['saved_at']):
            continue
        unavailable[task_id] -= 1
        links.append({'source_id': record.digest, 'source_hash': digest(record.value),
            'question_id': question.pk, 'reply_id': reply.pk, 'task_id': task_id,
            'origin_version_id': record.value['origin_version_id'],
            'artifact_id': artifact.digest, 'artifact_hash': record.value['artifact_hash']})
        kept[artifact.digest] = value
    return {'links': links, 'artifacts': kept, 'unavailable': unavailable}


def render_task_replies(source, task_id):
    items = []
    for link in source['links']:
        if link['task_id'] != task_id:
            continue
        value = source['artifacts'][link['artifact_id']]
        items.append({**{key: link[key] for key in ('question_id', 'reply_id', 'task_id', 'origin_version_id')},
            **{key: value[key] for key in ('question', 'reply', 'cards', 'completed_at')},
            'relation': 'task_context', 'adherence': 'unverified', 'causal_claim': False})
    return {'task_id': task_id, 'items': items, 'total': len(items),
            'unavailable': source['unavailable'].get(task_id, 0), 'selection': 'all'}


def read_task_replies(project, task):
    return render_task_replies(task_reply_source(project, task), str(task.pk))


def select_task_replies(history, before_reply_id=None):
    items = history['items']
    if before_reply_id is not None:
        ids = [item['reply_id'] for item in items]
        if before_reply_id not in ids:
            raise ValidationError('该答复不在当前可读取的任务经历中，请重新读取原任务。')
        prior = items[:ids.index(before_reply_id)]
        selected = prior[-2:]
        cursor = selected[0]['reply_id'] if len(prior) > 2 else None
        selection = 'before_reply'
    else:
        selected = [items[0], items[-1]] if len(items) > 2 else items
        cursor = items[-1]['reply_id'] if len(items) > 2 else None
        selection = 'first_and_latest' if len(items) > 2 else 'all'
    return {**history, 'items': selected, 'selection': selection, 'next_before_reply_id': cursor}


def validate_task_reply_source(project, source):
    current = task_reply_source(project)
    links = {row['source_id']: row for row in current['links']}
    if (any(links.get(row['source_id']) != row for row in source['links'])
            or any(current['artifacts'].get(key) != value for key, value in source['artifacts'].items())):
        raise ValidationError('实际任务经历的来源已变化，该历史读出不可恢复。')


def qualify_diagnostic_outcomes(history, excluded, *, changed=None):
    """Apply or remove the one reason owned by diagnosis, leaving other source checks intact."""
    for use in history:
        if not use['outcomes'] or (changed is not None and use['task_id'] not in changed):
            yield use
            continue
        outcomes = []
        for outcome in use['outcomes']:
            reasons = [reason for reason in outcome['reasons'] if reason != 'same_instance_solution_disclosed']
            if use['task_id'] in excluded:
                index = reasons.index('source_unavailable') if 'source_unavailable' in reasons else len(reasons)
                reasons.insert(index, 'same_instance_solution_disclosed')
            outcomes.append({**outcome, 'reasons': reasons,
                             'status': 'uncertain' if reasons else 'independent_reported_observation'})
        state = use['status']
        if state != 'source_unavailable':
            state = 'outcome_uncertain' if any(row['reasons'] for row in outcomes) else 'outcome_observed'
        yield {**use, 'status': state, 'outcomes': outcomes}


def history_source(project, verified, tasks, catalogue, verified_versions, *, diagnostic_sources=None):
    from quizzes.models import ExamQuestionResult
    from .learning_tasks import task_prompt_hash
    from .prism_memory import accessible
    uses = list(TaskMemoryObject.objects.filter(owner_id=project.user_id, project=project,
        kind='method_use').select_related('question__user', 'question__bot', 'task').order_by('pk'))
    if not uses:
        return [], []
    from .learning_task_evidence import verified_task_events
    verified = list(verified)
    for version_id in {use.task.knowledge_version_id for use in uses} - set(verified_versions):
        verified.extend(verified_task_events(project, version_id)['events'])
    from . import learning_diagnostics
    if diagnostic_sources is None and learning_diagnostics.active():
        diagnostic_sources = learning_diagnostics.read_sources(project, {str(use.task_id) for use in uses})
    excluded = learning_diagnostics.excluded_tasks(diagnostic_sources or {})
    replies = {row.value['use_digest']: row for row in TaskMemoryObject.objects.filter(
        owner_id=project.user_id, project=project, kind='method_reply').select_related('answer').order_by('-pk')}
    versions = {row.pk: row for row in TaskMemoryProgram.objects.filter(
        pk__in=[use.value['method_id'] for use in uses], definition__family='unimind-teaching-v1')}
    current = {row['id'] for row in catalogue}
    task_rows = {row['id']: row for row in tasks}
    conversations = set(Conversation.objects.filter(user_id=project.user_id, project=project).values_list('conversation_id', flat=True))
    prior_ids, prior_prompts = {}, {}
    if verified:
        for row in ExamQuestionResult.objects.filter(exam__user_id=project.user_id).order_by('exam__created_at', 'pk').values(
                'pk', 'question_id', 'question_snapshot', 'exam__created_at'):
            key = (row['exam__created_at'], row['pk'])
            if row['question_id']:
                prior_ids.setdefault(row['question_id'], key)
            if row['question_snapshot'].get('text'):
                prior_prompts.setdefault(task_prompt_hash(row['question_snapshot']), key)
    private_uses = list(LearningStrategyUse.objects.filter(project=project).values_list('created_at', flat=True))
    history, referenced = [], {}
    for use in uses:
        if use.question.user_id != project.user_id or use.question.role != 'user' or use.task.project_id != project.pk:
            continue
        value = use.value
        version = versions.get(value['method_id'])
        available = bool(version and version.digest == value['method_digest'] == digest(version.definition))
        if available:
            referenced[version.pk] = {'id': version.pk, 'digest': version.digest, 'definition': version.definition}
        source_ok = (use.question.conversation_id in conversations and accessible(use.question)
                     and value['question_hash'] == digest(use.question.content))
        receipt = replies.get(use.digest)
        reply = receipt.answer if receipt else None
        receipt_ok = bool(reply and reply.user_id == project.user_id and reply.role == 'assistant'
            and reply.bot_id == use.question.bot_id and reply.conversation_id == use.question.conversation_id
            and receipt.value['reply_hash'] == digest(reply.content)
            and receipt.value['saved_at'] == reply.timestamp.isoformat()
            and reply.metadata.get('learning_turn', {}).get('completed')
            and reply.metadata['learning_turn'].get('message_id') == use.question_id
            and reply.metadata['learning_turn'].get('completed_at') == receipt.value['completed_at'])
        outcomes = []
        for event, task, result in verified:
            if str(task.pk) != value['task_id']:
                continue
            at = (result.exam.created_at, result.pk)
            prompt = task_prompt_hash(result.question_snapshot)
            repeated = prior_ids.get(result.question_id, at) < at or prior_prompts.get(prompt, at) < at
            timing = receipt_ok and result.exam.created_at > max(
                datetime.fromisoformat(receipt.value['completed_at']), reply.timestamp)
            assigned = datetime.fromisoformat(value['assigned_at'])
            overlap = any(assigned <= datetime.fromisoformat(other.value['assigned_at']) <= result.exam.created_at
                for other in uses if other.pk != use.pk and other.task_id == use.task_id)
            overlap = overlap or any(assigned <= stamp <= result.exam.created_at for stamp in private_uses)
            reasons = [reason for condition, reason in [
                (not timing, 'no_completed_prior_reply'), (task.assistance != 'independent', 'assistance_not_independent'),
                (repeated, 'repeated_question'), (overlap, 'registered_methods_overlap'),
                (not source_ok or not available, 'source_unavailable')] if condition]
            outcomes.append({'result_id': result.pk, 'event_id': event.pk, 'outcome': event.content['outcome'],
                'version_id': task.knowledge_version_id,
                'score': result.score, 'max_score': result.max_score, 'assistance': task.assistance,
                'status': 'uncertain' if reasons else 'independent_reported_observation',
                'reasons': reasons, 'at': result.graded_at.isoformat(), 'label_source': event.content['label_source']})
        state = 'outcome_observed' if outcomes and all(not row['reasons'] for row in outcomes) else (
            'outcome_uncertain' if outcomes else 'reply_completed' if receipt_ok else 'assigned')
        if not outcomes and task_rows.get(value['task_id'], {}).get('status') == 'completed':
            state = 'outcome_unavailable'
        if not source_ok or (receipt and not receipt_ok) or not available:
            state = 'source_unavailable'
        dependencies = {use.digest: digest(use.value)}
        if receipt:
            dependencies[receipt.digest] = digest(receipt.value)
        history.append({'use_id': use.digest, 'method_id': value['method_id'], 'method_digest': value['method_digest'],
            'method_key': value['method_key'], 'task_id': value['task_id'], 'reason': value['reason'],
            'status': state, 'outcomes': outcomes, 'distribution_current': value['method_id'] in current,
            'source_available': source_ok and available, 'question_id': use.question_id,
            'answer_id': receipt.answer_id if receipt else None, 'dependencies': dependencies})
    return list(qualify_diagnostic_outcomes(history, excluded, changed=excluded)), list(referenced.values())


def render_history(source):
    versions = {version['id']: version['definition'] for version in source['method_versions']}
    rows = source['method_history']
    if source['project'].get('method_history_selection') == 'pending-recent-v1':
        pending = {task['id'] for task in source['tasks'] if task['is_current'] and task['status'] != 'completed'}
        current, completed = {}, []
        for row in rows:
            if row['task_id'] in pending:
                current[row['task_id'], row['method_key']] = row
            else:
                completed.append(row)
        rows = [*current.values(), *completed[-5:]]
    return [{**{key: row[key] for key in ('use_id', 'method_id', 'method_digest', 'method_key', 'task_id',
        'reason', 'status', 'outcomes', 'distribution_current')},
        'instruction': versions.get(row['method_id'], {}).get('instruction', '') if row['source_available'] else '',
        'adherence': 'unverified', 'causal_claim': False} for row in rows]


def read_use(project, use_id=None, *, task_id=None):
    from .fact_evidence import active
    from .task_memory_projection import project_source
    if not active():
        raise ValidationError('当前未开启统一记忆。')
    if bool(use_id) == bool(task_id):
        raise ValidationError('请只提供采用编号或任务编号中的一项。')
    if task_id:
        task = get_object_or_404(project.learning_tasks, pk=task_id)
    source = project_source(project)
    if task_id:
        source['method_history'] = [row for row in source['method_history'] if row['task_id'] == str(task.pk)]
        source['project'].pop('method_history_selection', None)
        return {'uses': render_history(source)}
    source['method_history'] = [row for row in source['method_history'] if row['use_id'] == use_id]
    if not source['method_history']:
        raise ValidationError('这条方法采用当前不可读取。')
    return render_history(source)[0]
