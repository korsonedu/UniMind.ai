"""SDTM's bounded, model-independent representation and transport kernel.

Features are observations, fields select the representation, and behavior slots
are an inspectable plan. No generated code or tool invocation is executed here.
"""
from collections import deque
from itertools import permutations
import json
import re


def validate_splits(*splits):
    ids = []
    for cases in splits:
        if not isinstance(cases, list) or not 1 <= len(cases) <= 24:
            raise ValueError('Each split requires 1..24 reference cases.')
        for case in cases:
            if (not isinstance(case, dict) or case.get('verified') is not True
                    or not isinstance(case.get('id'), (str, int)) or isinstance(case['id'], bool)):
                raise ValueError('Cases need a unique id and verified reference labels.')
            ids.append(case['id'])
            for kind in ('features', 'behavior'):
                values = case.get(kind)
                if not isinstance(values, dict) or not 1 <= len(values) <= 16:
                    raise ValueError('Features and behavior require 1..16 slots.')
                if any(not re.fullmatch('[a-z][a-z0-9_]{0,47}', key) or
                       not isinstance(value, str) or not 0 < len(value) <= 240 for key, value in values.items()):
                    raise ValueError('Slots need bounded snake_case keys and string values.')
    if len(ids) != len(set(ids)):
        raise ValueError('Reference splits require distinct case IDs.')


def digest(value):
    import hashlib
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def encode(features, fields):
    return {key: features[key] for key in fields if key in features}


def induce(cases, fields):
    """Induce paired changes, not concatenations of successful procedures."""
    operators = {}
    for source, target in permutations(cases, 2):
        before, after = encode(source['features'], fields), encode(target['features'], fields)
        if set(before) != set(fields) or set(after) != set(fields):
            continue
        change = {key: after[key] for key in fields if before[key] != after[key]}
        if set(source['behavior']) != set(target['behavior']):
            continue
        effect = {key: value for key, value in target['behavior'].items()
                  if source['behavior'][key] != value}
        if not change or not effect:
            continue
        operator = {
            'requires': {key: before[key] for key in change},
            'situation_delta': change,
            'behavior_requires': {key: source['behavior'][key] for key in effect},
            'behavior_delta': effect,
        }
        key = digest(operator)
        if key not in operators:
            operators[key] = {**operator, 'id': key, 'evidence': []}
        operators[key]['evidence'].append([source['id'], target['id']])
    return list(operators.values())


def transfer(cases, fields, target, operators=None, *, max_steps=2):
    """Search paired transformations. Conflicting plans cause abstention.

    Only fields changed by an operator are transported. Applicability in unseen
    contexts remains an empirical hypothesis, not a semantic correctness proof.
    """
    wanted = encode(target, fields)
    if not fields or len(wanted) != len(fields):
        return {'status': 'unknown', 'reason': 'missing_conditions', 'paths': []}
    operators = induce(cases, fields) if operators is None else operators
    queue = deque((encode(case['features'], fields), case['behavior'], case['id'], [])
                  for case in cases if set(encode(case['features'], fields)) == set(fields))
    seen, solutions, expanded = set(), [], 0
    while queue and expanded < 256:
        frame, behavior, source, path = queue.popleft()
        key = digest([frame, behavior, source])
        if key in seen:
            continue
        seen.add(key)
        expanded += 1
        if frame == wanted:
            solutions.append({'source': source, 'behavior': behavior, 'operators': path})
            continue
        if len(path) >= max_steps:
            continue
        for operator in operators:
            if (all(key in frame and frame[key] == value for key, value in operator['requires'].items())
                    and all(key in behavior and behavior[key] == value
                            for key, value in operator['behavior_requires'].items())):
                queue.append(({**frame, **operator['situation_delta']},
                              {**behavior, **operator['behavior_delta']}, source,
                              [*path, operator['id']]))
    if queue:
        return {'status': 'unknown', 'reason': 'search_budget', 'paths': [], 'expanded': expanded}
    plans = {digest(row['behavior']) for row in solutions}
    if len(plans) != 1:
        return {'status': 'ambiguous' if plans else 'unknown', 'paths': [], 'expanded': expanded}
    best = min(solutions, key=lambda row: (len(row['operators']), str(row['source'])))
    return {'status': 'matched', **best, 'paths': solutions[:8], 'expanded': expanded}


def evaluate(train, validation, fields):
    operators = induce(train, fields)
    correct = wrong = unknown = 0
    for case in validation:
        result = transfer(train, fields, case['features'], operators)
        if result['status'] != 'matched':
            unknown += 1
        elif result['behavior'] == case['behavior']:
            correct += 1
        else:
            wrong += 1
    count = len(validation)
    return {'count': count, 'correct': correct, 'wrong': wrong, 'unknown': unknown,
            'loss': (wrong + .5 * unknown) / count if count else 1,
            'operators': len(operators)}


def aliases(cases, fields):
    groups = {}
    for case in cases:
        key = digest(encode(case['features'], fields))
        groups.setdefault(key, set()).add(digest(case['behavior']))
    return sum(len(values) - 1 for values in groups.values())


def differentiate(train, validation, fields, *, candidate_fields=None):
    """Select one observed distinction using independent validation cases.

    This first kernel selects from grounded observed fields. Semantic discovery
    of new predicates is not claimed. Validation is selection data, not test data.
    """
    validate_splits(train, validation)
    baseline = evaluate(train, validation, fields)
    conflicts = aliases(train, fields)
    candidates = []
    available = set().union(*(case['features'] for case in train)) - set(fields)
    if candidate_fields is not None:
        available &= set(candidate_fields)
    for key in sorted(available):
        new_fields = [*fields, key]
        if aliases(train, new_fields) >= conflicts:
            continue
        report = evaluate(train, validation, new_fields)
        if report['wrong'] <= baseline['wrong'] and report['loss'] < baseline['loss']:
            candidates.append({'fields': new_fields, 'added': key, 'report': report})
    selected = min(candidates, key=lambda row: (row['report']['loss'], row['report']['operators'], row['added'])) if candidates else None
    return {'baseline': baseline, 'selected': selected, 'candidates': candidates,
            'train_ids': [row['id'] for row in train], 'validation_ids': [row['id'] for row in validation]}
