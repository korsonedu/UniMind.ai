"""Read-only evidence from private strategies and public method adoptions."""
import math

from django.db.models import Prefetch
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from ai_assistant.models import Conversation, LearningStrategyOutcome, LearningStrategyUse, ProjectLearning
from users.feature_access import has_learning_feature
from . import fact_evidence, learning_continuity, learning_diagnostics, method_adoption, public_methods
from .learning_library import _adopted_method, unconfirmed_strategy_use_ids
from .learning_tasks import _hash, task_label_source, task_question_hash, task_result_snapshot, task_states
from .prism_memory import accessible
from .project_learning import unconfirmed_progress_ids
from .task_memory_store import _project
from .teaching_sidecar import overlapping_public_use, validate_strategy_use, verified_strategy_reply

DISCLOSURE = 'same_instance_solution_disclosed'
INDEPENDENT = 'independent_reported_observation'


def _eligible(outcome):
    return outcome['status'] == INDEPENDENT and not outcome['reasons']


def _record(project, ledger, identity, method_ref, *, task_id, question_id, reply_id,
            assigned_at, completed_at, mechanisms, selection, source_available, outcomes):
    propensity = selection.get('propensity')
    if type(propensity) not in (int, float) or not 0 <= propensity <= 1:
        propensity = None
    return {'ledger': ledger, 'use_id': f"{method_ref['kind']}:{identity}", 'project_id': project.pk,
            'task_id': task_id, 'method_ref': method_ref, 'question_id': question_id if source_available else None,
            'reply_id': reply_id if source_available else None, 'assigned_at': assigned_at,
            'completed_at': completed_at if source_available else None,
            'mechanisms': mechanisms if source_available else None,
            'selection': {'selection_kind': selection.get('selection_kind'),
                          'propensity': float(propensity) if propensity is not None else None,
                          'model_visible_candidate_set': selection.get('model_visible_candidate_set')},
            'exposure': {'status': 'reply_completed' if reply_id and source_available else 'assigned',
                         'adherence': 'unverified', 'presentation': 'unknown'},
            'source_available': source_available, 'outcomes': outcomes,
            'eligible_for_eval': source_available and any(_eligible(row) for row in outcomes), 'causal_claim': False}


def _outcome(data, task, *, reasons, graded_at):
    return {**{key: data[key] for key in ('result_id', 'event_id', 'score', 'max_score', 'outcome',
                                        'assistance', 'label_source')},
            'task_id': task['id'], 'node_id': task['node_id'], 'mode': task['mode'], 'purpose': task['purpose'],
            'status': 'uncertain' if reasons else INDEPENDENT, 'reasons': reasons,
            'timing_verified': not any(reason in reasons for reason in ('no_completed_prior_teaching', 'no_completed_prior_reply')),
            'repeated': 'repeated_question' in reasons, 'overlapping_methods': any(
                reason in reasons for reason in ('overlapping_methods', 'registered_methods_overlap')),
            'disclosed': DISCLOSURE in reasons, 'graded_at': graded_at}


