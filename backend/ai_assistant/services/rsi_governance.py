"""Explicit platform-admin approval and replay-preserving teaching rollout."""
from sys import float_info
from uuid import uuid4

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from ai_assistant.models import TeachingMechanismActivation, TeachingResearchRun
from users.permissions import is_platform_admin
from . import public_methods


ACTIVE_STATUSES = ('canary_active', 'active')


def _object(value):
    return value if isinstance(value, dict) else {}


def _number(value):
    return type(value) in (int, float) and -float_info.max <= value <= float_info.max


def _at_least(value, minimum):
    return _number(value) and value >= minimum


def evaluate_gate(run_id, *, min_cases=2, min_ess=2.0, max_mae_regression=0.0, min_proxy_gain=0.0,
                  require_attested_anchors=True):
    run = TeachingResearchRun.objects.select_related('baseline', 'candidate', 'project').get(pk=run_id)
    if not all(_at_least(value, 0) for value in (min_cases, min_ess, max_mae_regression, min_proxy_gain)):
        raise ValidationError('Gate thresholds must be finite non-negative numbers.')

    report = _object(run.report)
    checks = {
        'candidate_missing': run.candidate_id is not None,
        'candidate_matches_baseline': run.candidate_id != run.baseline_id,
        'candidate_kind_mismatch': bool(run.candidate_id and run.candidate.kind == run.kind),
        'report_missing': bool(report),
        'unsupported_kind': run.kind in ('G', 'S', 'E'),
    }
    metrics = _object(report.get('metrics'))
    origin = _object(report.get('scope')).get('origin')
    if run.kind in ('G', 'E'):
        candidate = _object(metrics.get('candidate'))
        baseline = _object(metrics.get('baseline'))
        false_support = candidate.get('operator_false_independent_support')
        checks.update(live_model_required=report.get('execution') == 'live_model',
                      incomplete_run=report.get('status') != 'incomplete',
                      false_independent_support=_number(false_support) and false_support == 0)
        if run.kind == 'E':
            anchors = report.get('anchor_validation')
            mae, baseline_mae = candidate.get('operator_anchor_mae'), baseline.get('operator_anchor_mae')
            checks.update(
                unattested_anchors=anchors != 'operator_supplied_not_attested'
                and (not require_attested_anchors or anchors == 'objective_answer_key_verified'),
                insufficient_anchors=_at_least(candidate.get('operator_anchor_count'), min_cases),
                mae_regression=_number(mae) and _number(baseline_mae) and mae <= baseline_mae + max_mae_regression,
            )
        else:
            proxy, baseline_proxy = candidate.get('proxy_mean'), baseline.get('proxy_mean')
            checks.update(
                observational_data_required=origin == 'observational',
                unchanged_instruction=_object(report.get('comparison')).get('candidate_instruction_changed') is True,
                insufficient_completed_cases=_at_least(candidate.get('completed_cases'), min_cases),
                insufficient_proxy_gain=_number(proxy) and _number(baseline_proxy) and proxy >= baseline_proxy + min_proxy_gain,
            )
    elif run.kind == 'S':
        # T5 stores validated replay metrics at the report root and calls the eligible row count "n".
        metrics = metrics or report
        snips, baseline_reward = metrics.get('snips_estimate'), metrics.get('baseline_mean_reward')
        checks.update(
            offline_replay_required=report.get('status') == 'evaluated_offline_replay',
            synthetic_fixture=report.get('execution') != 'synthetic_fixture' and origin != 'synthetic_fixture',
            insufficient_randomized_decisions=_at_least(metrics.get('randomized_decisions', metrics.get('n')), min_cases),
            insufficient_ess=_at_least(metrics.get('effective_sample_size'), min_ess),
            snips_regression=_number(snips) and _number(baseline_reward) and snips >= baseline_reward,
        )
    failures = [code for code, passed in checks.items() if not passed]
    return {'run_id': run.pk, 'kind': run.kind, 'passed': not failures, 'failures': failures, 'checks': checks}


def _summary(activation):
    return {'activation_id': activation.pk, 'run_id': activation.research_run_id, 'kind': activation.kind,
            'scope': activation.scope, 'project_id': activation.project_id, 'decision_point': activation.decision_point,
            'mechanism_id': activation.mechanism_id, 'previous_id': activation.previous_id,
            'published_program_id': activation.published_program_id, 'status': activation.status,
            'gate_report': activation.gate_report, 'approved_by_id': activation.approved_by_id,
            'approved_at': activation.approved_at.isoformat() if activation.approved_at else None,
            'rolled_back_by_id': activation.rolled_back_by_id,
            'rolled_back_at': activation.rolled_back_at.isoformat() if activation.rolled_back_at else None,
            'rollback_reason': activation.rollback_reason}


def _mark_rolled_back(activation, reviewer, now, reason):
    activation.status = 'rolled_back'
    activation.rolled_back_by = reviewer
    activation.rolled_back_at = now
    activation.rollback_reason = reason
    activation.save(update_fields=['status', 'rolled_back_by', 'rolled_back_at', 'rollback_reason'])


