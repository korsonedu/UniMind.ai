"""Interpret independently assessed decisions against certified, committed examples."""

from contextlib import closing
from itertools import batched

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError

from ai_assistant.models import Conversation, ConversationProject, ProjectLearning, TaskMemoryObject, TaskMemoryProgram
from users.feature_access import has_learning_feature
from ai_assistant.services.dsh_cards import build_learning_visual
from ai_assistant.services.state.prism.prism_memory import accessible
from ai_assistant.services.decision.public_methods import validate_catalogue

FAMILY = 'unimind-diagnostic-example-v1'
BINDING = 'diagnostic_task'
DELIVERY = 'diagnostic_delivery'
TEXT_DELIVERY = 'diagnostic_text'
TEXT_RETRACTION = 'diagnostic_retract'
TEXT_STATE = 'diagnostic_state'


def active(project_id=None):
    from ai_assistant.services.state.sdtm.fact_evidence import active as task_memory_active
    projects = settings.UNIMIND_SDTM_DIAGNOSTIC_PROJECTS
    return (task_memory_active() and settings.UNIMIND_SDTM_STRUCTURED_DIAGNOSTICS
            and (not projects or project_id is None or project_id in projects))


def _digest(value):
    from ai_assistant.services.state.sdtm.task_memory_store import digest
    return digest(value)


def _instance(schema, bindings):
    return _digest([schema, bindings])


def _task_source(task):
    return _digest([task.knowledge_version_id, task.node_id, task.definition, task.question_snapshot])


def certify_task(task, *, schema, bindings, decisions):
    """Called by trusted content adapters after authenticating the instance and assessment."""
    if len(task.question_snapshot) != 1:
        raise ValidationError('当前诊断绑定须对应一份单题任务。')
    value = {'instance': _instance(schema, bindings), 'decisions': sorted(set(decisions)),
             'task_source': _task_source(task)}
    row, _ = TaskMemoryObject.objects.get_or_create(
        owner_id=task.project.user_id, digest=_digest([BINDING, str(task.pk)]),
        defaults={'project_id': task.project_id, 'task': task, 'kind': BINDING, 'value': value},
    )
    if row.value != value:
        raise ValidationError('该任务已有不同的诊断定义。')
    return row


def register_example(card, *, schema, bindings, decisions, method_id, method_digest):
    """Publish an exact structured example from the trusted content side."""
    method = {'id': method_id, 'digest': method_digest}
    validate_catalogue([method])
    rendered = build_learning_visual(card)
    if rendered['type'] not in ('step_solution', 'latex_derivation'):
        raise ValidationError('当前仅支持受认证的解题卡片。')
    card_hash = _digest(rendered)
    definition = {'family': FAMILY, 'card_hash': card_hash, 'card': rendered, 'method': method,
                  'instance': _instance(schema, bindings), 'decisions': sorted(set(decisions))}
    program, _ = TaskMemoryProgram.objects.get_or_create(
        request_key=f'{FAMILY}:{card_hash}',
        defaults={'definition': definition, 'digest': _digest(definition)},
    )
    if program.definition != definition or program.digest != _digest(definition):
        raise ValidationError('该卡片已有不同的诊断定义。')
    return program


def select_example(user, chat_context, arguments):
    """Choose a certified card for an applicable method using current task commitments."""
    from ai_assistant.services.state.knowledge.learning_continuity import current_task_ids, definition_scope
    from ai_assistant.services.project_learning import current_project
    from ai_assistant.services.state.sdtm.task_memory_store import preview

    project, _ = current_project(user, chat_context)
    if not active(project.pk) or not has_learning_feature(user, 'quiz.exam'):
        raise PermissionDenied('当前账号无法读取学习任务。')
    payload = arguments['payload']
    task_id = serializers.UUIDField().run_validation(payload['task_id'])
    task_view = preview(project, user, task_id=task_id)['packet']
    method = next((entry for entry in task_view['public_methods'] if entry['method_id'] == payload['method_id']), None)
    if not method:
        raise ValidationError('公共方法当前不适用于该任务。')

    state = ProjectLearning.objects.get(project=project)
    version_id = (state.plan.get('knowledge_path') or {}).get('version_id')
    ready = project.learning_tasks.filter(exam__isnull=True).values('id', 'knowledge_version_id', 'stage_id', 'node_id')
    identities = [{**row, 'version_id': row['knowledge_version_id']} for row in ready]
    current = current_task_ids(state.plan, identities, definition_scope(project, version_id))
    bindings = _bindings(project, current)
    commitments = {}
    for binding in bindings.values():
        commitments.setdefault(binding.value['instance'], set()).update(binding.value['decisions'])
    examples = TaskMemoryProgram.objects.filter(definition__family=FAMILY, definition__method__id=method['method_id'],
        definition__method__digest=method['method_digest']).order_by('pk')
    for example in examples:
        value = example.definition
        if (_digest(value) == example.digest and _card_hash(value.get('card')) == value['card_hash']
                and not commitments.get(value['instance'], set()).intersection(value['decisions'])):
            return {'visual': build_learning_visual(value['card']), 'example_id': example.pk,
                    'unchecked_pending_tasks': len(current) - len(bindings)}
    raise ValidationError('当前没有可用且与已认证待办不冲突的解题卡片。')