def _private_outcome(row, use, source_available, reply, completed, excluded):
    task, result, event, saved = row.task, row.result, row.event, row.snapshot
    if (task.project_id != use.project_id or task.strategy_use_id != use.pk or event.project_id != use.project_id
            or event.kind != 'assessment' or result.status != 'graded' or not result.graded_at
            or not all(math.isfinite(value) for value in (result.score, result.max_score))):
        return None
    try:
        question = task_result_snapshot(task, result)
    except (ValidationError, PermissionDenied):
        return None
    expected = {'task_id': str(task.pk), 'result_id': result.pk, 'assistance': task.assistance,
                'score': result.score, 'max_score': result.max_score, 'label_source': task_label_source(task, result),
                'question_hash': task_question_hash(question), 'answer_hash': _hash(result.user_answer.strip())}
    outcome = 'success' if result.max_score > 0 and result.score / result.max_score >= .6 else 'failure'
    if (any(saved.get(key) != value or event.content.get(key) != value for key, value in expected.items())
            or event.content.get('outcome') != outcome):
        return None
    reasons = [reason for reason in saved['reasons'] if excluded is None or reason != DISCLOSURE]
    checks = [
        (not saved['timing_verified'] or not reply or result.exam.created_at <= max(completed, reply.timestamp)
         or result.exam.created_at < max(use.created_at, task.created_at) or result.graded_at < result.exam.created_at,
         'no_completed_prior_teaching'),
        (saved['overlapping_methods'] or overlapping_public_use(task, use.created_at, result.exam.created_at),
         'overlapping_methods'),
        (excluded is not None and str(task.pk) in excluded, DISCLOSURE),
        (not source_available or saved.get('method_version_id') != use.method_version_id, 'source_unavailable'),
    ]
    reasons.extend(reason for applies, reason in checks if applies and reason not in reasons)
    return _outcome({**expected, 'event_id': event.pk, 'outcome': outcome},
                    {'id': str(task.pk), 'node_id': task.node_id, 'mode': task.mode, 'purpose': task.purpose},
                    reasons=reasons, graded_at=result.graded_at.isoformat())


def _private_records(project, task_access, now):
    uses = LearningStrategyUse.objects.filter(project=project, strategy__user_id=project.user_id,
        message__user_id=project.user_id).exclude(strategy__source_event_id__in=unconfirmed_progress_ids(project.user_id))
    uses = uses.exclude(pk__in=unconfirmed_strategy_use_ids(project.user_id, uses)).select_related(
        'message__bot', 'message__user', 'strategy__source_event__message__bot',
        'strategy__source_event__message__user', 'method_version')
    tasks = {}
    if task_access:
        rows = project.learning_tasks.filter(strategy_use_id__in=uses.values('pk')).values_list('strategy_use_id', 'pk')
        for use_id, task_id in rows:
            tasks.setdefault(use_id, []).append(str(task_id))
        uses = uses.prefetch_related(Prefetch('task_outcomes', queryset=LearningStrategyOutcome.objects.select_related(
            'task__project', 'result__exam', 'result__question__knowledge_point', 'event').order_by('result__graded_at', 'pk')))
    excluded = None
    if learning_diagnostics.active(project.pk) and task_access:
        excluded = learning_diagnostics.excluded_tasks(learning_diagnostics.read_sources(
            project, {task_id for ids in tasks.values() for task_id in ids}, now=now))
    rooms = dict(Conversation.objects.filter(user=project.user, project__user=project.user)
                 .values_list('conversation_id', 'project_id'))
    for use in uses.order_by('pk'):
        strategy, source = use.strategy, use.strategy.source_event
        method = _adopted_method(use)
        question_available = rooms.get(use.message.conversation_id) == project.pk and accessible(use.message)
        available = bool(question_available and source.message and rooms.get(source.message.conversation_id) == source.project_id
                         and accessible(source.message)
                         and (method['method_state'] == 'available' or (
                             method['method_state'] == 'unversioned' and not use.decision.get('selected_digest'))))
        if available:
            try:
                validate_strategy_use(project, use.pk)
            except ValidationError:
                available = False
        reply, completed = verified_strategy_reply(use) if question_available else (None, None)
        if use.exposure.get('reply_id') and not reply:
            available = False
        outcomes = []
        if task_access:
            for row in use.task_outcomes.all():
                outcome = _private_outcome(row, use, available, reply, completed, excluded)
                if outcome is not None:
                    outcomes.append(outcome)
        ids = tasks.get(use.pk, [])
        yield _record(project, 'private_strategy', use.pk,
            {'kind': 'private', 'id': strategy.pk, 'digest': method['method_digest'] or use.decision.get('selected_digest'),
             'key': None, 'domain': strategy.domain if available else None, 'topic': strategy.topic if available else None,
             'version_id': use.method_version_id or use.decision.get('selected_version_id')},
            task_id=ids[0] if len(ids) == 1 else None, question_id=use.message_id, reply_id=reply.pk if reply else None,
            assigned_at=use.created_at.isoformat(), completed_at=completed.isoformat() if completed else None,
            mechanisms=use.decision.get('mechanisms') or use.message.metadata.get('rsi_sidecar'),
            selection=use.decision if available else {}, source_available=available, outcomes=outcomes)