def approve_and_activate(run_id, reviewer, *, scope='project_canary', project=None, public_method_spec=None,
                         gate_options=None):
    if not is_platform_admin(reviewer):
        raise PermissionDenied('Teaching mechanism approval requires a platform administrator.')
    if scope not in ('project_canary', 'global'):
        raise ValidationError('Invalid activation scope.')

    with transaction.atomic():
        run = TeachingResearchRun.objects.select_for_update(of=('self',)).select_related(
            'project', 'baseline', 'candidate').get(pk=run_id)
        gate = evaluate_gate(run.pk, **(gate_options or {}))
        if not gate['passed']:
            raise ValidationError(gate['failures'])
        canary = scope == 'project_canary'
        target_project = (project or run.project) if canary else None
        if canary and target_project.pk != run.project_id:
            raise ValidationError('Canary activation must use the research project.')
        if run.kind == 'E' and not canary:
            raise ValidationError('Evaluation mechanisms are project-canary references only.')

        decision_point = ''
        if run.kind == 'S':
            from .rsi_dataset import DECISION_POINTS
            from .rsi_policy import RECHECK_DELAYS, _policy_weights, _target_policy, _exploration_rate

            decision_point = _object(run.protocol).get('decision_point') or run.report.get('decision_point')
            if decision_point not in DECISION_POINTS:
                raise ValidationError('Invalid S decision point.')
            policy = _target_policy(run.candidate)
            actions = RECHECK_DELAYS if decision_point == 'recheck_timing' else policy
            if 'exploration_rate' in _object(policy):
                valid = decision_point == 'method_ranking' and _exploration_rate(policy) is not None
            else:
                valid = _policy_weights(policy, actions) is not None
            if not valid:
                raise ValidationError('Invalid S target policy.')
        elif run.kind == 'G':
            spec = _object(public_method_spec)
            key = spec.get('key')
            if not {'key', 'requires', 'source'} <= spec.keys() or not isinstance(key, str) or not 1 <= len(key.strip()) <= 40:
                raise ValidationError('A reviewed public method key (up to 40 characters), requires and source are required.')
            decision_point = key.strip()

        prior = TeachingMechanismActivation.objects.select_for_update().filter(kind=run.kind, scope=scope,
            project=target_project, decision_point=decision_point, status__in=ACTIVE_STATUSES).first()
        program = None
        if run.kind == 'G':
            request_key = spec.get('request_key', f'rsi_approve:{uuid4()}')
            if not isinstance(request_key, str):
                raise ValidationError('The public method request key must be a string.')
            program = public_methods.publish_method({'key': decision_point, 'requires': spec['requires'],
                'source': spec['source'], 'retired': False, 'instruction': _object(run.candidate.content).get('instruction')},
                request_key=request_key, project_id=target_project.pk if canary else None)
            if program.rsi_activations.exists():
                if prior and prior.published_program_id == program.pk and prior.research_run_id == run.pk:
                    return _summary(prior)
                raise ValidationError('The public method request key was already used for another activation.')
        now = timezone.now()
        activation = TeachingMechanismActivation.objects.create(kind=run.kind, scope=scope, project=target_project,
            decision_point=decision_point, research_run=run, mechanism=run.candidate, previous=prior, published_program=program,
            status='gate_passed', gate_report=gate, approved_by=reviewer, approved_at=now)
        if prior:
            _mark_rolled_back(prior, reviewer, now, f'superseded_by:{activation.pk}')
        activation.status = 'canary_active' if canary else 'active'
        activation.save(update_fields=['status'])
        return _summary(activation)


def rollback_activation(activation_id, reviewer, *, reason='', restore_previous=False):
    if not is_platform_admin(reviewer):
        raise PermissionDenied('Teaching mechanism rollback requires a platform administrator.')
    if not isinstance(reason, str) or len(reason) > 500:
        raise ValidationError('The rollback reason must be a string of at most 500 characters.')

    with transaction.atomic():
        activation = TeachingMechanismActivation.objects.select_for_update(of=('self',)).select_related(
            'previous__published_program', 'published_program').get(pk=activation_id)
        if activation.status not in ACTIVE_STATUSES:
            raise ValidationError('Only an active teaching mechanism can be rolled back.')
        active_status = activation.status
        _mark_rolled_back(activation, reviewer, timezone.now(), reason or 'operator_rollback')
        previous = activation.previous if restore_previous else None
        rollback_program = None
        if activation.kind == 'G':
            if previous and previous.published_program_id:
                program, action = previous.published_program, 'restore'
            else:
                previous = None
                program, action = activation.published_program, 'retire'
            if program:
                definition = {key: value for key, value in program.definition.items() if key not in ('family', 'project_id')}
                rollback_program = public_methods.publish_method({**definition, 'retired': action == 'retire'},
                    request_key=f'rsi_rollback_{action}:{activation.pk}', project_id=activation.project_id)
        if previous:
            previous.status = active_status
            previous.rolled_back_by = previous.rolled_back_at = None
            previous.rollback_reason = ''
            previous.save(update_fields=['status', 'rolled_back_by', 'rolled_back_at', 'rollback_reason'])
        return {**_summary(activation), 'restored_activation_id': previous.pk if previous else None,
                'rollback_program_id': rollback_program.pk if rollback_program else None}


def active_s_policy(project_id, decision_point):
    scope = Q(scope='global', project__isnull=True, status='active')
    if project_id is not None:
        scope |= Q(scope='project_canary', project_id=project_id, status='canary_active')
    return TeachingMechanismActivation.objects.select_related('mechanism').filter(
        scope, kind='S', decision_point=decision_point).order_by('-scope').first()
