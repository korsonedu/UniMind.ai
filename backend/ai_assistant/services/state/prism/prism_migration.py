"""Private legacy candidates, reviewed references and live source invalidation."""
from types import SimpleNamespace
from django.db import transaction
from django.db.models import Count
from rest_framework.exceptions import ValidationError

from ai_assistant.models import (AIChatMessage, AgentMemory, Experience, LearningStrategy,
    PrismMemory, PrismProposal, PrismRevision)
from ai_assistant.services.state.prism.prism_kernel import differentiate, digest, evaluate, induce, validate_splits


def source_snapshot(user, kind, source_id):
    from ai_assistant.services.state.prism.prism_memory import accessible
    if kind == 'experience':
        row = Experience.objects.select_related('trajectory__bot').filter(pk=source_id, user=user, status='active').first()
        if not row or not row.trajectory or row.trajectory.user_id != user.pk:
            raise ValidationError('Owned legacy trajectory unavailable.')
        if row.scope_type == 'student' and row.scope_value.get('student_id') != user.pk:
            raise ValidationError('Legacy student scope does not match its owner.')
        trajectory = row.trajectory
        texts = {item['content'] for item in trajectory.messages[-10:] if item.get('role') == 'user'
                 and isinstance(item.get('content'), str) and item['content'].strip()}
        if not texts:
            raise ValidationError('Legacy trajectory has no identifiable user evidence.')
        sources = list(AIChatMessage.objects.filter(user=user, bot=trajectory.bot,
            conversation_id=trajectory.conversation_id, role='user', content__in=texts,
            timestamp__lte=trajectory.created_at).select_related('user', 'bot'))
        if {item.content for item in sources} != texts:
            raise ValidationError('Legacy trajectory evidence is deleted or cannot be matched.')
        content = {'title': row.title, 'effect': row.effect, 'trigger': row.trigger,
                   'dimension': row.dimension, 'scope_type': row.scope_type, 'scope_value': row.scope_value,
                   'trajectory_id': trajectory.pk, 'trajectory_hash': digest(trajectory.messages)}
    elif kind == 'method':
        from ai_assistant.services.teaching_sidecar import method_snapshot
        row = LearningStrategy.objects.select_related('source_event__message__user', 'source_event__message__bot').filter(
            pk=source_id, user=user, is_retired=False, source_event__project__user=user).first()
        if not row or not row.source_event.message:
            raise ValidationError('Owned method source unavailable.')
        sources = [row.source_event.message]
        content = method_snapshot(row)
    else:
        raise ValidationError('Only experience and method sources are transferable candidates.')
    if any(item.user_id != user.pk or not accessible(item) for item in sources):
        raise ValidationError('Legacy evidence is outside current source permissions.')
    evidence = sorted((item.pk, digest(item.content)) for item in sources)
    origin = {'kind': kind, 'source_id': source_id, 'owner_id': user.pk,
              'fingerprint': digest([kind, source_id, content, evidence]),
              'source_message_ids': sorted(item.pk for item in sources)}
    return {'origin': origin, 'content': content}


def validate_origin(memory):
    if not memory.provenance:
        return
    origin = memory.provenance
    if memory.scope != 'student' or memory.owner_id != origin.get('owner_id'):
        raise ValidationError('Migrated evidence must remain private to its owner.')
    current = source_snapshot(memory.owner, origin['kind'], origin['source_id'])['origin']
    if current != origin:
        raise ValidationError('Legacy evidence changed; reviewed migration is stale.')


def inventory(user=None):
    facts, experiences, methods = AgentMemory.objects.all(), Experience.objects.all(), LearningStrategy.objects.all()
    if user:
        facts, experiences, methods = facts.filter(user=user), experiences.filter(user=user), methods.filter(user=user)
    return {'facts': facts.count(), 'automatic_experience_copies': facts.filter(source='auto', key__startswith='experience:').count(),
            'experience_counts': list(experiences.order_by().values('scope_type', 'status').annotate(count=Count('id'))),
            'methods': methods.count(), 'notice': 'Inventory is not verification or a migration approval.'}


