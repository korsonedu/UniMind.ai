"""Owned, versioned knowledge paths and auditable BEP observations."""
import hashlib
import json
from datetime import datetime
from uuid import uuid4

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from ai_assistant.models import (AIChatMessage, Conversation, LearningKnowledgeMap, LearningKnowledgeVersion,
    LearningResourceVersion, ProjectLearningEvent)
from .learning_library import _state
from .learning_resources import store_resource
from .project_learning import LearningConflict
from .bayesian_evidence import ALGORITHM_VERSION, belief


class CitationInput(serializers.Serializer):
    resource_id = serializers.IntegerField(min_value=1)
    revision = serializers.IntegerField(min_value=1)
    quote = serializers.CharField(min_length=8, max_length=500)


class NodeInput(serializers.Serializer):
    id = serializers.RegexField(r'^[a-zA-Z0-9_-]{1,60}$')
    title = serializers.CharField(max_length=150)
    outcome = serializers.CharField(max_length=500)
    prerequisites = serializers.ListField(child=serializers.CharField(max_length=60), max_length=15)
    citation = CitationInput()


class KnowledgeInput(serializers.Serializer):
    action = serializers.ChoiceField(choices=['search', 'read', 'save', 'prepare', 'probe'])
    query = serializers.CharField(max_length=200, required=False, allow_blank=True)
    map_id = serializers.IntegerField(min_value=1, required=False)
    revision = serializers.IntegerField(min_value=1, required=False)
    version_id = serializers.IntegerField(min_value=1, required=False)
    title = serializers.CharField(max_length=200, required=False)
    nodes = NodeInput(many=True, max_length=30, allow_empty=False, required=False)
    targets = serializers.ListField(child=serializers.CharField(max_length=60), min_length=1, max_length=30, required=False)
    depth = serializers.ChoiceField(choices=['apply', 'transfer'], required=False)
    node_id = serializers.CharField(max_length=60, required=False)
    mode = serializers.ChoiceField(choices=['apply', 'transfer'], required=False)
    question = serializers.CharField(min_length=8, max_length=2000, required=False)
    rubric = serializers.CharField(min_length=8, max_length=1500, required=False)


class PathInput(serializers.Serializer):
    version_id = serializers.IntegerField(min_value=1)
    targets = serializers.ListField(child=serializers.CharField(max_length=60), min_length=1, max_length=30)
    depth = serializers.ChoiceField(choices=['apply', 'transfer'])


class CheckInput(serializers.Serializer):
    probe_id = serializers.IntegerField(min_value=1)
    outcome = serializers.ChoiceField(choices=['success', 'failure', 'unclear'])
    quote = serializers.CharField(min_length=2, max_length=2000)
    reason = serializers.CharField(min_length=8, max_length=1500)


def owned_version(project, version_id):
    return get_object_or_404(LearningKnowledgeVersion.objects.select_related('knowledge_map'),
                            pk=version_id, knowledge_map__user=project.user)


def closure(snapshot, targets):
    nodes = {node['id']: node for node in snapshot['nodes']}
    selected = set()
    def visit(node_id):
        if node_id not in nodes:
            raise ValidationError('目标或前置节点不在这个知识版本中。')
        if node_id in selected:
            return
        selected.add(node_id)
        for parent in nodes[node_id]['prerequisites']:
            visit(parent)
    for node_id in targets:
        visit(node_id)
    return [node for node in snapshot['nodes'] if node['id'] in selected]


def validate_nodes(user, nodes):
    by_id = {node['id']: node for node in nodes}
    if len(by_id) != len(nodes):
        raise ValidationError('知识编号不能重复。')
    visiting, visited = set(), set()
    def visit(key):
        if key in visiting:
            raise ValidationError('前置关系存在环，请调整方向。')
        if key not in by_id:
            raise ValidationError('前置节点不存在。')
        if key in visited:
            return
        visiting.add(key)
        for parent in by_id[key]['prerequisites']:
            visit(parent)
        visiting.remove(key)
        visited.add(key)
    for node in nodes:
        visit(node['id'])
        citation = node['citation']
        source = get_object_or_404(LearningResourceVersion, resource__user=user,
            resource_id=citation['resource_id'], revision=citation['revision'], resource__is_archived=False)
        if citation['quote'] not in source.snapshot['excerpt']:
            raise ValidationError('知识引用必须是该资料版本实际读取片段中的原文。')
        citation.update(url=source.snapshot['url'], title=source.snapshot['title'], read_at=source.snapshot['read_at'])


