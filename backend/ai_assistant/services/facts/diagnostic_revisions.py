"""Trusted, project-scoped transactions for reviewed text disclosure sources."""

from collections import defaultdict
from contextlib import closing
from itertools import batched

from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from ai_assistant.models import ConversationProject, TaskMemoryObject
from ai_assistant.services.learning_diagnostics import (BINDING, TEXT_DELIVERY, TEXT_STATE, _deliveries, _digest,
    ordered_deliveries, text_states, valid_binding)

REVISION = 'diagnostic_revision'


def _identity(project, request_key):
    return _digest([REVISION, project.pk, request_key])


def _boundary_pairs(project, watched, targets, now):
    """Check both interpretations against the same chronological source read."""
    before, after = {}, {}
    expected = sum(map(len, watched.values()))
    with closing(ordered_deliveries(project, watched, now).iterator(chunk_size=32)) as source:
        for batch in batched(source, 32):
            relevant = [row for row in batch if any(
                (row.value['instance'], decision) not in before or (row.value['instance'], decision) not in after
                for decision in watched[row.value['instance']]
                if row.kind != TEXT_DELIVERY or decision in row.value['decisions'])]
            verified = _deliveries(project, relevant, validate_activity=False)
            states = text_states(project, [row.digest for row in relevant if row.kind == TEXT_DELIVERY
                                           and row.digest in verified])
            for row in relevant:
                delivery = verified.get(row.digest)
                if not delivery:
                    continue
                instance = row.value['instance']
                current = states.get(row.digest, (True, None, False))[0]
                witness = (row.answer.timestamp, row.digest)
                for decision in watched[instance].intersection(delivery['decisions']):
                    if current:
                        before.setdefault((instance, decision), witness)
                    if targets.get(row.digest, current):
                        after.setdefault((instance, decision), witness)
            if len(before) == len(after) == expected:
                break
    return before, after


def bindings_in_window(project, instance, lower, upper):
    examined = Q(task__exam__user_id=project.user_id, task__exam__created_at__gt=lower)
    if upper is None:
        examined |= Q(task__exam__isnull=True)
    else:
        examined &= Q(task__exam__created_at__lte=upper)
    return TaskMemoryObject.objects.filter(examined, owner_id=project.user_id, project=project,
        task__project=project, kind=BINDING, value__instance=instance).select_related('task__exam')


def revision_impact(project, rows, targets, *, now):
    watched = defaultdict(set)
    for row in rows:
        if row.digest in targets:
            watched[row.value['instance']].update(row.value['decisions'])
    first, next_ = _boundary_pairs(project, watched, targets, now) if watched else ({}, {})
    witnesses, windows = [], defaultdict(dict)
    for instance, decision in sorted(first.keys() | next_.keys()):
        old, new = first.get((instance, decision)), next_.get((instance, decision))
        if old == new:
            continue
        witnesses.append({'instance': instance, 'decision': decision,
                          'before': [old[0].isoformat(), old[1]] if old else None,
                          'after': [new[0].isoformat(), new[1]] if new else None})
        old_at, new_at = old[0] if old else None, new[0] if new else None
        times = sorted(time for time in (old_at, new_at) if time is not None)
        if old_at != new_at:
            windows[instance, times[0], times[1] if len(times) == 2 else None][decision] = (
                new_at is not None and (old_at is None or new_at < old_at))

    submitted, pending = defaultdict(dict), defaultdict(dict)
    for (instance, lower, upper), changes in windows.items():
        for row in bindings_in_window(project, instance, lower, upper):
            if not valid_binding(project, row):
                continue
            exam = row.task.exam
            cutoff = min(now, exam.created_at) if exam else now
            if (exam and exam.user_id != project.user_id) or cutoff <= lower or (upper and cutoff > upper):
                continue
            affected = {decision: changes[decision] for decision in row.value['decisions'] if decision in changes}
            if affected:
                (submitted if exam else pending)[str(row.task_id)].update(affected)
    return {'as_of': now.isoformat(), 'witness_changes': witnesses,
            'submitted_tasks': dict(submitted), 'pending_tasks': dict(pending)}


@transaction.atomic
def revise_text_sources(project, *, request_key, changes=None, undo_of=None, now=None):
    """Commit a reviewed change or undo it if its sources have not changed again."""
    if (not isinstance(request_key, str) or not request_key.strip()
            or (changes is None) == (undo_of is None)):
        raise ValidationError('请提供唯一请求编号和来源更正或撤回编号。')
    if changes is not None and (not isinstance(changes, dict) or not changes
            or any(not isinstance(key, str) or type(value) is not bool for key, value in changes.items())):
        raise ValidationError('来源更正需要回执编号和启用状态。')
    project = ConversationProject.objects.select_for_update(
        no_key=connection.features.has_select_for_no_key_update).get(pk=project.pk, user_id=project.user_id)
    owned = TaskMemoryObject.objects.filter(owner_id=project.user_id, project=project)
    identity = _identity(project, request_key)
    intent = {'changes': changes, 'undo_of': undo_of}
    prior = owned.filter(kind=REVISION, digest=identity).first()
    if prior:
        if prior.value['intent'] != intent:
            raise ValidationError('同一请求编号已用于不同的更正。')
        return prior

    original = None
    if undo_of is not None:
        if not isinstance(undo_of, str) or not undo_of.strip():
            raise ValidationError('撤回编号无效。')
        original = owned.filter(kind=REVISION, digest=_identity(project, undo_of)).first()
        if original is None:
            raise ValidationError('没有找到可撤回的来源更正。')
        changes = {row['receipt']: row['before'] for row in original.value['changes']}
    source_rows = list(owned.filter(kind=TEXT_DELIVERY, digest__in=changes)
                       .select_related('question__bot', 'question__user', 'answer'))
    if len(source_rows) != len(changes):
        raise ValidationError('一个或多个正文披露回执不在当前项目中。')
    states = text_states(project, changes)
    if original and any(revision != original.digest for _, revision, _ in states.values()):
        raise ValidationError('来源在更正后又已变化，不能撤回旧操作。')

    transitions = []
    for key, target in sorted(changes.items()):
        current, _, permanently_withdrawn = states[key]
        if target and permanently_withdrawn:
            raise ValidationError('旧方式永久撤回的回执不能恢复。')
        if target != current:
            transitions.append({'receipt': key, 'before': current, 'after': target})
    enabling = {row['receipt'] for row in transitions if row['after']}
    if enabling and enabling != set(_deliveries(project, [row for row in source_rows if row.digest in enabling],
                                                 validate_activity=False)):
        raise ValidationError('待恢复的回执已无法核验。')

    impact = revision_impact(project, source_rows,
        {row['receipt']: row['after'] for row in transitions}, now=now or timezone.now())
    committed = TaskMemoryObject.objects.create(owner_id=project.user_id, project=project,
        kind=REVISION, digest=identity, value={'intent': intent, 'changes': transitions, 'impact': impact})
    for row in transitions:
        key = row['receipt']
        TaskMemoryObject.objects.update_or_create(owner_id=project.user_id,
            digest=_digest([TEXT_STATE, {'receipt': key}]),
            defaults={'project': project, 'kind': TEXT_STATE,
                      'value': {'receipt': key, 'active': row['after'], 'revision': committed.digest}})
    return committed
