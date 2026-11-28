"""Grounded semantic proposals and separately reviewed shared abstractions."""
import re

from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from ai_assistant.models import AIChatMessage, PrismEpisode, PrismMemory, PrismProposal
from ai_assistant.services.state.prism.prism_kernel import differentiate, digest, evaluate, induce, validate_splits


def previous_episode(question):
    return PrismEpisode.objects.filter(question__user=question.user,
        question__conversation_id=question.conversation_id, question__bot_id=question.bot_id,
        answer__user=question.user, answer__bot_id=question.bot_id, answer__role='assistant',
        answer__timestamp__lt=question.timestamp).select_related('question__user', 'question__bot', 'answer').order_by(
        '-answer__timestamp', '-id').first()


def propose_relations(question, observation):
    from ai_assistant.services.state.prism.prism_memory import accessible
    feedback = observation.get('feedback') or {}
    if feedback.get('kind') not in ('clarification', 'correction', 'extension') or not accessible(question):
        return []
    source = previous_episode(question)
    if not source or source.pk != observation.get('previous_episode_id') or not accessible(source.question):
        return []
    proposals = []
    for item in feedback.get('distinctions', [])[:3]:
        key, description = item.get('key', ''), item.get('description', '')
        source_quote, quote = item.get('source_evidence', ''), item.get('followup_evidence', '')
        if (not re.fullmatch('[a-z][a-z0-9_]{0,47}', key) or not 0 < len(description.strip()) <= 400
                or not source_quote.strip() or not quote.strip() or quote not in question.content
                or not (source_quote in source.question.content or source_quote in source.answer.content)
                or any(not isinstance(item.get(name), str) or not 0 < len(item[name]) <= 240
                       for name in ('source_value', 'followup_value'))
                or item['source_value'] == item['followup_value']):
            continue
        memory, _ = PrismMemory.objects.get_or_create(key=f'student:{question.user_id}:learning', defaults={
            'owner': question.user, 'scope': 'student', 'fields': [], 'active': False})
        if memory.owner_id != question.user_id or memory.scope != 'student' or key in memory.fields:
            continue
        proposal, _ = PrismProposal.objects.get_or_create(memory=memory, question=question,
            kind='relation', key=key, defaults={'source_episode': source, 'payload': {
                **item, 'feedback_kind': feedback['kind'], 'source_revision': memory.revision,
                'status': 'model_interpretation_not_verified'}})
        proposals.append(proposal.pk)
    return proposals


def _reviewer(memory, reviewer, *, shared=False):
    from users.permissions import is_platform_admin
    if not reviewer.is_active or (shared and not is_platform_admin(reviewer)):
        raise PermissionDenied('Shared memory publication requires a platform administrator.')
    if not shared and memory.owner_id != reviewer.pk and not is_platform_admin(reviewer):
        raise PermissionDenied('This memory belongs to another learner.')


def _sources(memory, cases):
    from ai_assistant.services.state.prism.prism_memory import accessible
    from ai_assistant.services.state.prism.prism_migration import validate_origin
    validate_origin(memory)
    ids = {case['source_message_id'] for case in cases if case.get('source_message_id')}
    rows = list(AIChatMessage.objects.filter(pk__in=ids, user_id=memory.owner_id).select_related('user', 'bot'))
    if len(rows) != len(ids) or any(not accessible(row) for row in rows):
        raise ValidationError('Reference evidence is unavailable or belongs to another learner.')


@transaction.atomic
def review_relation(proposal_id, reviewer, spec):
    from ai_assistant.services.state.prism.prism_memory import accessible, refine
    proposal = PrismProposal.objects.select_for_update().get(pk=proposal_id, kind='relation')
    proposal.memory = PrismMemory.objects.select_for_update().get(pk=proposal.memory_id)
    _reviewer(proposal.memory, reviewer)
    if (proposal.memory.scope != 'student' or not proposal.question or not proposal.source_episode
            or proposal.question.user_id != proposal.memory.owner_id
            or proposal.source_episode.question.user_id != proposal.memory.owner_id):
        raise ValidationError('A relation proposal must remain within its learner scope.')
    if proposal.status != 'pending':
        raise ValidationError('This proposal has already been reviewed.')
    if (not proposal.question or not proposal.source_episode or not accessible(proposal.question)
            or not accessible(proposal.source_episode.question)):
        raise ValidationError('The proposal source is no longer accessible.')
    train, validation = spec['training'], spec['validation']
    validate_splits(train, validation)
    _sources(proposal.memory, train + validation)
    if not all(proposal.key in case['features'] for case in train + validation):
        raise ValidationError('Reviewed cases must explicitly annotate the proposed distinction.')
    expected = spec.get('expected_revision', proposal.payload['source_revision'])
    regression_report = None
    if expected != proposal.payload['source_revision']:
        if expected != proposal.memory.revision:
            raise ValidationError('The requested rebase revision is not current.')
        regression = spec.get('regression', [])
        validate_splits(train, validation, regression)
        _sources(proposal.memory, regression)
        previous = {case['id']: case for case in proposal.memory.cases}
        if ({case['id'] for case in regression} != set(previous) or any(
                case['behavior'] != previous[case['id']]['behavior'] or any(
                    case['features'].get(key) != value for key, value in previous[case['id']]['features'].items())
                for case in regression)):
            raise ValidationError('Rebasing requires annotated regression cases preserving all current references.')
        fields = [*proposal.memory.fields, proposal.key]
        if any(not set(fields) <= set(case['features']) for case in train + validation + regression):
            raise ValidationError('Rebased references must annotate current fields and the new distinction.')
        preview = differentiate(train, validation, proposal.memory.fields, candidate_fields=[proposal.key])
        if preview['selected']:
            regression_report = evaluate(train, regression, preview['selected']['fields'])
            if regression_report['correct'] != len(regression):
                raise ValidationError('Rebased representation failed to retain current reference behavior.')
    report = refine(proposal.memory_id, expected, train, validation,
                    candidate_fields=[proposal.key], definition=proposal.payload['description'])
    proposal.status = 'accepted' if report['selected'] else 'rejected'
    proposal.review = {**report, 'spec_digest': digest(spec), 'reference_kind': 'reviewed_task_behavior'}
    if expected != proposal.payload['source_revision']:
        proposal.review.update(rebased_from=proposal.payload['source_revision'], reviewed_revision=expected,
                               regression=regression_report)
    proposal.reviewer = reviewer
    proposal.save(update_fields=['status', 'review', 'reviewer'])
    return proposal.review