def _card_hash(card):
    if isinstance(card, dict) and card.get('type') in ('step_solution', 'latex_derivation') and 'payload' in card:
        return _digest({'type': card['type'], 'payload': card['payload']})


def capture(question, answer):
    """Persist the exact committed card and its program in the original answer transaction."""
    cards = [(i, card_hash) for i, card in enumerate(answer.metadata.get('dsh_cards', ()))
             if (card_hash := _card_hash(card))]
    if not cards:
        return
    keys = [f'{FAMILY}:{card_hash}' for _, card_hash in cards]
    programs = TaskMemoryProgram.objects.in_bulk(keys, field_name='request_key')
    if not programs:
        return
    room = Conversation.objects.filter(user_id=question.user_id, conversation_id=question.conversation_id,
                                       project__user_id=question.user_id).first()
    if room is None or not active(room.project_id):
        return
    for index, card_hash in cards:
        program = programs.get(f'{FAMILY}:{card_hash}')
        if (program is None or program.definition.get('family') != FAMILY
                or program.definition.get('card_hash') != card_hash or _digest(program.definition) != program.digest):
            continue
        value = {'program_id': program.pk, 'program_digest': program.digest, 'card': index,
                 'instance': program.definition['instance']}
        TaskMemoryObject.objects.get_or_create(
            owner_id=question.user_id, digest=_digest([DELIVERY, answer.pk, value]),
            defaults={'project_id': room.project_id, 'kind': DELIVERY, 'value': value,
                      'question': question, 'answer': answer},
        )


def certify_text_delivery(task, question, answer, *, span, quote, decisions):
    """Bind a reviewed assertion in a completed reply to an assessed instance."""
    project = task.project
    binding = _bindings(project, [task.pk]).get(str(task.pk))
    decisions = sorted(set(decisions))
    start, end = span
    if (not binding or not decisions or not set(decisions) <= set(binding.value['decisions'])
            or not 0 <= start < end <= len(answer.content) or answer.content[start:end] != quote):
        raise ValidationError('正文披露引用或考查范围无效。')
    value = {'instance': binding.value['instance'], 'binding': binding.digest,
             'binding_hash': _digest(binding.value), 'span': [start, end], 'quote_hash': _digest(quote),
             'question_hash': _digest(question.content), 'reply_hash': _digest(answer.content),
             'at': answer.timestamp.isoformat(), 'decisions': decisions}
    receipt = TaskMemoryObject(owner_id=project.user_id, project=project, task=task,
        kind=TEXT_DELIVERY, question=question, answer=answer, value=value,
        digest=_digest([TEXT_DELIVERY, answer.pk, value]))
    if not _deliveries(project, [receipt]):
        raise ValidationError('正文披露没有可核验的已完成答复。')
    return TaskMemoryObject.objects.get_or_create(owner_id=project.user_id, digest=receipt.digest,
        defaults={'project': project, 'task': task, 'kind': TEXT_DELIVERY, 'question': question,
                  'answer': answer, 'value': value})[0]


@transaction.atomic
def retract_text_delivery(receipt):
    if receipt.kind != TEXT_DELIVERY:
        raise ValidationError('该记录不是正文披露回执。')
    ConversationProject.objects.select_for_update().get(pk=receipt.project_id, user_id=receipt.owner_id)
    value = {'receipt': receipt.digest}
    TaskMemoryObject.objects.get_or_create(owner_id=receipt.owner_id,
        digest=_digest([TEXT_RETRACTION, value]),
        defaults={'project_id': receipt.project_id, 'kind': TEXT_RETRACTION, 'value': value})


