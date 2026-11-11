"""Frozen temporal holdout for rubric-labelled BEP observations, not learning effects."""
from datetime import datetime
from math import log

from .bayesian_evidence import (
    ALGORITHM_VERSION, ASSISTANCE_WEIGHTS, GRID, GUESS, SLIP,
    STALE_HALF_LIFE_DAYS, belief,
)


MODELS = ('bep', 'prior_only', 'weighted_beta')


def _time(value):
    value = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Evaluation times must include a timezone.')
    return value


def _metrics(rows, model):
    count = len(rows)
    bins = []
    for index in range(5):
        members = [row for row in rows if min(4, int(row['probabilities'][model] * 5)) == index]
        bins.append({
            'lower': index / 5, 'upper': (index + 1) / 5, 'count': len(members),
            'mean_prediction': sum(row['probabilities'][model] for row in members) / len(members) if members else None,
            'success_rate': sum(row['outcome'] == 'success' for row in members) / len(members) if members else None,
        })
    brier = log_loss = None
    if count:
        brier = sum((row['probabilities'][model] - (row['outcome'] == 'success')) ** 2 for row in rows) / count
        loss = 0.
        for row in rows:
            probability = min(1 - 1e-12, max(1e-12, row['probabilities'][model]))
            loss -= log(probability if row['outcome'] == 'success' else 1 - probability)
        log_loss = loss / count
    return {'n': count, 'brier': brier, 'log_loss': log_loss, 'calibration_bins': bins}


def evaluate_records(records, cutoff, data_origin):
    """Evaluate one authorized project's fixed holdout without feeding its labels back.

    Provenance is the caller's responsibility. Deduplication is project-wide for
    event/message/probe IDs and per version/node across modes for nonempty hashes.
    """
    if data_origin not in ('synthetic', 'observational'):
        raise ValueError('data_origin must be synthetic or observational.')
    cutoff = _time(cutoff)
    counts = dict.fromkeys(('input', 'training', 'holdout', 'invalid', 'duplicate',
                            'straddling', 'unscored_training', 'unscored_holdout'), 0)
    parsed = []
    for record in records:
        counts['input'] += 1
        try:
            at, task_at = _time(record['at']), _time(record['task_at'])
            if at < task_at or record['mode'] not in ('apply', 'transfer'):
                raise ValueError('Invalid task chronology or mode.')
            if record['outcome'] not in ('success', 'failure', 'unclear') or record['assistance'] not in ASSISTANCE_WEIGHTS:
                raise ValueError('Invalid observation label.')
            identifiers = ('event_id', 'result_id', 'version_id') if record.get('evidence_type') == 'formal' else ('event_id', 'message_id', 'probe_id', 'version_id')
            if any(type(record[key]) is not int or record[key] < 1 for key in identifiers):
                raise ValueError('Invalid observation identifier.')
            if record.get('evidence_type') == 'formal':
                from uuid import UUID
                UUID(record['task_id'])
                if record.get('label_source') != 'objective_answer_key':
                    raise ValueError('Unknown formal label source.')
            if not isinstance(record['node_id'], str) or not record['node_id']:
                raise ValueError('Missing node identifier.')
            if any(not isinstance(record[key], str) for key in ('question_hash', 'answer_hash')):
                raise ValueError('Invalid evidence hash.')
            parsed.append((at, task_at, record))
        except (KeyError, TypeError, ValueError, OverflowError):
            counts['invalid'] += 1
    seen = set()
    training = {}
    holdout = []
    for at, task_at, record in sorted(parsed, key=lambda item: (item[0], item[2]['event_id'])):
        node = (record['version_id'], record['node_id'])
        formal = record.get('evidence_type') == 'formal'
        identifiers = ('event_id', 'result_id') if formal else ('event_id', 'message_id', 'probe_id')
        keys = {(key, record[key]) for key in identifiers}
        hashes = ('question_hash',) if formal else ('question_hash', 'answer_hash')
        keys.update((key, *node, record[key]) for key in hashes if record[key])
        if seen.intersection(keys):
            counts['duplicate'] += 1
            continue
        seen.update(keys)
        group = (*node, record['mode'])
        if at < cutoff:
            if record['outcome'] in ('success', 'failure') and ASSISTANCE_WEIGHTS[record['assistance']] > 0:
                training.setdefault(group, []).append({**record, 'at': at})
                counts['training'] += 1
            else:
                counts['unscored_training'] += 1
        elif task_at < cutoff:
            counts['straddling'] += 1
        elif record['outcome'] in ('success', 'failure') and record['assistance'] == 'independent':
            holdout.append((task_at, record))
            counts['holdout'] += 1
        else:
            counts['unscored_holdout'] += 1
    predictions = []
    for task_at, record in holdout:
        group = (record['version_id'], record['node_id'], record['mode'])
        history = [row for row in training.get(group, []) if row['at'] < task_at]
        estimate = belief(history, task_at)
        success_weight = sum(ASSISTANCE_WEIGHTS[row['assistance']] for row in history if row['outcome'] == 'success')
        total_weight = sum(ASSISTANCE_WEIGHTS[row['assistance']] for row in history)
        probabilities = {
            'bep': estimate['predicted_success'],
            'prior_only': GUESS + (1 - GUESS - SLIP) * .5,
            'weighted_beta': (1 + success_weight) / (2 + total_weight),
        }
        predictions.append({
            **{key: record[key] for key in ('event_id', 'version_id', 'node_id', 'mode', 'outcome')},
            'task_at': task_at.isoformat(), 'probabilities': probabilities, 'history_count': len(history),
            'label_source': record.get('label_source', 'xiaoyu_rubric_judgement'),
        })
    label_sources = sorted({row['label_source'] for row in predictions})
    return {
        'algorithm': {
            'version': ALGORITHM_VERSION, 'evaluation_protocol': 'frozen-temporal-holdout-v1',
            'grid': list(GRID), 'guess': GUESS, 'slip': SLIP,
            'stale_half_life_days': STALE_HALF_LIFE_DAYS, 'assistance_weights': dict(ASSISTANCE_WEIGHTS),
            'weighted_beta_prior': [1, 1], 'log_loss_clip': 1e-12, 'calibration_bin_count': 5,
        },
        'cutoff': cutoff.isoformat(), 'data_origin': data_origin,
        'label_source': label_sources[0] if len(label_sources) == 1 else ('mixed' if label_sources else 'none'),
        'metrics_by_label_source': {source: {model: _metrics([row for row in predictions if row['label_source'] == source], model) for model in MODELS} for source in label_sources},
        'calibrated': False, 'counts': counts,
        'metrics': {model: {scope: _metrics([row for row in predictions if scope == 'overall' or row['mode'] == scope], model)
                            for scope in ('overall', 'apply', 'transfer')} for model in MODELS},
        'predictions': predictions,
    }