def validate_path(project, state, plan):
    path = plan.get('knowledge_path')
    assigned = {key for stage in plan['stages'] for key in stage.get('knowledge_nodes', [])}
    if not path:
        if assigned:
            raise ValidationError('请先选择知识地图版本与目标。')
        return
    serializer = PathInput(data=path)
    serializer.is_valid(raise_exception=True)
    path = plan['knowledge_path'] = serializer.validated_data
    version = owned_version(project, path['version_id'])
    nodes = closure(version.snapshot, path['targets'])
    if assigned != {node['id'] for node in nodes}:
        raise ValidationError('阶段需覆盖所选目标及其全部前置节点，且不能超出范围。')
    positions = {}
    for index, stage in enumerate(plan['stages']):
        for node_id in stage.get('knowledge_nodes', []):
            positions.setdefault(node_id, index)
    if any(positions[parent] > positions[node['id']] for node in nodes for parent in node['prerequisites']):
        raise ValidationError('前置知识应安排在相同或更早的学习阶段。')
    for stage in plan['stages']:
        for node in nodes:
            if node['id'] not in stage.get('knowledge_nodes', []):
                continue
            citation = node['citation']
            if not any(source['id'] in stage['sources'] and source.get('library_id') == citation['resource_id']
                       and source.get('library_revision') == citation['revision'] for source in state.resources):
                raise ValidationError('请先 prepare，将该知识版本的实际来源接入阶段引用。')


def version_data(version):
    return {'version_id': version.pk, 'map_id': version.knowledge_map_id, 'revision': version.revision,
            'title': version.snapshot['title'], 'nodes': version.snapshot['nodes'],
            'relation_notice': '前置关系为教学建议；原文引用支持知识内容，关系尚未独立验证。'}


def _fingerprint(text):
    return hashlib.sha256(''.join(text.split()).casefold().encode()).hexdigest()


def presented(probe, answer):
    """Only a completed, matching assistant turn that actually contains this task."""
    replies = AIChatMessage.objects.filter(user=answer.user, bot=answer.bot, conversation_id=answer.conversation_id,
        role='assistant', timestamp__gt=probe.message.timestamp, timestamp__lt=answer.timestamp,
        metadata__learning_turn__message_id=probe.message_id, metadata__learning_turn__completed=True)
    question = ''.join(probe.content['question'].split())
    for reply in replies:
        completed_at = reply.metadata.get('learning_turn', {}).get('completed_at')
        if completed_at and datetime.fromisoformat(completed_at) < answer.timestamp and question in ''.join(reply.content.split()):
            return True
    return False


def validate_check(project, state, message, raw, stage, assistance):
    serializer = CheckInput(data=raw)
    serializer.is_valid(raise_exception=True)
    check = serializer.validated_data
    path = state.plan.get('knowledge_path', {})
    probe = get_object_or_404(ProjectLearningEvent, pk=check['probe_id'], project=project, kind='probe', message__isnull=False)
    if (probe.message_id == message.pk or probe.created_at >= message.timestamp or
            probe.content['version_id'] != path.get('version_id') or
            probe.content['node_id'] not in stage.get('knowledge_nodes', []) or
            probe.message.conversation_id != message.conversation_id or not presented(probe, message)):
        raise ValidationError('检查须在本项目实际呈现任务后，由同一对话后续另一轮回答提供依据。')
    if check['quote'] not in message.content:
        raise ValidationError('表现摘录必须来自当前用户的真实回答。')
    # One answer/probe and exact repeated answers cannot inflate accumulated evidence.
    prior = ProjectLearningEvent.objects.filter(project=project, kind='progress', content__knowledge_check__isnull=False)
    if prior.filter(content__knowledge_check__probe_id=probe.pk).exists() or prior.filter(message=message).exists():
        raise ValidationError('这个任务或这条回答已有检查记录，请安排新的独立任务。')
    answer_hash = _fingerprint(message.content)
    if prior.filter(content__knowledge_check__version_id=path['version_id'],
                    content__knowledge_check__node_id=probe.content['node_id'], content__knowledge_check__answer_hash=answer_hash).exists():
        raise ValidationError('重复的原回答不能作为新的独立证据。')
    return {**check, 'version_id': path['version_id'], 'node_id': probe.content['node_id'],
            'mode': probe.content['mode'], 'assistance': assistance, 'answer_hash': answer_hash,
            'algorithm': ALGORITHM_VERSION, 'question': probe.content['question'], 'rubric': probe.content['rubric']}


