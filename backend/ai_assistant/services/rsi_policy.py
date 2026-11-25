"""Versioned teaching assignments over the candidates available to this turn."""
from hashlib import sha256

from django.conf import settings
from rest_framework.exceptions import ValidationError

from ai_assistant.models import TeachingDecisionLog
from .teaching_sidecar import current_bundle


RECHECK_DELAYS = {'immediate-v1': 0, 'delayed-v1': 2}
RECHECK_VERSION = 'recheck-timing-s1'
METHOD_VERSION = 'method-ranking-s1'


def policy_mode(project_id=None):
    mode = settings.UNIMIND_RSI_ONLINE_POLICY_MODE
    if mode not in ('shadow', 'active') or (project_id is not None and project_id not in settings.UNIMIND_RSI_POLICY_PROJECTS):
        return 'off'
    return mode


def _draw(key, probabilities):
    # Use 53 bits so converting the hash to a float cannot round up to 1.
    draw = (int.from_bytes(sha256(key.encode()).digest()[:7], 'big') >> 3) / (1 << 53)
    for index, probability in enumerate(probabilities):
        if draw < probability:
            return index
        draw -= probability
    return len(probabilities) - 1


def _decisions(project, message, point):
    return TeachingDecisionLog.objects.filter(project=project, owner_id=project.user_id,
                                               message=message, decision_point=point)


def _record(project, message, point, *, task, version, mode, selected, propensity, candidates, context,
            frame_id, program_digest):
    return TeachingDecisionLog.objects.get_or_create(project=project, owner_id=project.user_id,
        message=message, decision_point=point, defaults={
            'task': task, 'mechanism_id': lambda: current_bundle()['S']['id'], 'policy_version': version,
            'selection_mode': mode, 'selected_action': selected, 'propensity': propensity,
            'candidates': candidates, 'context_snapshot': context, 'sdtm_frame_id': frame_id,
            'sdtm_program_digest': program_digest, 'exposure': {'status': 'assigned'},
        })[0]


def select_recheck_timing(project, task, current_message, *, source_result_id, prior_decision=None,
                          sdtm_frame_id=None, sdtm_program_digest='', bpe_summary=None):
    """Return the assigned strategy and its log for a new recheck countdown."""
    if prior_decision and prior_decision.get('source_result_id') == source_result_id:
        strategy = prior_decision['strategy']
        if strategy not in RECHECK_DELAYS:
            raise ValidationError('ULR 复测策略配置无效。')
        return strategy, None
    decisions = _decisions(project, current_message, 'recheck_timing')
    if saved := decisions.first():
        return saved.selected_action, saved

    baseline = f'{settings.UNIMIND_ULR_RECHECK_STRATEGY}-v1'
    if baseline not in RECHECK_DELAYS:
        raise ValidationError('ULR 复测策略配置无效。')
    arms = sorted(RECHECK_DELAYS)
    selected, selection_mode, propensity = baseline, 'deterministic', None
    context = {'source_result_id': source_result_id, 'baseline_action': baseline}
    if bpe_summary is not None:
        context['bpe_summary'] = bpe_summary
    mode = policy_mode(project.pk)
    rate = settings.UNIMIND_RSI_EXPLORATION_RATE
    probabilities = [None] * len(arms)
    if mode == 'shadow' or (mode == 'active' and rate > 0):
        distribution = [1 - rate if arm == baseline else rate / (len(arms) - 1) for arm in arms]
        index = _draw(f'recheck:{project.pk}:{source_result_id}:{RECHECK_VERSION}', distribution)
        if mode == 'shadow':
            context['shadow_recommendation'] = arms[index]
            selection_mode = 'shadow_only'
        else:
            selected, propensity = arms[index], distribution[index]
            selection_mode, probabilities = 'stratified_random', distribution
    candidates = [{'action': arm, 'delay_turns': RECHECK_DELAYS[arm], 'propensity': probability}
                  for arm, probability in zip(arms, probabilities)]
    saved = _record(project, current_message, 'recheck_timing', task=task, version=RECHECK_VERSION, mode=selection_mode,
        selected=selected, propensity=propensity, candidates=candidates, context=context,
        frame_id=sdtm_frame_id, program_digest=sdtm_program_digest)
    return saved.selected_action, saved