def text_states(project, sources):
    """Read current reviewed-source states, including legacy permanent withdrawals."""
    states = {key: (True, None, False) for key in sources}
    keys = {_digest([kind, {'receipt': key}]): (key, kind) for key in states
            for kind in (TEXT_STATE, TEXT_RETRACTION)}
    for row in TaskMemoryObject.objects.filter(owner_id=project.user_id, project=project,
            kind__in=(TEXT_STATE, TEXT_RETRACTION), digest__in=keys):
        key, kind = keys[row.digest]
        if row.kind != kind or row.value.get('receipt') != key:
            continue
        if kind == TEXT_RETRACTION and row.digest == _digest([kind, row.value]):
            states[key] = (False, row.digest, True)
        elif kind == TEXT_STATE and not states[key][2]:
            states[key] = (row.value['active'], row.value['revision'], False)
    return states


def _deliveries(project, rows, *, validate_activity=True):
    if not rows:
        return {}
    programs = TaskMemoryProgram.objects.in_bulk({row.value['program_id'] for row in rows if row.kind == DELIVERY})
    text = {row.digest: row for row in rows if row.kind == TEXT_DELIVERY}
    text_bindings, states = {}, {}
    if text:
        text_bindings = _bindings(project, {row.task_id for row in text.values()})
        if validate_activity:
            states = text_states(project, text)
    rooms = set(Conversation.objects.filter(project=project, user_id=project.user_id).values_list('conversation_id', flat=True))
    valid = {}
    methods, permissions = {}, {}
    for row in rows:
        question, reply = row.question, row.answer
        if (not question or not reply or question.user_id != project.user_id or reply.user_id != project.user_id
                or question.conversation_id not in rooms or reply.conversation_id != question.conversation_id
                or reply.bot_id != question.bot_id or reply.role != 'assistant' or question.role != 'user'
                or row.digest != _digest([row.kind, reply.pk, row.value])):
            continue
        permission = (question.conversation_id, question.bot_id, _digest(question.metadata.get('course_context')))
        if permission not in permissions:
            permissions[permission] = accessible(question)
        if not permissions[permission]:
            continue
        completed = reply.metadata.get('learning_turn', {})
        if not completed.get('completed') or completed.get('message_id') != question.pk:
            continue
        if row.kind == TEXT_DELIVERY:
            value = row.value
            binding = text_bindings.get(str(row.task_id))
            start, end = value['span']
            if ((not validate_activity or states[row.digest][0]) and row.question_id < row.answer_id
                    and question.timestamp <= reply.timestamp and binding and binding.digest == value['binding']
                    and _digest(binding.value) == value['binding_hash']
                    and binding.value['instance'] == value['instance']
                    and set(value['decisions']) <= set(binding.value['decisions'])
                    and value['at'] == reply.timestamp.isoformat()
                    and _digest(question.content) == value['question_hash']
                    and 0 <= start < end <= len(reply.content) and _digest(reply.content) == value['reply_hash']
                    and _digest(reply.content[start:end]) == value['quote_hash']):
                valid[row.digest] = {'at': reply.timestamp.isoformat(), 'reply_id': reply.pk, 'card': None,
                    'span': value['span'], 'decisions': value['decisions'], 'method': None}
            continue
        program = programs.get(row.value['program_id'])
        if (program is None or program.digest != row.value['program_digest'] or program.digest != _digest(program.definition)
                or program.definition.get('family') != FAMILY or program.definition['instance'] != row.value['instance']):
            continue
        cards = reply.metadata.get('dsh_cards', ())
        index = row.value['card']
        if index >= len(cards) or _card_hash(cards[index]) != program.definition['card_hash']:
            continue
        method = program.definition['method']
        method_key = (method['id'], method['digest'])
        if method_key not in methods:
            try:
                validate_catalogue([method])
            except ValidationError:
                methods[method_key] = False
            else:
                methods[method_key] = True
        if methods[method_key]:
            valid[row.digest] = {'at': reply.timestamp.isoformat(), 'reply_id': reply.pk, 'card': index,
                                 'decisions': program.definition['decisions'], 'method': method}
    return valid


def _bindings(project, task_ids):
    rows = TaskMemoryObject.objects.filter(owner_id=project.user_id, project=project, kind=BINDING,
                                           task_id__in=task_ids).select_related('task__exam')
    return {str(row.task_id): row for row in rows
            if valid_binding(project, row)}


def valid_binding(project, row):
    return (row.task is not None and row.task.project_id == project.pk
            and _task_source(row.task) == row.value['task_source']
            and row.digest == _digest([BINDING, str(row.task_id)]))


