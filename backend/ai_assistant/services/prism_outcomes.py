"""Prospective representation learning from verified independent objective tasks."""
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ai_assistant.models import Conversation, PrismMemory, PrismRevision, ProjectLearning
from .prism_kernel import aliases, digest, evaluate, induce, transfer

KIND = 'objective_outcomes'
DEFINITIONS = {'node': '正式任务所属知识点 ID', 'mode': '正式任务的应用 apply 或迁移 transfer 类型',
    'stage': '正式任务所属学习阶段 ID'}


def learn(cases, *, freeze_times=None, now=None):
    """Freeze candidates before future tasks exist; labels never select themselves."""
    fields, past, pending, revisions, predictions = ['node'], [], None, [], []
    frozen = {}
    for case in cases:
        prediction = transfer(past, fields, case['features'])
        predictions.append({'id': case['id'], 'fields': fields[:], 'status': prediction['status'],
            'predicted': prediction.get('behavior'), 'observed': case['behavior']})
        if pending and case['task_at'] > pending['cutoff'] and case['exam_id'] not in {
                row['exam_id'] for row in pending['validation']}:
            pending['validation'].append(case)
            if len(pending['validation']) == 2:
                baseline = evaluate(pending['training'], pending['validation'], fields)
                candidate = evaluate(pending['training'], pending['validation'], pending['fields'])
                accepted = candidate['loss'] < baseline['loss'] and candidate['wrong'] <= baseline['wrong']
                revisions.append({'before': fields[:], 'after': pending['fields'], 'accepted': accepted,
                    'training_ids': [row['id'] for row in pending['training']],
                    'future_ids': [row['id'] for row in pending['validation']], 'baseline': baseline, 'candidate': candidate})
                if accepted:fields = pending['fields']
                pending = None
        past.append(case)
        if pending is None and aliases(past, fields):
            choices = [fields + [key] for key in ('mode', 'stage') if key not in fields]
            choices = [choice for choice in choices if aliases(past, choice) < aliases(past, fields)]
            if choices:
                selected = min(choices, key=lambda choice: (aliases(past, choice), choice))
                identity = digest([selected, [row['id'] for row in past]])
                cutoff = (freeze_times or {}).get(identity, now or case['at'])
                frozen[identity] = cutoff
                pending = {'fields': selected, 'training': past[:], 'cutoff': cutoff, 'validation': []}
    return {'fields': fields, 'revisions': revisions, 'pending': pending, 'predictions': predictions, 'freeze_times': frozen}


def observations(project, version_id):
    from .learning_task_evidence import verified_task_events
    rows = []
    for event, task, result in verified_task_events(project, version_id)['events']:
        if (event.content['label_source'] != 'objective_answer_key' or task.assistance != 'independent'
                or not task.node_id or task.mode not in ('apply', 'transfer')):
            continue
        rows.append({'id': str(event.pk), 'verified': True,
            'features': {'node': task.node_id, 'mode': task.mode, 'stage': task.stage_id},
            'behavior': {'outcome': event.content['outcome']}, 'exam_id': result.exam_id,
            'task_at': task.created_at.isoformat(), 'at': result.graded_at.isoformat(),
            'source_digest': digest([event.content, task.question_snapshot])})
    return rows[-24:]


@transaction.atomic
def refresh(project, version_id):
    if getattr(settings, 'UNIMIND_PRISM_MODE', 'off') != 'active' or version_id is None:
        return None
    # Serialize learners' result callbacks before replaying the same project stream.
    type(project).objects.select_for_update().get(pk=project.pk, user_id=project.user_id)
    cases = observations(project, version_id)
    key = f'student:{project.user_id}:outcomes:{project.pk}:{version_id}'
    memory = PrismMemory.objects.select_for_update().filter(key=key, owner=project.user, scope='student').first()
    if not cases:
        if memory and memory.active:
            memory.active = False;memory.save(update_fields=['active', 'updated_at'])
        return None
    fingerprint = digest(cases)
    if memory and memory.active and memory.provenance.get('source_digest') == fingerprint:
        return memory
    previous = memory.provenance.get('state', {}).get('freeze_times', {}) if memory else {}
    state = learn(cases, freeze_times=previous, now=timezone.now().isoformat())
    provenance = {'kind': KIND, 'project_id': project.pk, 'version_id': version_id,
        'source_digest': fingerprint, 'state': state, 'label': 'objective_answer_key', 'scope': 'individual_observation_not_teaching_effect'}
    values = {'fields': state['fields'], 'definitions': DEFINITIONS, 'cases': cases,
        'operators': induce(cases, state['fields']), 'provenance': provenance, 'active': True}
    if memory:
        if memory.fields != state['fields']:
            PrismRevision.objects.create(memory=memory, before={name: getattr(memory, name) for name in
                ('fields', 'definitions', 'cases', 'operators', 'provenance', 'active', 'revision')},
                report={'automatic': True, 'source_digest': fingerprint, 'prospective_revisions': state['revisions']}, accepted=True)
        for name, value in values.items():setattr(memory, name, value)
        memory.revision += 1;memory.save()
    else:
        memory = PrismMemory.objects.create(key=key, owner=project.user, scope='student', **values)
    return memory


def context(question):
    if getattr(settings, 'UNIMIND_PRISM_MODE', 'off') != 'active':return {}
    conversation = Conversation.objects.filter(user=question.user, bot=question.bot,
        conversation_id=question.conversation_id).first()
    learning = ProjectLearning.objects.filter(project_id=conversation.project_id,
        project__user=question.user, status='active').first() if conversation and conversation.project_id else None
    if not learning:return {}
    version = learning.plan.get('knowledge_path', {}).get('version_id')
    memory = PrismMemory.objects.filter(owner=question.user, scope='student', active=True,
        key=f'student:{question.user_id}:outcomes:{learning.project_id}:{version}').first()
    if (not memory or memory.provenance.get('kind') != KIND or digest(memory.cases) != memory.provenance.get('source_digest')
            or memory.provenance.get('source_digest') != digest(observations(learning.project, version))):
        return {}
    stage = next((row for row in learning.plan.get('stages', []) if row['id'] == learning.current_stage), {})
    forecasts = []
    for node in stage.get('knowledge_nodes', [])[:3]:
        for mode in ('apply', 'transfer'):
            target = {'node': node, 'mode': mode, 'stage': learning.current_stage}
            result = transfer(memory.cases, memory.fields, target, memory.operators)
            forecasts.append({**target, 'status': result['status'], 'predicted_outcome': result.get('behavior', {}).get('outcome')})
    return {'key': memory.key, 'revision': memory.revision, 'fields': memory.fields,
        'observations': len(memory.cases), 'forecasts': forecasts,
        'notice': '本人近期独立客观题的待检验表现模式，用于安排核查；不代表掌握或教法效果，未知需保留，不据此给出题目答案。'}
