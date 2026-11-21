"""Import a completed graph as an immutable, project-usable learning version."""
import hashlib
import json
import math
from collections import defaultdict

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from ai_assistant.models import LearningKnowledgeMap, LearningKnowledgeVersion, LearningResource, LearningResourceVersion
from knowledge_builder.views import _visible_builds

NOTICE = 'AI 生成的知识结构快照，尚未逐项核验教材依据；前置关系为教学建议。'


def available_builds(user):
    return _visible_builds(user).filter(status='COMPLETED').prefetch_related('blocks').order_by('-completed_at')


def prepare_build(project, data, state):
    from .learning_knowledge import closure, knowledge_operation
    from .project_learning import change_learning, LearningConflict

    if not state.planning_enabled:
        raise ValidationError('当前为自由对话，请在新建项目时选择规划模式后采用学习路径。')
    if data.get('revision') != state.revision:
        raise LearningConflict()
    build = get_object_or_404(available_builds(project.user), pk=data.get('build_id'))
    blocks = {block.pk: block for block in build.blocks.all()}
    selected = set(data.get('block_ids', []))
    if not selected or not selected.issubset(blocks):
        raise ValidationError('请选择该图谱中的目标学习块。')
    edges = list(build.block_edges.filter(is_retained=True))
    # Mutually dependent blocks form one learning unit, keeping the project path acyclic.
    groups = {pk: pk for pk in blocks}
    def root(pk):
        while groups[pk] != pk:
            pk = groups[pk]
        return pk
    for edge in edges:
        if edge.edge_kind == 'bidirectional':
            left, right = root(edge.from_block_id), root(edge.to_block_id)
            groups[max(left, right)] = min(left, right)
    members = defaultdict(list)
    for pk, block in blocks.items():
        members[root(pk)].append(block)
    parents = defaultdict(set)
    for edge in edges:
        left, right = root(edge.from_block_id), root(edge.to_block_id)
        if left != right and edge.edge_kind == 'unidirectional':
            parents[right].add(left)
    included = {root(pk) for pk in selected}
    pending = list(included)
    while pending:
        for parent in parents[pending.pop()] - included:
            included.add(parent)
            pending.append(parent)
    if len(included) > 30:
        raise ValidationError('本次范围包含超过 30 个学习单元，请缩小目标范围，分段开始。')
    ordered = []
    while len(ordered) < len(included):
        ready = sorted(pk for pk in included - set(ordered) if parents[pk].issubset(ordered))
        if not ready:
            raise ValidationError('图谱前置关系存在环，请修订结构后再采用。')
        ordered.extend(ready)
    nodes, texts = [], []
    for pk in ordered:
        rows = members[pk]
        title = ' / '.join(block.short_title for block in rows)[:150]
        outcome = '\n'.join(block.narrative_summary or block.short_title for block in rows)[:500]
        atoms = [{'id': item.atom_id, 'title': item.atom.name, 'outcome': item.atom.goal_statement,
                  'membership': item.membership_type, 'step': step.step_title}
                 for block in rows for step in block.steps.prefetch_related('step_atoms__atom').all()
                 for item in step.step_atoms.all()]
        text = f'{title}\n{outcome}' + ''.join(f"\n{atom['step']} · {atom['title']}：{atom['outcome']}" for atom in atoms)
        texts.append(text)
        nodes.append({'id': f'kb_{pk}', 'title': title, 'outcome': outcome,
                      'prerequisites': [f'kb_{parent}' for parent in sorted(parents[pk])],
                      'builder_block_ids': [block.pk for block in rows], 'builder_atoms': atoms, 'quote': text[:500]})
    origin = {'build_id': str(build.pk), 'completed_at': build.completed_at.isoformat() if build.completed_at else None,
              'block_ids': sorted(block.pk for group in included for block in members[group])}
    digest = hashlib.sha256(json.dumps([origin, nodes], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    old = LearningKnowledgeVersion.objects.filter(knowledge_map__user=project.user, snapshot__builder__fingerprint=digest).first()
    if old:
        version = old
    else:
        url = f'/xiaoyu/knowledge-builder/{build.pk}?snapshot={digest}'
        excerpt = NOTICE + '\n\n' + '\n\n'.join(texts)
        resource, _ = LearningResource.objects.get_or_create(user=project.user, url_hash=hashlib.sha256(url.encode()).hexdigest(),
            defaults={'url': url, 'title': build.subject[:200], 'excerpt': excerpt, 'read_at': timezone.now()})
        snapshot = {key: getattr(resource, key) for key in ('url', 'title', 'excerpt', 'domain', 'topic', 'level', 'edition')}
        snapshot.update(read_at=resource.read_at.isoformat(), source_kind='generated_graph', content_version=digest,
                        references=[], not_web_read=True)
        LearningResourceVersion.objects.get_or_create(resource=resource, revision=1, defaults={'snapshot': snapshot})
        for node in nodes:
            node['citation'] = {'resource_id': resource.pk, 'revision': 1, 'quote': node.pop('quote'),
                                'url': url, 'title': resource.title, 'read_at': snapshot['read_at'], 'source_kind': 'generated_graph'}
        mapping = LearningKnowledgeMap.objects.create(user=project.user, title=build.subject[:200])
        version = LearningKnowledgeVersion.objects.create(knowledge_map=mapping, revision=1,
            snapshot={'title': mapping.title, 'nodes': nodes, 'builder': {**origin, 'fingerprint': digest}, 'notice': NOTICE})
    targets = sorted({f'kb_{root(pk)}' for pk in selected})
    prepared = knowledge_operation(project, {'action': 'prepare', 'version_id': version.pk,
                                            'targets': targets, 'depth': data.get('depth', 'apply')})
    nodes = closure(version.snapshot, targets)
    # Keep the existing bounded stage interface; adjacent units can share one stage.
    chunk = math.ceil(len(nodes) / 20)
    stages = []
    for offset in range(0, len(nodes), chunk):
        units = nodes[offset:offset + chunk]
        stages.append({'id': f'kb_stage_{offset}', 'title': ' / '.join(node['title'] for node in units)[:200],
            'outcome': '\n'.join(node['outcome'] for node in units),
            'task': '结合已有表现了解起点，准备具体学习任务；完成后根据原作答决定继续、练习或回补。',
            'knowledge_nodes': [node['id'] for node in units],
            'prerequisites': [stages[-1]['id']] if stages else [], 'sources': list(prepared['sources'].values())})
    plan = {'goal': state.plan.get('goal') or project.instructions[:2000] or f'学习{build.subject}',
            'deadline': state.plan.get('deadline'), 'weekly_minutes': state.plan.get('weekly_minutes', 0),
            'stages': stages, 'knowledge_path': prepared['knowledge_path']}
    result = change_learning(project, {'action': 'plan', 'revision': state.revision, 'plan': plan,
        'require_confirmation': True, 'reason': '根据所选图谱目标与前置关系准备学习路径，确认后开始。'})
    result['href'] = f'/xiaoyu?project={project.pk}&learning_view=proposal'
    return result