def knowledge_state(project, state, *, compact=False):
    path = state.plan.get('knowledge_path')
    if not path:
        return {'algorithm': ALGORITHM_VERSION, 'path': None, 'nodes': [], 'recommendations': [], 'probes': []}
    version = owned_version(project, path['version_id'])
    nodes = closure(version.snapshot, path['targets'])
    observations = {}
    evidence = []
    checks = ProjectLearningEvent.objects.filter(project=project, kind='progress', message__isnull=False,
        content__knowledge_check__version_id=version.pk).select_related('message').order_by('created_at', 'pk')
    checks = list(checks)
    probes_by_id = {probe.pk: probe for probe in ProjectLearningEvent.objects.filter(project=project, kind='probe',
        pk__in=[event.content['knowledge_check']['probe_id'] for event in checks], message__isnull=False).select_related('message')}
    excluded_count = 0
    for event in checks:
        check = event.content['knowledge_check']
        if check.get('algorithm') != ALGORITHM_VERSION:
            continue
        probe = probes_by_id.get(check['probe_id'])
        if not probe or check['quote'] not in event.message.content or not presented(probe, event.message):
            excluded_count += 1
            continue
        observations.setdefault((check['node_id'], check['mode']), []).append({**check, 'at': event.created_at.isoformat()})
        evidence.append({'event_id': event.pk, 'message_id': event.message_id, 'source': event.message.content[:2000], 'conversation_id': str(event.message.conversation_id),
            'at': event.created_at.isoformat(), **check})
    now = timezone.now()
    states = [{**node, 'beliefs': {mode: belief(observations.get((node['id'], mode), []), now) for mode in ('apply', 'transfer')}} for node in nodes]
    by_id = {node['id']: node for node in states}
    # Conservative routing heuristic, not a mastery gate or a calibrated probability threshold.
    def ready(node):
        estimate = node['beliefs']['apply']
        return estimate['independent_count'] >= 2 and estimate['interval'][0] >= .5
    recommendations = []
    for node in states:
        blockers = [parent for parent in node['prerequisites'] if not ready(by_id[parent])]
        if blockers:
            continue
        mode = 'transfer' if path['depth'] == 'transfer' and ready(node) else 'apply'
        estimate = node['beliefs'][mode]
        coverage = sum(node['id'] in {item['id'] for item in closure(version.snapshot, [target])} for target in path['targets']) / len(path['targets'])
        gap = 1 - estimate['mean']
        score = estimate['information_gain'] * (1 + coverage) * (1 + gap)
        recommendations.append({'node_id': node['id'], 'title': node['title'], 'mode': mode, 'score': round(score, 6),
            'information_gain': estimate['information_gain'], 'target_coverage': round(coverage, 3), 'gap': round(gap, 3),
            'reason': ('先了解常规应用表现' if mode == 'apply' else '已有常规独立证据，换情境检查候选迁移') +
                      ('；证据较早，安排重新检查' if estimate['stale_days'] and estimate['stale_days'] > 30 else '')})
    recommendations.sort(key=lambda row: (-row['score'], row['node_id']))
    used = {row['probe_id'] for row in evidence}
    probes = [{'id': event.pk, **event.content} for event in ProjectLearningEvent.objects.filter(project=project,
        kind='probe', message__isnull=False, content__version_id=version.pk).exclude(pk__in=used).order_by('-id')[:3]]
    result = {'algorithm': ALGORITHM_VERSION, 'version_id': version.pk, 'map_id': version.knowledge_map_id,
              'revision': version.revision, 'title': version.snapshot['title'], 'path': path, 'nodes': states,
              'recommendations': recommendations[:3], 'probes': probes,
              'excluded_evidence_count': excluded_count,
              'notice': '固定参数下的条件表现估计，尚未校准；不代表正式分数或真实掌握概率。迁移任务由小宇提出，尚未独立验证。'}
    if compact:
        result['nodes'] = [{'id': node['id'], 'title': node['title'], 'beliefs': node['beliefs']} for node in states]
    else:
        result['evidence'] = evidence[-20:][::-1]
    return result


