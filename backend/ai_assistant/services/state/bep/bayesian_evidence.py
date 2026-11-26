"""BEP prototype: evidence-weighted grid Bayes, conditional on fixed assumptions.

Theta describes performance on comparable tasks, not a validated mastery score.
The uniform-mixture drift expresses staleness, not an estimated forgetting rate.
"""
from datetime import datetime
from math import log


ALGORITHM_VERSION = 'bep-0.1'
GRID = tuple((index + .5) / 20 for index in range(20))
GUESS = .15
SLIP = .05
STALE_HALF_LIFE_DAYS = 90
ASSISTANCE_WEIGHTS = {'independent': 1., 'hint': .35, 'guided': 0., 'unknown': 0.}


def _time(value):
    value = datetime.fromisoformat(value) if isinstance(value, str) else value
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('BEP observation times must include a timezone.')
    return value


def _entropy(probabilities):
    return -sum(p * log(p) for p in probabilities if p > 0)


def _updated(posterior, likelihoods, weight=1.):
    values = [p * likelihood ** weight for p, likelihood in zip(posterior, likelihoods)]
    total = sum(values)
    return [value / total for value in values]


def _quantile(posterior, quantile):
    cumulative = 0.
    for theta, probability in zip(GRID, posterior):
        cumulative += probability
        if cumulative + 1e-12 >= quantile:
            return theta
    return GRID[-1]


def _drift(posterior, days):
    retained = 2 ** (-max(0., days) / STALE_HALF_LIFE_DAYS)
    return [retained * p + (1 - retained) / len(GRID) for p in posterior]


def belief(observations, now):
    """Replay chronological evidence and return conditional estimates plus next-probe IG.

    Caller validates task provenance, assistance and outcomes, and removes repeated
    evidence. Information gain assumes the same fixed independent-task likelihood.
    """
    now = _time(now)
    posterior = [1 / len(GRID)] * len(GRID)
    success = [GUESS + (1 - GUESS - SLIP) * theta for theta in GRID]
    failure = [1 - probability for probability in success]
    effective_count = 0.
    independent_count = 0
    last_observed = None
    for observation in observations:
        outcome = observation['outcome']
        weight = ASSISTANCE_WEIGHTS.get(observation['assistance'], 0.)
        if outcome not in ('success', 'failure') or not weight:
            continue
        at = _time(observation['at'])
        if last_observed is not None:
            posterior = _drift(posterior, (at - last_observed).total_seconds() / 86400)
        posterior = _updated(posterior, success if outcome == 'success' else failure, weight)
        effective_count += weight
        independent_count += observation['assistance'] == 'independent'
        last_observed = at
    stale_days = max(0., (now - last_observed).total_seconds() / 86400) if last_observed else None
    if stale_days is not None:
        posterior = _drift(posterior, stale_days)
    predicted_success = sum(p * likelihood for p, likelihood in zip(posterior, success))
    information_gain = _entropy(posterior) - (
        predicted_success * _entropy(_updated(posterior, success)) +
        (1 - predicted_success) * _entropy(_updated(posterior, failure)))
    return {
        'mean': sum(theta * p for theta, p in zip(GRID, posterior)),
        'predicted_success': predicted_success,
        'interval': [_quantile(posterior, .1), _quantile(posterior, .9)],
        'effective_count': round(effective_count, 6),
        'independent_count': independent_count,
        'last_observed_at': last_observed.isoformat() if last_observed else None,
        'information_gain': max(0., information_gain),
        'stale_days': stale_days,
    }