def ordered_deliveries(project, instances, cutoff):
    return TaskMemoryObject.objects.filter(owner_id=project.user_id, project=project,
        kind__in=(DELIVERY, TEXT_DELIVERY),
        value__instance__in=instances, answer__timestamp__lt=cutoff
    ).select_related('question__bot', 'question__user', 'answer').order_by('answer__timestamp', 'answer_id', 'pk')


def read_sources(project, task_ids, *, now=None):
    """Return only sources with an eligible temporal and diagnostic relation."""
    if not active(project.pk) or not task_ids or not has_learning_feature(project.user, 'quiz.exam'):
        return {}
    now = now or timezone.now()
    source, pending, cutoffs = {}, {}, {}
    for task_id, binding in _bindings(project, task_ids).items():
        exam = binding.task.exam
        if exam and exam.user_id != project.user_id:
            continue
        cutoff = min(now, exam.created_at) if exam else now
        assessed = binding.value['decisions']
        source[task_id] = {'binding': binding.digest, 'binding_hash': _digest(binding.value),
                           'assessed': assessed, 'as_of': cutoff.isoformat(), 'deliveries': {}}
        if assessed:
            cutoffs[task_id] = cutoff
            pending.setdefault(binding.value['instance'], {})[task_id] = set(assessed)
    if not pending:
        return source

    deliveries = ordered_deliveries(project, pending, max(cutoffs.values()))
    # Earliest verified support is enough for each decision. Keep reading while it is uncovered.
    with closing(deliveries.iterator(chunk_size=32)) as iterator:
        for batch in batched(iterator, 32):
            relevant = [row for row in batch if any(
                row.answer.timestamp < cutoffs[task_id]
                and (row.kind != TEXT_DELIVERY or remaining.intersection(row.value['decisions']))
                for task_id, remaining in pending.get(row.value['instance'], {}).items())]
            verified = _deliveries(project, relevant)
            for row in relevant:
                delivery = verified.get(row.digest)
                instance = row.value['instance']
                if not delivery or instance not in pending:
                    continue
                obligations = pending[instance]
                for task_id, remaining in tuple(obligations.items()):
                    if row.answer.timestamp >= cutoffs[task_id]:
                        del obligations[task_id]
                        continue
                    overlap = remaining.intersection(delivery['decisions'])
                    if overlap:
                        source[task_id]['deliveries'][row.digest] = delivery
                        remaining.difference_update(overlap)
                    if not remaining:
                        del obligations[task_id]
                if not obligations:
                    del pending[instance]
            if not pending:
                break
    return source


def excluded_tasks(source):
    # A scalar grade cannot recover which decisions the learner made independently.
    return {task_id for task_id, binding in source.items() if binding['deliveries']}


def interpret(source):
    """Read a live or frozen projection without rewriting assistance or marks."""
    result = {}
    for task_id, binding in source.items():
        deliveries = sorted(binding['deliveries'].values(),
                            key=lambda item: (item['at'], item['reply_id'], item['card'] is None,
                                              item.get('span', [item['card']])[0]))
        disclosed = set(binding['assessed']).intersection(
            decision for delivery in deliveries for decision in delivery['decisions'])
        result[task_id] = {'as_of': binding['as_of'], 'disclosed': sorted(disclosed),
            'status': 'disclosed' if disclosed else 'unknown',
            'coverage': 'certified_cards_and_text' if any('span' in item for item in deliveries) else 'certified_cards_only',
            'sources': [{'reply_id': item['reply_id'], 'card': item['card'], 'example_method': item['method'],
                         **({'span': item['span']} if 'span' in item else {})}
                        for item in deliveries]}
    return result


def validate_sources(project, source):
    if not has_learning_feature(project.user, 'quiz.exam'):
        raise ValidationError('当前权限无法恢复独立复查的历史证据。')
    bindings = _bindings(project, source)
    expected = {key: value for entry in source.values() for key, value in entry['deliveries'].items()}
    rows = list(TaskMemoryObject.objects.filter(owner_id=project.user_id, project=project,
        kind__in=(DELIVERY, TEXT_DELIVERY), digest__in=expected)
        .select_related('question__bot', 'question__user', 'answer'))
    if (_deliveries(project, rows) != expected or any(
            task_id not in bindings or bindings[task_id].digest != entry['binding']
            or _digest(bindings[task_id].value) != entry['binding_hash'] for task_id, entry in source.items())):
        raise ValidationError('独立复查的历史来源已删除或变化。')
