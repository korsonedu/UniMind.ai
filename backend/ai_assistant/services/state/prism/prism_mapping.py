"""Reviewed, finite-domain encoding equivalence for public relation memories."""
from django.db import transaction
from rest_framework.exceptions import ValidationError

from ai_assistant.models import PrismMemory, PrismProposal
from ai_assistant.services.state.prism.prism_kernel import digest, transfer, validate_splits


def memory_digest(memory):
    return digest([memory.fields, memory.definitions, memory.cases, memory.operators, memory.provenance])


def valid_mappings(memories):
    from ai_assistant.services.state.prism.prism_memory import checked_memories
    by_id = {memory.pk: memory for memory in memories}
    result = []
    for proposal in PrismProposal.objects.filter(kind='mapping', status='accepted', memory_id__in=by_id).order_by('id'):
        source, target = by_id[proposal.memory_id], by_id.get(proposal.payload['target_id'])
        if (not target or source.scope != 'system' or target.scope != 'system'
                or source.revision != proposal.payload['source_revision']
                or target.revision != proposal.payload['target_revision']
                or memory_digest(source) != proposal.payload['source_digest']
                or memory_digest(target) != proposal.payload['target_digest']):
            continue
        if len(list(checked_memories(None, [source, target]))) == 2:
            result.append((source, target, proposal))
    return result


@transaction.atomic
def review_mapping(source_id, target_id, reviewer, spec):
    from ai_assistant.services.state.prism.prism_feedback import _public_replay, _reviewer, _sources
    memories = {memory.pk: memory for memory in PrismMemory.objects.select_for_update().filter(
        pk__in=sorted([source_id, target_id])).order_by('pk')}
    source, target = memories[source_id], memories[target_id]
    _reviewer(source, reviewer, shared=True)
    if (source.pk == target.pk or any(memory.scope != 'system' or memory.owner_id is not None
            or not memory.active or len(memory.fields) != 1 for memory in (source, target))):
        raise ValidationError('Mapping requires two active, public single-relation memories.')
    if spec.get('source_revision') != source.revision or spec.get('target_revision') != target.revision:
        raise ValidationError('Mapping source or target revision changed.')
    for memory in (source, target):
        validate_splits(memory.cases)
        _sources(memory, memory.cases)
    source_field, target_field = source.fields[0], target.fields[0]
    report, training = _public_replay({**spec, 'fields': ['source_value', 'target_value'], 'definitions': {}})
    mapping = {}
    for case in training:
        before, after = case['features']['source_value'], case['features']['target_value']
        if before in mapping and mapping[before] != after:
            raise ValidationError('The proposed encoding is not a function.')
        mapping[before] = after
    if len(set(mapping.values())) != len(mapping):
        raise ValidationError('Relation encoding must be invertible.')
    if (set(mapping) != {case['features'][source_field] for case in source.cases}
            or set(mapping.values()) != {case['features'][target_field] for case in target.cases}):
        raise ValidationError('Bridge training must cover both reviewed value domains.')
    if source_field == target_field and any(value in mapping.values() and mapping[value] != value for value in mapping):
        raise ValidationError('Overlapping codes under the same field are ambiguous.')
    for name in ('training', 'validation', 'test'):
        for case in spec[name]:
            if set(case['features']) != {'source_value', 'target_value'}:
                raise ValidationError('A single-relation bridge cannot discard additional conditions.')
            before, after = case['features']['source_value'], case['features']['target_value']
            if mapping.get(before) != after:
                raise ValidationError('Held-out bridge does not preserve the learned encoding.')
            for memory, field, value in ((source, source_field, before), (target, target_field, after)):
                result = transfer(memory.cases, memory.fields, {field: value}, memory.operators)
                if result['status'] != 'matched' or result['behavior'] != case['behavior']:
                    raise ValidationError('Bridge behavior differs from a reviewed memory.')
    inverse = {value: key for key, value in mapping.items()}
    for before_memory, after_memory, value_map in ((source, target, mapping), (target, source, inverse)):
        for case in before_memory.cases:
            result = transfer(after_memory.cases, after_memory.fields,
                {after_memory.fields[0]: value_map[case['features'][before_memory.fields[0]]]}, after_memory.operators)
            if result['status'] != 'matched' or result['behavior'] != case['behavior']:
                raise ValidationError('Mapping fails bidirectional reference regression.')
    key = digest([target.pk, source.revision, target.revision])
    existing = PrismProposal.objects.filter(memory=source, kind='mapping', key=key).first()
    if existing:
        if existing.status != 'accepted' or existing.review['spec_digest'] != digest(spec):
            raise ValidationError('This mapping has already been reviewed with different references.')
        return existing
    active = valid_mappings(list(PrismMemory.objects.filter(scope='system', active=True)))
    if any(src.pk in (source.pk, target.pk) or dst.pk == source.pk for src, dst, _ in active):
        raise ValidationError('Mappings require one canonical target, without chains or cycles.')
    return PrismProposal.objects.create(memory=source, kind='mapping', key=key, status='accepted', reviewer=reviewer,
        payload={'target_id': target.pk, 'source_revision': source.revision, 'target_revision': target.revision,
                 'source_digest': memory_digest(source), 'target_digest': memory_digest(target),
                 'source_field': source_field, 'target_field': target_field, 'values': mapping},
        review={**report, 'passed': True, 'spec_digest': digest(spec), 'bidirectional_cases': len(source.cases) + len(target.cases),
                'bridge': {key: spec[key] for key in ('training', 'validation', 'test')}})


def memory_groups(user):
    from ai_assistant.services.state.prism.prism_memory import visible_memories
    memories = list(visible_memories(user))
    mappings = valid_mappings(memories)
    incoming, sources = {}, set()
    for source, target, proposal in mappings:
        incoming.setdefault(target.pk, []).append(proposal)
        sources.add(source.pk)
    return [(memory, incoming.get(memory.pk, [])) for memory in memories if memory.pk not in sources]


def mapped_frame(memory, mappings, frame):
    if not mappings:
        return frame, False
    target_field = memory.fields[0]
    domain = {case['features'][target_field] for case in memory.cases}
    if target_field in frame and frame[target_field] not in domain and not any(
            row.payload['source_field'] == target_field and frame[target_field] in row.payload['values'] for row in mappings):
        return frame, True
    choices = {frame[target_field]} if frame.get(target_field) in domain else set()
    by_field = {}
    for proposal in mappings:
        by_field.setdefault(proposal.payload['source_field'], []).append(proposal.payload['values'])
    for field, encodings in by_field.items():
        if field not in frame:
            continue
        value = frame[field]
        projected = {encoding[value] for encoding in encodings if value in encoding}
        if not projected and value in domain:
            projected = {value}  # Already-normalized value under an alias field.
        if not projected:
            return frame, True
        choices.update(projected)
    if len(choices) > 1:
        return frame, True
    return ({**frame, target_field: next(iter(choices))} if choices else frame), False


def mapping_version(mappings):
    return digest([[row.pk, row.payload, row.review['spec_digest']] for row in mappings]) if mappings else None