def _method_candidate(kind, row):
    method_id = row['method_id'] if kind == 'public' else row['id']
    task_id = (row.get('binding') or {}).get('task_id') if kind == 'public' else None
    task_id = str(task_id) if task_id is not None else None
    action = f'{kind}:{method_id}:{task_id}' if task_id else f'{kind}:{method_id}'
    return {'action': action, 'kind': kind, 'method_id': method_id, 'task_id': task_id,
            'method_digest': row.get('method_digest'), 'propensity': None}


def _candidate_key(candidate):
    return candidate['action'], candidate['method_digest']


def method_assignment(log, *, kind, method_id, method_digest, task_id=None):
    return next((candidate for candidate in log.candidates if candidate['kind'] == kind
        and candidate['method_id'] == method_id and candidate['method_digest'] == method_digest
        and candidate['task_id'] == (str(task_id) if task_id is not None else None)), None)


def rank_method_candidates(project, current_message, *, public_methods=(), private_strategies=(), task=None,
                           sdtm_frame_id=None, sdtm_program_digest='', estimates=None):
    """Rank a visible slate. SDTM estimates inform visibility upstream; only ledger outcomes inform ranking."""
    original = [(_method_candidate(kind, row), row) for kind, rows in
                (('public', public_methods), ('private', private_strategies)) for row in rows]
    entries = original
    mode = policy_mode(project.pk)
    if not entries:
        return {'public_methods': [], 'private_strategies': [], 'method_candidate_order': []}
    decisions = _decisions(project, current_message, 'method_ranking') if current_message is not None else None
    saved = decisions.first() if decisions is not None else None
    context = {}
    selection_mode = 'deterministic'
    if not saved and mode != 'off':
        from . import rsi_evidence
        evidence = rsi_evidence.summarize_method_evidence(rsi_evidence.project_method_evidence(project))
        for candidate, row in entries:
            if candidate['kind'] == 'public':
                ledger, identity = 'public_method', row.get('key') or candidate['method_id']
            else:
                ledger, identity = 'private_strategy', candidate['method_id']
            counts = evidence.get((ledger, identity, candidate['method_digest']), {})
            successes = counts.get('independent_success_count', 0)
            failures = counts.get('independent_failure_count', 0)
            candidate['posterior_mean'] = (1.0 + successes) / (2.0 + successes + failures)
        ranked = sorted(entries, key=lambda entry: -entry[0]['posterior_mean'])
        rate = settings.UNIMIND_RSI_EXPLORATION_RATE
        if mode == 'shadow':
            context['shadow_ranking'] = [candidate['action'] for candidate, _ in ranked]
            selection_mode = 'shadow_only'
        else:
            entries = ranked
            if current_message is not None and rate > 0 and len(entries) >= 2:
                explore = rate / len(entries)
                probabilities = [1 - rate + explore] + [explore] * (len(entries) - 1)
                for (candidate, _), probability in zip(entries, probabilities):
                    candidate['propensity'] = probability
                index = _draw(f'method_rank:{project.pk}:{current_message.pk}:{METHOD_VERSION}', probabilities)
                entries.insert(0, entries.pop(index))
                selection_mode = 'bounded_exploration'
    if decisions is not None and not saved:
        selected = entries[0][0]
        saved = _record(project, current_message, 'method_ranking', task=task, version=METHOD_VERSION, mode=selection_mode,
            selected=selected['action'], propensity=selected['propensity'],
            candidates=[candidate for candidate, _ in entries], context=context,
            frame_id=sdtm_frame_id, program_digest=sdtm_program_digest)
    if saved and mode == 'active':
        # A different task read can expose a different slate in the same turn.
        order = {_candidate_key(candidate): rank for rank, candidate in enumerate(saved.candidates)}
        if len(entries) == len(order) and {_candidate_key(candidate) for candidate, _ in entries} == order.keys():
            entries.sort(key=lambda entry: order[_candidate_key(entry[0])])
        else:
            entries = original
    return {'public_methods': [row for candidate, row in entries if candidate['kind'] == 'public'],
            'private_strategies': [row for candidate, row in entries if candidate['kind'] == 'private'],
            'method_candidate_order': [candidate['action'] for candidate, _ in entries]}
