"""Source-bound personal claims and their time/scope-dependent current view."""
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path

from django.db.models import Q
from django.utils import timezone

from ai_assistant.models import AgentMemory, Conversation, TaskMemoryObject


def active():
    from django.conf import settings
    return getattr(settings, 'UNIMIND_SDTM_TASK_MEMORY_MODE', 'off') == 'active'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def resolve(claims, *, project_id, now):
    """Confidence admits a claim; event time orders applicable self reports."""
    eligible = [c for c in claims if c['confidence'] >= .6 and c['event_at'] <= now
        and c['valid_from'] <= now and (c['valid_until'] is None or now < c['valid_until'])
        and c['project_id'] in (None, project_id)]
    if not eligible:
        return {'status': 'unknown'}
    specific = [c for c in eligible if c['project_id'] is not None]
    eligible = specific or eligible
    latest = max(c['event_at'] for c in eligible)
    winners = [c for c in eligible if c['event_at'] == latest]
    if len({(c['operation'], c['value']) for c in winners}) > 1:
        return {'status': 'conflict'}
    winner = sorted(winners, key=lambda c: c['identity'])[0]
    return {'status': 'retracted' if winner['operation'] == 'retract' else 'known', 'claim': winner}


RESOLVER = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
CONTEXT_POLICY = ('当前 memory 是有来源及时间／项目作用域的个人条件视图。'
    'unavailable 中的条件已撤回、未决或当前未知，不能从旧计划或旧对话恢复其旧值。'
    '教学经验与历史建议不能覆盖当前条件。'
    '计划中与当前个人条件冲突的安排须重新核对；保留计划目标及待做任务，不擅自将其标记完成。')


def _time(value):
    at = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(at, datetime) or timezone.is_naive(at):
        raise ValueError('Claim times must be aware datetimes.')
    return at


def _put(user, fact, kind, value, *, question=None, project_id=None):
    key = digest({'kind': kind, 'fact': fact.pk, 'question': question.pk if question else None,
                  'project': project_id, 'value': value})
    return TaskMemoryObject.objects.get_or_create(owner=user, digest=key, defaults={
        'fact': fact, 'kind': kind, 'value': value, 'question': question, 'project_id': project_id})


def append(user, candidate, question):
    """Called under the existing fact-write transaction and revision lock."""
    from ai_assistant.services.state.prism.prism_memory import accessible
    if question.user_id != user.pk or question.role != 'user' or not user.is_active or not accessible(question):
        return 0
    conversation = Conversation.objects.filter(user=user, conversation_id=question.conversation_id).first()
    evidence = ' '.join(str(candidate.get('evidence') or '').split())
    if not conversation or not evidence or evidence not in ' '.join(question.content.split()):
        return 0
    scope, operation = candidate.get('scope', 'global'), candidate.get('operation', 'set')
    if scope not in ('global', 'project') or operation not in ('set', 'retract'):
        return 0
    project_id = conversation.project_id if scope == 'project' else None
    if scope == 'project' and (project_id is None or conversation.project.user_id != user.pk):
        return 0
    try:
        confidence = float(candidate.get('confidence', 0))
        start = _time(candidate.get('valid_from') or question.timestamp)
        # Retraction cancels a claim from its effective time until a later statement.
        # An extractor's end date for the cancelled assertion is not the tombstone's expiry.
        end = _time(candidate['valid_until']) if operation == 'set' and candidate.get('valid_until') else None
    except (TypeError, ValueError):
        return 0
    memory_type, key, value = candidate.get('memory_type'), candidate.get('key'), candidate.get('value')
    if (memory_type not in dict(AgentMemory.MEMORY_TYPES) or not key or not value
            or not math.isfinite(confidence) or not .6 <= confidence <= 1 or end and end <= start):
        return 0
    fact, created = AgentMemory.objects.get_or_create(user=user, memory_type=memory_type, key=key,
        defaults={'value': value, 'source': 'dsh', 'confidence': confidence, 'evidence': evidence,
                  'source_conversation_id': str(question.conversation_id)})
    if not fact.is_active:
        return 0
    if not TaskMemoryObject.objects.filter(owner=user, fact=fact, kind='fact_base').exists():
        baseline = None if created else {'value': fact.value, 'confidence': fact.confidence,
            'event_at': fact.updated_at.isoformat(), 'source': fact.source}
        _put(user, fact, 'fact_base', {'baseline': baseline})
    claim = {'value': value, 'confidence': confidence, 'operation': operation, 'evidence': evidence,
        'event_at': question.timestamp.isoformat(), 'valid_from': start.isoformat(),
        'valid_until': end.isoformat() if end else None, 'source': 'dsh', 'evidence_kind': 'self_report'}
    return int(_put(user, fact, 'fact_claim', claim, question=question, project_id=project_id)[1])