@transaction.atomic
def stage(user, kind, source_id, reviewer):
    from ai_assistant.services.state.prism.prism_feedback import _reviewer
    _reviewer(SimpleNamespace(owner_id=user.pk), reviewer)
    source = source_snapshot(user, kind, source_id)
    key = f'student:{user.pk}:legacy:{kind}:{source_id}:{source["origin"]["fingerprint"][:16]}'
    memory, _ = PrismMemory.objects.get_or_create(key=key, defaults={
        'scope': 'student', 'owner': user, 'active': False, 'provenance': source['origin']})
    proposal, _ = PrismProposal.objects.get_or_create(memory=memory, kind='migration', question=None,
        key=source['origin']['fingerprint'], defaults={'payload': {
            'origin': source['origin'], 'source_revision': memory.revision, 'status': 'requires_reviewed_references'}})
    return proposal


@transaction.atomic
def review(proposal_id, reviewer, spec):
    from ai_assistant.services.state.prism.prism_feedback import _reviewer, _sources
    proposal = PrismProposal.objects.select_for_update().get(pk=proposal_id, kind='migration')
    memory = PrismMemory.objects.select_for_update().get(pk=proposal.memory_id)
    _reviewer(memory, reviewer)
    if proposal.status != 'pending' or memory.revision != proposal.payload['source_revision']:
        raise ValidationError('Migration was already reviewed or changed.')
    validate_origin(memory)
    if spec.get('reviewed_source_match') is not True:
        raise ValidationError('The reviewer must explicitly confirm source/reference semantic correspondence.')
    train, validation, test = [spec[key] for key in ('training', 'validation', 'test')]
    validate_splits(train, validation, test)
    _sources(memory, train + validation + test)
    groups = [{case.get('group') for case in split} for split in (train, validation, test)]
    source_ids = [{case['source_message_id'] for case in split if case.get('source_message_id')}
                  for split in (train, validation, test)]
    if any(not all(isinstance(group, str) and group.strip() for group in part) for part in groups) or any(
            groups[i] & groups[j] or source_ids[i] & source_ids[j] for i, j in ((0, 1), (0, 2), (1, 2))):
        raise ValidationError('Migration references require distinct case-family groups across splits.')
    fields = spec['fields']
    definitions = spec.get('definitions', {})
    if not fields or len(fields) != len(set(fields)) or not all(set(fields) <= set(case['features']) for case in train + validation + test):
        raise ValidationError('Reference representation is incomplete.')
    if not isinstance(definitions, dict) or any(key not in train[0]['features'] or not isinstance(value, str)
                                               or not 0 < len(value) <= 400 for key, value in definitions.items()):
        raise ValidationError('Reference relation definitions are invalid.')
    report = differentiate(train, validation, fields)
    selected = report['selected']['fields'] if report['selected'] else fields
    report['test'] = evaluate(train, test, selected)
    validation_report = report['selected']['report'] if report['selected'] else report['baseline']
    passed = all(result['wrong'] == 0 and result['correct'] > 0 for result in (validation_report, report['test']))
    report.update(passed=passed, spec_digest=digest(spec), test_use='one_shot_release_gate_not_field_selection')
    PrismRevision.objects.create(memory=memory, before={'fields': memory.fields, 'cases': memory.cases,
        'operators': memory.operators, 'revision': memory.revision, 'active': memory.active,
        'definitions': memory.definitions, 'provenance': memory.provenance}, report=report, accepted=passed)
    if passed:
        memory.fields, memory.cases = selected, train
        memory.definitions = {key: value for key, value in definitions.items() if key in selected}
        memory.operators, memory.active = induce(train, selected), True
        memory.revision += 1
        memory.save()
    proposal.status = 'accepted' if passed else 'rejected'
    proposal.review, proposal.reviewer = report, reviewer
    proposal.save(update_fields=['status', 'review', 'reviewer'])
    return report