@transaction.atomic
def knowledge_operation(project, arguments, *, message=None):
    serializer = KnowledgeInput(data=arguments)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    action = data['action']
    if action == 'search':
        rows = LearningKnowledgeMap.objects.filter(user=project.user, title__icontains=data.get('query', '')).order_by('-pk')[:20]
        return {'maps': [{'id': row.pk, 'title': row.title, 'revision': row.revision,
                         'versions': list(row.versions.order_by('-revision').values('id', 'revision', 'created_at')[:10])} for row in rows]}
    if action == 'read':
        return version_data(owned_version(project, data.get('version_id')))
    state = _state(project, message)
    if action == 'save':
        if not data.get('title') or not data.get('nodes'):
            raise ValidationError('请提供知识地图名称和带来源的知识单元。')
        validate_nodes(project.user, data['nodes'])
        if data.get('map_id'):
            row = get_object_or_404(LearningKnowledgeMap.objects.select_for_update(), user=project.user, pk=data['map_id'])
            if data.get('revision') != row.revision:
                raise LearningConflict('知识地图已更新，请读取最新版本。')
            snapshot = {'title': data['title'], 'nodes': data['nodes']}
            previous = row.versions.get(revision=row.revision)
            if previous.snapshot == snapshot:
                return version_data(previous)
            row.title, row.revision = data['title'], row.revision + 1
            row.save(update_fields=['title', 'revision'])
        else:
            # Retried same-turn saves return the existing immutable version.
            snapshot = {'title': data['title'], 'nodes': data['nodes']}
            key = hashlib.sha256(json.dumps([message.pk if message else None, project.pk, snapshot], sort_keys=True).encode()).hexdigest()
            old = ProjectLearningEvent.objects.filter(request_key=key).first()
            if old:
                return version_data(owned_version(project, old.content['version_id']))
            row = LearningKnowledgeMap.objects.create(user=project.user, title=data['title'])
        version = LearningKnowledgeVersion.objects.create(knowledge_map=row, revision=row.revision, snapshot=snapshot)
        ProjectLearningEvent.objects.create(project=project, message=message, kind='knowledge',
            content={'version_id': version.pk}, request_key=key if not data.get('map_id') else None)
        return version_data(version)
    if action == 'prepare':
        path_input = PathInput(data=data)
        path_input.is_valid(raise_exception=True)
        path = path_input.validated_data
        version = owned_version(project, path['version_id'])
        nodes = closure(version.snapshot, path['targets'])
        sources = {}
        for node in nodes:
            citation = node['citation']
            key = f"{citation['resource_id']}:{citation['revision']}"
            if key not in sources:
                original = get_object_or_404(LearningResourceVersion, resource__user=project.user,
                    resource_id=citation['resource_id'], revision=citation['revision'], resource__is_archived=False)
                snapshot = original.snapshot
                source = {k: snapshot[k] for k in ('url', 'title', 'excerpt', 'read_at', 'domain', 'topic', 'level', 'edition')}
                source.update(id=uuid4().hex, library_id=citation['resource_id'], library_revision=citation['revision'], pinned=True)
                sources[key] = store_resource(project, source)['resource']['id']
        state.refresh_from_db(fields=['resources'])
        if not set(sources.values()).issubset({source['id'] for source in state.resources}):
            raise ValidationError('项目来源空间不足，请缩小本次知识范围后重试。')
        return {'knowledge_path': path, 'nodes': nodes, 'sources': sources,
                'notice': '来源已接入，目标尚未改变；请在阶段计划中覆盖这些节点及来源，已有范围调整须用户确认。'}
    if action == 'probe':
        path = state.plan.get('knowledge_path', {})
        if not message or state.status != 'active' or data.get('node_id') not in {node['id'] for node in closure(owned_version(project, path.get('version_id')).snapshot, path.get('targets', []))}:
            raise ValidationError('检查须在正在学习的已选知识范围内登记。')
        if not data.get('mode') or not data.get('question') or not data.get('rubric'):
            raise ValidationError('请先登记任务、常规或候选迁移类型与具体判断标准。')
        content = {key: data[key] for key in ('node_id', 'mode', 'question', 'rubric')}
        content.update(version_id=path['version_id'], question_hash=_fingerprint(data['question']))
        old = ProjectLearningEvent.objects.filter(project=project, kind='probe', content__version_id=path['version_id'],
            content__node_id=data['node_id'], content__question_hash=content['question_hash']).first()
        if old:
            if old.message_id == message.pk:
                return {'probe_id': old.pk, **old.content}
            raise ValidationError('这道任务已登记过，请换一个实际任务，避免同题反复累计。')
        event = ProjectLearningEvent.objects.create(project=project, message=message, kind='probe', content=content)
        return {'probe_id': event.pk, **content, 'notice': '必须在本轮回复中原样呈现 question，成功回复后等待下一轮真实作答。'}
    raise ValidationError('不支持的知识操作。')