def current(user, *, project=None, now=None, include_inactive=False):
    """Return public-rule interpretations of this learner's permitted private evidence."""
    from ai_assistant.services.memory_core import active_facts
    from ai_assistant.services.state.prism.prism_memory import accessible
    now = now or timezone.now()
    rows = list(active_facts(user, include_inactive=include_inactive))
    objects = list(TaskMemoryObject.objects.filter(owner=user, fact_id__in=[r.pk for r in rows],
        kind__in=['fact_base', 'fact_claim']).filter(Q(project__isnull=True) | Q(project=project))
        .select_related('question__user', 'question__bot'))
    # A project-only slot has no global fallback, even when read from another project.
    managed = {obj.fact_id for obj in objects if obj.kind == 'fact_base'}
    conversations = {str(cid): pid for cid, pid in Conversation.objects.filter(user=user).values_list('conversation_id', 'project_id')}
    items, conflicts, unavailable, provenance = [], [], [], []
    for row in rows:
        fields = {key: getattr(row, key) for key in ['id', 'memory_type', 'key', 'value', 'source', 'confidence', 'updated_at']}
        if row.source == 'manual' or row.pk not in managed:
            items.append(fields)
            continue
        claims = []
        for obj in objects:
            if obj.fact_id != row.pk:
                continue
            if obj.kind == 'fact_base':
                base = obj.value['baseline']
                if base:
                    claims.append({**base, 'operation': 'set', 'project_id': None, 'valid_until': None,
                        'event_at': _time(base['event_at']), 'valid_from': _time(base['event_at']),
                        'identity': obj.digest, 'source_message_id': None})
                continue
            if (not obj.question or not accessible(obj.question)
                    or str(obj.question.conversation_id) not in conversations
                    or obj.project_id is not None and conversations[str(obj.question.conversation_id)] != obj.project_id
                    or obj.value['evidence'] not in ' '.join(obj.question.content.split())):
                continue
            claim = {**obj.value, 'project_id': obj.project_id, 'identity': obj.digest,
                     'source_message_id': obj.question_id}
            for key in ['event_at', 'valid_from', 'valid_until']:
                claim[key] = _time(claim[key]) if claim[key] else None
            claims.append(claim)
        state = resolve(claims, project_id=project.pk if project else None, now=now)
        provenance.append({'id': row.pk, 'status': state['status'], 'evidence': sorted(c['identity'] for c in claims)})
        if state['status'] == 'conflict':
            conflicts.append({'id': row.pk, 'memory_type': row.memory_type, 'key': row.key})
        if state['status'] != 'known':
            unavailable.append({'id': row.pk, 'memory_type': row.memory_type, 'key': row.key, 'status': state['status']})
        if state['status'] == 'known':
            c = state['claim']
            items.append({**fields, 'value': c['value'], 'confidence': c['confidence'], 'source': c['source'], 'updated_at': c['event_at'],
                'source_message_id': c['source_message_id'], 'claim_id': c['identity'],
                'scope_project_id': c['project_id'], 'evidence_kind': 'self_report'})
    items.sort(key=lambda r: (r['updated_at'], r['id']), reverse=True)
    return {'items': items, 'conflicts': conflicts, 'unavailable': unavailable,
            'resolution': {'code': RESOLVER, 'claims': provenance}}