def _public_records(project, now):
    state = ProjectLearning.objects.filter(project=project).first()
    if state is None:
        return
    version = (state.plan.get('knowledge_path') or {}).get('version_id')
    _, verified, scope = learning_continuity.formal_observations(project, version)
    tasks = task_states(project, state, scope=scope)
    task_rows = {row['id']: row for row in tasks}
    diagnostic = learning_diagnostics.read_sources(project, set(task_rows), now=now) if learning_diagnostics.active(project.pk) else {}
    history, versions = method_adoption.history_source(project, verified['events'], tasks, public_methods.catalogue(),
        verified['verified_versions'], diagnostic_sources=diagnostic, include_provenance=True)
    definitions = {version['id']: version['definition'] for version in versions}
    for row in history:
        task = task_rows.get(row['task_id'])
        if task is None:
            continue
        available = row['source_available'] and row['status'] != 'source_unavailable' and task['status'] != 'unavailable'
        outcomes = []
        for outcome in row['outcomes']:
            reasons = outcome['reasons']
            if not available and 'source_unavailable' not in reasons:
                reasons = [*reasons, 'source_unavailable']
            outcomes.append(_outcome(outcome, task, reasons=reasons, graded_at=outcome['at']))
        definition = definitions.get(row['method_id'], {})
        yield _record(project, 'public_method', row['use_id'],
            {'kind': 'public', 'id': row['method_id'], 'digest': row['method_digest'], 'key': row['method_key'],
             'domain': None, 'topic': definition.get('requires', {}).get('topic'), 'version_id': row['method_id']},
            task_id=row['task_id'], question_id=row['question_id'], reply_id=row['answer_id'] if row['reply_completed'] else None,
            assigned_at=row['assigned_at'], completed_at=row['completed_at'], mechanisms=row['mechanisms'],
            selection={'selection_kind': 'model_directed_nonrandom'}, source_available=available, outcomes=outcomes)


def project_method_evidence(project, *, include_private=True, include_public=True, now=None):
    """Read evidence for a trusted project scope, with current permissions and a diagnostic cutoff."""
    project = _project(project, project.user)
    if not has_learning_feature(project.user, 'full.report'):
        return []
    now = now or timezone.now()
    task_access = has_learning_feature(project.user, 'quiz.exam')
    records = list(_private_records(project, task_access, now)) if include_private else []
    if include_public and task_access and fact_evidence.active():
        records.extend(_public_records(project, now))
    return sorted(records, key=lambda row: (row['assigned_at'], row['use_id']))


def summarize_method_evidence(records):
    counts = {}
    for row in records:
        method = row['method_ref']
        key = (row['ledger'], method['key'] or method['id'], method['digest'])
        count = counts.setdefault(key, dict.fromkeys((
            'assigned_count', 'reply_completed_count', 'outcome_count', 'eligible_outcome_count',
            'uncertain_outcome_count', 'independent_success_count', 'independent_failure_count',
            'excluded_disclosure_count', 'excluded_repeated_count', 'excluded_overlap_count'), 0))
        count['assigned_count'] += 1
        count['reply_completed_count'] += row['exposure']['status'] == 'reply_completed'
        for outcome in row['outcomes']:
            eligible = row['source_available'] and _eligible(outcome)
            count['outcome_count'] += 1
            count['eligible_outcome_count'] += eligible
            count['uncertain_outcome_count'] += outcome['status'] == 'uncertain'
            count['independent_success_count'] += eligible and outcome['outcome'] == 'success'
            count['independent_failure_count'] += eligible and outcome['outcome'] == 'failure'
            count['excluded_disclosure_count'] += outcome['disclosed']
            count['excluded_repeated_count'] += outcome['repeated']
            count['excluded_overlap_count'] += outcome['overlapping_methods']
    return dict(sorted(counts.items(), key=lambda item: (item[0][0], str(item[0][1]), item[0][2] or '')))
