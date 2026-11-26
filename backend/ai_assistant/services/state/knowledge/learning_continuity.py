"""Reuse verified formal observations across exactly matching definitions."""
import hashlib
import json

from rest_framework.exceptions import ValidationError

ALGORITHM = 'exact-prerequisite-closure-v1'


def signatures(snapshot):
    nodes = {node['id']: node for node in snapshot['nodes']}
    cache = {}

    def visit(node_id):
        if node_id not in cache:
            node = nodes[node_id]
            definition = {key: value for key, value in node.items() if key != 'prerequisites'}
            value = [definition, sorted(visit(parent) for parent in node['prerequisites'])]
            cache[node_id] = hashlib.sha256(json.dumps(value, ensure_ascii=False,
                sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        return cache[node_id]

    return {node_id: visit(node_id) for node_id in nodes}


def definition_scope(project, version_id):
    from ai_assistant.models import LearningKnowledgeVersion
    from ai_assistant.services.state.knowledge.learning_knowledge import owned_version
    if version_id is None:
        return None
    target = owned_version(project, version_id)
    versions = {str(target.pk): target.snapshot}
    version_ids = project.learning_tasks.values_list('knowledge_version_id', flat=True).distinct()
    versions.update({str(row.pk): row.snapshot for row in LearningKnowledgeVersion.objects.filter(
        pk__in=version_ids, knowledge_map_id=target.knowledge_map_id).exclude(pk=target.pk)})
    return {'algorithm': ALGORITHM, 'target_version_id': target.pk, 'versions': versions}


def current_task_ids(plan, tasks, proof):
    target_id = (plan.get('knowledge_path') or {}).get('version_id')
    stages = {stage['id']: stage for stage in plan.get('stages', [])}
    if proof is not None and (proof['algorithm'] != ALGORITHM or proof['target_version_id'] != target_id):
        raise ValidationError('任务范围与当前知识定义不一致。')
    definitions = {key: signatures(value) for key, value in proof['versions'].items()} if proof else {}
    target = definitions.get(str(target_id), {})
    current = set()
    for task in tasks:
        stage = stages.get(task['stage_id'])
        if stage is None:
            continue
        node = task['node_id']
        if task['version_id'] == target_id or (node in stage.get('knowledge_nodes', []) and node in target
                and definitions.get(str(task['version_id']), {}).get(node) == target[node]):
            current.add(str(task['id']))
    return current


def formal_observations(project, version_id):
    from ai_assistant.services.facts.learning_task_evidence import formal_observations as verified_observations
    from ai_assistant.services.learning_tasks import task_prompt_hash

    current, checked = verified_observations(project, version_id)
    checked['verified_versions'] = [version_id]
    if version_id is None:
        return current, checked, None
    proof = definition_scope(project, version_id)
    target_keys = signatures(proof['versions'][str(version_id)])
    candidates = list(current)
    for origin_id, snapshot in sorted(proof['versions'].items(), key=lambda row: int(row[0])):
        if int(origin_id) == version_id:
            continue
        old, provenance = verified_observations(project, int(origin_id))
        checked['events'].extend(provenance['events'])
        checked['verified_versions'].append(int(origin_id))
        checked['excluded_provenance'] += provenance['excluded_provenance']
        checked['repeated_questions'] += provenance['repeated_questions']
        origin_keys = signatures(snapshot)
        matched = [row for row in old if row['node_id'] in target_keys
                   and origin_keys[row['node_id']] == target_keys[row['node_id']]]
        candidates.extend(matched)
    seen, rows = set(), []
    for row in sorted(candidates, key=lambda value: (value['at'], value['result_id'])):
        keys = {(row['node_id'], 'question', row['question_hash']),
                (row['node_id'], 'prompt', task_prompt_hash({'text': row['question']}))}
        if keys.intersection(seen):
            checked['repeated_questions'] += 1
            continue
        seen.update(keys)
        rows.append(row)
    return rows, checked, proof


def evidence_scope(source):
    proof = source['evidence_continuity']
    target_id = (source['project']['plan'].get('knowledge_path') or {}).get('version_id')
    if proof['algorithm'] != ALGORITHM or proof['target_version_id'] != target_id:
        raise ValidationError('历史观察的能力映射版本不一致。')
    definitions = {key: signatures(value) for key, value in proof['versions'].items()}
    target = definitions.get(str(target_id), {})
    for row in source['observations']:
        node_id = row['node_id']
        if node_id not in target or definitions.get(str(row['version_id']), {}).get(node_id) != target[node_id]:
            raise ValidationError('历史观察与当前能力定义不一致。')
    old = [row for row in source['observations'] if row['version_id'] != target_id]
    return {'algorithm': ALGORITHM, 'target_version_id': target_id,
            'historical_observations': len(old),
            'origin_version_ids': sorted({row['version_id'] for row in old})}
