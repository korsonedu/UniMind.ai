"""Trusted public method versions and evidence-conditioned private task bindings."""
import math

from django.db.models import Q
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from ai_assistant.models import TaskMemoryProgram

FAMILY = 'unimind-teaching-v1'


class Conditions(serializers.Serializer):
    topic = serializers.CharField(max_length=150, required=False)
    mode = serializers.ChoiceField(choices=['apply', 'transfer'], required=False)
    purpose = serializers.ChoiceField(choices=['diagnostic', 'practice', 'recheck'], required=False)
    min_independent_count = serializers.IntegerField(min_value=0, required=False)
    max_predicted_success = serializers.FloatField(min_value=0, max_value=1, required=False)
    min_stale_days = serializers.FloatField(min_value=0, required=False)
    max_weekly_minutes = serializers.IntegerField(min_value=1, required=False)


class Method(serializers.Serializer):
    key = serializers.RegexField(r'^[a-z0-9_-]{1,80}$')
    instruction = serializers.CharField(max_length=2000)
    requires = Conditions()
    source = serializers.CharField(max_length=3000)
    retired = serializers.BooleanField(default=False)


def publish_method(spec, *, request_key, project_id=None):
    """Trusted server publication only; no student text promotion or public API."""
    from ai_assistant.services.state.sdtm.task_memory_store import digest
    parser = Method(data=spec)
    parser.is_valid(raise_exception=True)
    if set(spec['requires']) - set(Conditions().fields):
        raise ValidationError('公共方法含未注册的条件。')
    data = parser.validated_data
    if not data['requires'] or any(isinstance(value, (int, float)) and not math.isfinite(value)
                                   for value in data['requires'].values()):
        raise ValidationError('公共方法需要明确、有限的适用条件。')
    definition = {'family': FAMILY, **data}
    if project_id is not None:
        definition['project_id'] = project_id
    row, _ = TaskMemoryProgram.objects.get_or_create(request_key=digest([FAMILY, request_key]),
        defaults={'definition': definition, 'digest': digest(definition)})
    if row.definition != definition or row.digest != digest(definition):
        raise ValidationError('发布编号已用于不同的方法内容。')
    return row


def catalogue(project_id=None):
    from ai_assistant.services.state.sdtm.task_memory_store import digest
    scope = Q(definition__project_id__isnull=True)
    if project_id is not None:
        scope |= Q(definition__project_id=project_id)
    latest = {}
    for row in TaskMemoryProgram.objects.filter(scope, definition__family=FAMILY).order_by('-pk'):
        latest.setdefault((row.definition.get('project_id'), row.definition['key']), row)
    visible = {}
    for (scope_id, key), row in latest.items():
        if not row.definition['retired'] and row.digest == digest(row.definition):
            if scope_id is not None or key not in visible:
                visible[key] = row
    return [{'id': row.pk, 'digest': row.digest, 'definition': row.definition}
            for row in sorted(visible.values(), key=lambda row: -row.pk)]


def validate_catalogue(versions):
    """Retirement affects new routing; deleted or altered sources deny historical replay."""
    from ai_assistant.services.state.sdtm.task_memory_store import digest
    rows = {row.pk: row for row in TaskMemoryProgram.objects.filter(
        pk__in=[version['id'] for version in versions], definition__family=FAMILY)}
    if any(version['id'] not in rows or rows[version['id']].digest != version['digest']
           or digest(rows[version['id']].definition) != version['digest']
           or ('definition' in version and rows[version['id']].definition != version['definition']) for version in versions):
        raise ValidationError('公共方法原始版本已删除或变化，历史读出不可恢复。')
    return [{'id': version['id'], 'digest': version['digest'], 'definition': rows[version['id']].definition}
            for version in versions]


def route(source, estimates):
    if source['project']['status'] != 'active':
        return []
    matches = []
    for task in source['tasks']:
        if not task['is_current'] or task['status'] != 'ready' or task['stage_id'] != source['project']['current_stage']:
            continue
        estimate = estimates.get(task['node_id'] + ':' + task['mode'], {})
        actual = {'topic': source['project']['concepts'].get(task['node_id']), 'mode': task['mode'],
                  'purpose': task['purpose'], 'min_independent_count': estimate.get('independent_count'),
                  'max_predicted_success': estimate.get('predicted_success'),
                  'min_stale_days': estimate.get('stale_days'),
                  'max_weekly_minutes': source['project']['plan'].get('weekly_minutes')}
        for version in source['public_methods']:
            rule = version['definition']
            def matches_condition(key, value):
                observed = actual[key]
                if observed is None:
                    return False
                return observed >= value if key.startswith('min_') else observed <= value if key.startswith('max_') else observed == value
            if all(matches_condition(key, value) for key, value in rule['requires'].items()):
                matches.append({'method_id': version['id'], 'method_digest': version['digest'],
                    'key': rule['key'], 'instruction': rule['instruction'], 'source': rule['source'],
                    'requires': rule['requires'], 'binding': {'task_id': task['id'], 'node_id': task['node_id'],
                    'conditions': {key: actual[key] for key in rule['requires']}}, 'status': 'matched_not_adopted'})
    return sorted(matches, key=lambda row: (-len(row['requires']), row['key'], row['binding']['task_id']))[:3]