@transaction.atomic
def propose_shared(memory_id, target_key, reviewer):
    memory = PrismMemory.objects.get(pk=memory_id, scope='student')
    _reviewer(memory, reviewer, shared=True)
    if not memory.active or not memory.cases or not memory.fields:
        raise ValidationError('Only an active reference memory can propose a shared abstraction.')
    _sources(memory, memory.cases)
    proposal, _ = PrismProposal.objects.get_or_create(memory=memory, kind='shared', question=None,
        key=digest([target_key, memory.revision]), defaults={'payload': {
            'source_revision': memory.revision, 'target_key': target_key,
            'status': 'requires_independent_public_references'}})
    return proposal


def _public_replay(spec):
    train, validation, test = [spec[key] for key in ('training', 'validation', 'test')]
    validate_splits(train, validation, test)
    if spec.get('public_system_cases') is not True:
        raise ValidationError('Explicitly reviewed public reference cases are required.')
    all_cases = train + validation + test
    if any(set(case) - {'id', 'verified', 'features', 'behavior', 'group'} for case in all_cases):
        raise ValidationError('Shared references cannot contain source IDs, quotes or private metadata.')
    if any(not isinstance(case.get('group'), str) or not case['group'].strip() for case in all_cases):
        raise ValidationError('Public replay requires annotated case-family groups.')
    groups = [{case['group'] for case in rows} for rows in (train, validation, test)]
    if groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2]:
        raise ValidationError('Public replay splits require disjoint, annotated case-family groups.')
    fields, definitions = spec['fields'], spec.get('definitions', {})
    if (not isinstance(fields, list) or not fields or len(fields) != len(set(fields))
            or not all(re.fullmatch('[a-z][a-z0-9_]{0,47}', field) for field in fields)
            or not all(set(fields) <= set(case['features']) for case in all_cases)
            or not isinstance(definitions, dict) or set(definitions) - set(fields)
            or any(not isinstance(value, str) or not 0 < len(value) <= 400 for value in definitions.values())):
        raise ValidationError('Public representation fields and definitions are invalid.')
    reports = {name: evaluate(train, rows, fields) for name, rows in (('validation', validation), ('test', test))}
    passed = all(report['wrong'] == 0 and report['correct'] > 0 for report in reports.values())
    return {'passed': passed, **reports, 'spec_digest': digest(spec)}, train


@transaction.atomic
def review_shared(proposal_id, reviewer, spec):
    proposal = PrismProposal.objects.select_for_update().get(pk=proposal_id, kind='shared')
    memory = PrismMemory.objects.select_for_update().get(pk=proposal.memory_id)
    _reviewer(memory, reviewer, shared=True)
    if proposal.status != 'pending' or memory.revision != proposal.payload['source_revision']:
        raise ValidationError('The shared proposal is reviewed or its source revision changed.')
    if not memory.active:
        raise ValidationError('The source memory has been disabled.')
    _sources(memory, memory.cases)
    report, training = _public_replay(spec)
    public_ids = {case['id'] for split in ('training', 'validation', 'test') for case in spec[split]}
    if public_ids & {case['id'] for case in memory.cases}:
        raise ValidationError('Shared validation must use references distinct from the personal source cases.')
    if not set(spec['fields']) <= set(memory.fields):
        raise ValidationError('A shared abstraction must retain relations from its source representation.')
    report['retained_fields'] = spec['fields']
    report['removed_field_count'] = len(set(memory.fields) - set(spec['fields']))
    if report['passed']:
        target = proposal.payload['target_key']
        if not isinstance(target, str) or not 0 < len(target) <= 160 or PrismMemory.objects.filter(key=target).exists():
            raise ValidationError('A new, bounded system memory key is required.')
        # The shared state comes exclusively from independently reviewed public
        # references. No private case, operator, definition or quotation is copied.
        shared = PrismMemory.objects.create(key=target, scope='system', owner=None,
            fields=spec['fields'], definitions=spec.get('definitions', {}), cases=training,
            operators=induce(training, spec['fields']))
        report['published_key'] = shared.key
    proposal.status = 'accepted' if report['passed'] else 'rejected'
    proposal.review, proposal.reviewer = report, reviewer
    proposal.save(update_fields=['status', 'review', 'reviewer'])
    return report
