"""Observational RSI sidecar. No candidate activation or teaching-effect claims."""
import hashlib
import json
import logging
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from ai_assistant.models import (
    AIChatMessage, Conversation, LearningStrategy, LearningStrategyOutcome,
    LearningStrategyUse, LearningStrategyVersion, ProjectLearningEvent,
    TaskMemoryObject, TeachingDecisionLog, TeachingMechanismVersion,
)
from users.feature_access import has_learning_feature

logger = logging.getLogger(__name__)
PRESENTATION_SURFACES = ('chat_card', 'hint_reply', 'recheck_card', 'practice_card')
SCHEMA = 'rsi-sidecar-6ab-v1'
SOURCES = {
    'G': ['prompts/ai_assistant/bots/xiaoyu/project_learning.txt',
          'prompts/ai_assistant/bots/xiaoyu/dsh_system_prompt.txt',
          'ai_assistant/services/project_learning.py', 'ai_assistant/services/dsh_service.py',
          'ai_assistant/services/ulr_runtime.py', 'ai_assistant/services/ulr_tool_program.py',
          'ai_assistant/services/ulr_capabilities.py', 'ai_assistant/services/public_methods.py'],
    'S': ['ai_assistant/services/learning_library.py', 'ai_assistant/services/bayesian_evidence.py',
          'ai_assistant/services/ulr_teaching.py', 'ai_assistant/services/public_methods.py',
          'ai_assistant/services/method_adoption.py', 'ai_assistant/services/rsi_policy.py',
          'ai_assistant/services/rsi_evidence.py'],
    'E': ['prompts/quizzes/grading_prompt.txt', 'ai_assistant/services/learning_guidance.py',
          'ai_assistant/services/learning_task_evidence.py', 'ai_assistant/services/learning_tasks.py',
          'quizzes/services/ai_task_service.py', 'quizzes/services/question_generator.py',
          'ai_assistant/services/dsh_tasks.py', 'ai_assistant/services/dsh_generation.py',
          'ai_assistant/services/ulr_grading.py', 'ai_assistant/services/ulr_structured.py',
          'ai_assistant/services/learning_diagnostics.py'],
    'M': ['ai_assistant/services/teaching_sidecar.py', 'ai_assistant/services/teaching_shadow.py',
          'ai_assistant/services/rsi_dataset.py'],
}
SDTM_SOURCES = [
    'ai_assistant/services/task_memory_store.py', 'ai_assistant/services/task_memory_projection.py',
    'ai_assistant/services/learning_continuity.py', 'ai_assistant/services/fact_evidence.py',
    'ai_assistant/services/prism_kernel.py', 'ai_assistant/services/prism_memory.py',
    'ai_assistant/services/prism_feedback.py', 'ai_assistant/services/memory_core.py',
    'ai_assistant/services/prism_outcomes.py',
]


def canonical_hash(value, *, default=None):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False, default=default).encode()).hexdigest()


def observe(callback, *args, **kwargs):
    """An observation failure must not roll back a completed teaching operation."""
    try:
        with transaction.atomic():
            return callback(*args, **kwargs)
    except Exception as exc:
        logger.warning('rsi_observation_error action=%s error_type=%s',
                       getattr(callback, '__name__', type(callback).__name__), type(exc).__name__)
        return None


def _store_mechanism(kind, content, owner, parent):
    if kind not in SOURCES or not isinstance(content, dict) or not content:
        raise ValidationError('教学机制类型或内容无效。')
    if parent and (parent.kind != kind or parent.owner_id not in (None, owner.pk if owner else None)):
        raise PermissionDenied('不能引用其他人的机制版本。')
    digest = canonical_hash({'schema': SCHEMA, 'kind': kind, 'owner': owner.pk if owner else None,
                             'parent': parent.digest if parent else None, 'content': content})
    row, _ = TeachingMechanismVersion.objects.get_or_create(digest=digest,
        defaults={'kind': kind, 'owner': owner, 'parent': parent, 'content': content})
    return row


def register_mechanism(kind, content, *, owner=None, parent=None):
    if owner is None or not owner.is_active:
        raise PermissionDenied('影子研究机制必须归属有效的个人账号。')
    return _store_mechanism(kind, content, owner, parent)


def current_bundle():
    from ai_engine.config import get_model_for_task
    from .ulr_config import ulr_enabled

    models = {key: get_model_for_task(operation)['model'] for key, operation in
              [('chat', 'assistant.chat.planner'), ('grade', 'quizzes.grade')]}
    prism_mode = settings.UNIMIND_PRISM_MODE
    task_memory_mode = settings.UNIMIND_SDTM_TASK_MEMORY_MODE
    routes = {key: bool(getattr(settings, key, False)) for key in
              ('UNIMIND_DSH_GENERATION_ENABLED', 'UNIMIND_DSH_GRADING_ENABLED', 'UNIMIND_DSH_XIAOYU_ENABLED')}
    routes.update(ulr_enabled=ulr_enabled(), ulr_recheck_strategy=settings.UNIMIND_ULR_RECHECK_STRATEGY,
                  prism_mode=prism_mode, sdtm_task_memory_mode=task_memory_mode,
                  sdtm_structured_diagnostics=settings.UNIMIND_SDTM_STRUCTURED_DIAGNOSTICS,
                  rsi_online_policy_mode=settings.UNIMIND_RSI_ONLINE_POLICY_MODE,
                  rsi_exploration_rate=settings.UNIMIND_RSI_EXPLORATION_RATE)
    root = Path(settings.BASE_DIR)
    model_config_hash = hashlib.sha256((root / 'ai_engine/config.py').read_bytes()).hexdigest()
    bundle = {}
    for kind, paths in SOURCES.items():
        role = 'existing_runtime_descriptor'
        if kind == 'M':
            mode = 'active' if 'active' in (prism_mode, task_memory_mode) else (
                prism_mode if prism_mode != 'off' else task_memory_mode)
            role = 'observational_sidecar' if mode == 'off' else f'sdtm_{mode}'
            if mode != 'off':
                paths = [*paths, *SDTM_SOURCES]
        content = {'schema': SCHEMA, 'role': role,
                   'selection': 'model_directed_nonrandom' if kind == 'S' else None,
                   'sources': {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in paths},
                   'models': models, 'provider_weights_pinned': False, 'candidate_activation': False,
                   'routes': routes, 'model_config_hash': model_config_hash}
        if kind == 'M' and prism_mode != 'off':
            content.update(prism_mode=prism_mode, reference_activation='reviewed_only')
        row = _store_mechanism(kind, content, None, None)
        bundle[kind] = {'id': row.pk, 'digest': row.digest}
    return bundle


@transaction.atomic
def freeze_turn(project, message, snapshot):
    if message.user_id != project.user_id or message.role != 'user' or not Conversation.objects.filter(
            user_id=project.user_id, project=project, conversation_id=message.conversation_id).exists():
        raise PermissionDenied('当前教学提问不属于本人项目。')
    metadata = AIChatMessage.objects.select_for_update().values_list('metadata', flat=True).get(pk=message.pk)
    if frozen := metadata.get('rsi_sidecar'):
        return frozen
    if AIChatMessage.objects.filter(user_id=message.user_id, bot_id=message.bot_id,
            conversation_id=message.conversation_id, role='assistant',
            metadata__learning_turn__message_id=message.pk).exists():
        return None  # Do not instrument an already completed historical turn retroactively.
    frozen = {'schema': SCHEMA, 'mode': 'observational', 'project_id': project.pk,
              'bundle': current_bundle(), 'context_hash': canonical_hash(snapshot),
              'frozen_at': timezone.now().isoformat()}
    message.metadata = {**metadata, 'rsi_sidecar': frozen}
    message.save(update_fields=['metadata'])
    return frozen


def method_snapshot(strategy):
    if not strategy.source_event.message_id or strategy.source_event.message.user_id != strategy.user_id:
        raise ValidationError('教学方法原始依据已不可用。')
    source = strategy.source_event
    snapshot = {'method': str(source.content.get('strategy', '')), 'domain': strategy.domain,
                'topic': strategy.topic, 'source_event_id': source.pk,
                'source_message_id': source.message_id, 'context': source.content.get('context', {})}
    snapshot['source_message_hash'] = canonical_hash(source.message.content)
    snapshot['source_event_hash'] = canonical_hash(source.content)
    if not snapshot['method'].strip():
        raise ValidationError('教学方法内容为空。')
    return snapshot


def ensure_method_version(strategy):
    strategy = LearningStrategy.objects.select_related('source_event__message').get(pk=strategy.pk)
    snapshot = method_snapshot(strategy)
    generator_id = (strategy.source_event.message.metadata.get('rsi_sidecar', {}).get('bundle', {}).get('G') or {}).get('id')
    generator = TeachingMechanismVersion.objects.filter(pk=generator_id, kind='G', owner__isnull=True).first()
    row, _ = LearningStrategyVersion.objects.get_or_create(strategy=strategy, digest=canonical_hash(snapshot),
        defaults={'snapshot': snapshot, 'generator': generator})
    return row


def record_strategy_use(use, *, created):
    if not created or use.decision:
        return
    use = LearningStrategyUse.objects.select_related('strategy__source_event', 'message', 'project').get(pk=use.pk)
    validate_strategy_use(use.project, use.pk, pending_message_id=use.message_id)
    version = use.method_version or ensure_method_version(use.strategy)
    frozen = use.message.metadata.get('rsi_sidecar')
    eligible = []
    from .project_learning import unconfirmed_progress_ids
    candidates = (LearningStrategy.objects.filter(user_id=use.project.user_id, is_retired=False,
            source_event__message__isnull=False).exclude(source_event_id__in=unconfirmed_progress_ids(use.project.user_id))
            .select_related('source_event__message').order_by('pk'))
    for strategy in candidates:
        candidate = ensure_method_version(strategy)
        eligible.append({'strategy_id': strategy.pk, 'version_id': candidate.pk, 'digest': candidate.digest})
    use.method_version = version
    use.decision = {'schema': SCHEMA, 'status': 'observed' if frozen else 'unobserved_turn',
                    'decision_id': use.pk,
                    'selection_kind': 'model_directed_nonrandom', 'propensity': None,
                    'mechanisms': frozen, 'eligible_candidates': eligible,
                    'model_visible_candidate_set': 'not_inferred_from_eligibility',
                    'selected_version_id': version.pk, 'selected_digest': version.digest,
                    'prediction': None, 'prediction_status': 'not_recorded',
                    'assigned_at': use.created_at.isoformat()}
    log = TeachingDecisionLog.objects.filter(message=use.message, project=use.project,
        owner_id=use.project.user_id, decision_point='method_ranking').first()
    if log:
        from .rsi_policy import method_assignment
        use.decision.update(model_visible_candidate_set=log.candidates, decision_log_id=log.pk)
        candidate = method_assignment(log, kind='private', method_id=use.strategy_id, method_digest=version.digest)
        if candidate and candidate['action'] == log.selected_action and log.propensity is not None:
            use.decision.update(propensity=log.propensity, selection_kind=log.selection_mode)
    from .memory_core import prism_active
    if prism_active():
        from .prism_memory import context
        packet = context(use.message)
        if packet:
            use.decision['prism'] = {'status': 'retrieved_not_usage_proof',
                'methods': [{key: entry[key] for key in ('id', 'revision', 'version')} for entry in packet['methods']],
                'memories': [{key: entry[key] for key in ('key', 'revision', 'scope')} for entry in packet['memories']]}
    use.exposure = {'status': 'assigned', 'adherence': 'unverified'}
    use.save(update_fields=['method_version', 'decision', 'exposure'])


def record_tool_result(user, context, name, arguments, result, channel=None):
    if not context:
        return
    message = AIChatMessage.objects.select_for_update().filter(pk=context.get('message_id'), user=user,
        role='user', bot_id=context.get('bot_id'), conversation_id=context.get('conversation_id')).first()
    if not message or not message.metadata.get('rsi_sidecar'):
        return
    project_id = message.metadata['rsi_sidecar']['project_id']
    if not Conversation.objects.filter(user=user, project_id=project_id, project__user=user,
                                       conversation_id=message.conversation_id).exists():
        return
    # Project commits can carry datetimes before the shared tool executor serializes them.
    entry = {'tool': name, 'arguments_hash': canonical_hash(arguments),
             'result_hash': canonical_hash(result, default=str)}
    if channel is not None:
        entry['channel'] = channel
    entries = message.metadata.get('rsi_observations', [])
    if entry not in entries:
        entries.append(entry)
        message.metadata['rsi_observations'] = entries
        message.save(update_fields=['metadata'])


def _presentation_exposure(receipt):
    return {'status': 'presented', 'presentation': 'presented', 'presented_at': receipt['presented_at'],
            'presentation_surface': receipt['surface'], 'adherence': 'unverified'}


@transaction.atomic
def record_turn_completion(reply):
    reply = AIChatMessage.objects.select_for_update().filter(pk=reply.pk, role='assistant').first()
    if not reply:
        return
    turn = reply.metadata.get('learning_turn', {})
    if not turn.get('completed'):
        return
    trigger = AIChatMessage.objects.filter(pk=turn.get('message_id'), user_id=reply.user_id,
        bot_id=reply.bot_id, conversation_id=reply.conversation_id, role='user').first()
    if not trigger:
        return
    completion = {'status': 'reply_completed', 'reply_id': reply.pk, 'reply_hash': canonical_hash(reply.content),
                  'completed_at': turn.get('completed_at'), 'saved_at': reply.timestamp.isoformat(),
                  'adherence': 'unverified'}
    decisions = TeachingDecisionLog.objects.filter(message=trigger, owner_id=reply.user_id,
        project__user_id=reply.user_id).filter(Q(answer=reply) | Q(answer__isnull=True))
    pending = Q(exposure__status='assigned')
    decision_exposure = {**completion, 'presentation': 'unknown'}
    if receipt := reply.metadata.get('rsi_presentation'):
        # History can expose the saved reply before the completion observer runs.
        pending |= Q(answer=reply, exposure__presentation='presented', exposure__reply_id__isnull=True)
        completion.update(_presentation_exposure(receipt))
        decision_exposure.update(completion, presentation_card_type=receipt['card_type'])
    decisions.filter(pending).update(answer=reply, exposure=decision_exposure)
    from .learning_library import unconfirmed_strategy_use_ids
    uses = LearningStrategyUse.objects.filter(message=trigger, project__user_id=reply.user_id)
    for use in uses.exclude(pk__in=unconfirmed_strategy_use_ids(reply.user_id, uses)):
        if use.decision and use.exposure.get('status') == 'assigned':
            use.exposure = {**completion, 'engine': reply.metadata.get('engine')}
            if action := (reply.metadata.get('ulr_teaching') or {}).get('action'):
                use.exposure['ulr_teaching_action'] = action
            use.save(update_fields=['exposure'])


def record_exposure_presentation(user, *, message_id, surface='chat_card', card_type=''):
    if not user.is_authenticated or not has_learning_feature(user, 'ai.assistant'):
        raise PermissionDenied()
    if surface not in PRESENTATION_SURFACES:
        raise ValidationError({'surface': '无效的学习回复呈现场景。'})
    if not isinstance(card_type, str) or len(card_type) > 64:
        raise ValidationError({'card_type': '卡片类型须为最多 64 个字符的字符串。'})

    from .learning_library import unconfirmed_strategy_use_ids
    with transaction.atomic():
        reply = AIChatMessage.objects.select_for_update().filter(pk=message_id, user=user, role='assistant',
            metadata__learning_turn__completed=True).first()
        if not reply or not Conversation.objects.filter(user=user, conversation_id=reply.conversation_id).exists():
            raise NotFound('学习回复记录不可用。')

        receipt = reply.metadata.get('rsi_presentation')
        created = receipt is None
        if created:
            receipt = {'status': 'presented', 'presented_at': timezone.now().isoformat(),
                       'surface': surface, 'card_type': card_type}
            reply.metadata['rsi_presentation'] = receipt
        teaching = reply.metadata.get('ulr_teaching')
        mark_teaching = isinstance(teaching, dict) and teaching.get('presentation') == 'unknown'
        if mark_teaching:
            teaching.update(presentation='presented', presented_at=receipt['presented_at'])
        if created or mark_teaching:
            reply.save(update_fields=['metadata'])

        exposure = _presentation_exposure(receipt)
        updated_decisions = 0
        for decision in TeachingDecisionLog.objects.filter(owner=user, answer=reply):
            if decision.exposure.get('presentation') != 'presented':
                decision.exposure.update(exposure, presentation_card_type=receipt['card_type'])
                decision.save(update_fields=['exposure'])
                updated_decisions += 1

        uses = LearningStrategyUse.objects.filter(project__user=user,
            message_id=reply.metadata['learning_turn'].get('message_id'), exposure__reply_id=reply.pk)
        updated_strategy_uses = 0
        for use in uses.exclude(pk__in=unconfirmed_strategy_use_ids(user.pk, uses)):
            if use.exposure.get('presentation') != 'presented':
                use.exposure.update(exposure)
                use.save(update_fields=['exposure'])
                updated_strategy_uses += 1
        return {'message_id': reply.pk, 'status': 'presented', 'presented_at': receipt['presented_at'], 'created': created,
                'updated_decisions': updated_decisions, 'updated_strategy_uses': updated_strategy_uses}


def validate_strategy_use(project, use_id, *, pending_message_id=None):
    from .learning_library import unconfirmed_strategy_use_ids
    from .project_learning import unconfirmed_progress_ids
    uses = LearningStrategyUse.objects.select_related('strategy__source_event__message', 'message').filter(
        pk=use_id, project=project, strategy__user_id=project.user_id, strategy__is_retired=False,
        strategy__source_event__message__user_id=project.user_id, message__user_id=project.user_id).exclude(
            strategy__source_event_id__in=unconfirmed_progress_ids(project.user_id))
    unconfirmed = unconfirmed_strategy_use_ids(project.user_id, uses.exclude(message_id=pending_message_id))
    use = uses.exclude(pk__in=unconfirmed).first()
    if not use or not Conversation.objects.filter(user_id=project.user_id,
            conversation_id=use.message.conversation_id, project=project).exists():
        raise ValidationError('教学方法使用记录已失效或不属于当前项目。')
    return use


def verified_strategy_reply(use):
    reply = AIChatMessage.objects.filter(pk=use.exposure.get('reply_id'), user_id=use.project.user_id,
        bot_id=use.message.bot_id, conversation_id=use.message.conversation_id, role='assistant',
        metadata__learning_turn__message_id=use.message_id, metadata__learning_turn__completed=True).first()
    if not reply:
        return None, None
    completed_at = reply.metadata['learning_turn'].get('completed_at')
    completed = parse_datetime(completed_at or '')
    if (completed and timezone.is_aware(completed) and use.exposure.get('completed_at') == completed_at
            and use.exposure.get('reply_hash') == canonical_hash(reply.content)
            and use.exposure.get('saved_at') == reply.timestamp.isoformat()):
        return reply, completed
    return None, None


def overlapping_public_use(task, assigned_at, submitted_at):
    assignments = TaskMemoryObject.objects.filter(owner_id=task.project.user_id, project=task.project,
        kind='method_use', task=task).values_list('value__assigned_at', flat=True)
    return any(timezone.is_aware(stamp) and assigned_at <= stamp <= submitted_at
               for value in assignments if (stamp := parse_datetime(value or '')))


def record_task_outcome(task, result, event):
    if not task.strategy_use_id or result.status != 'graded':
        return
    from .learning_tasks import task_result_snapshot, task_label_source, task_question_hash, task_prompt_hash, _hash
    use = validate_strategy_use(task.project, task.strategy_use_id)
    question = task_result_snapshot(task, result)  # Current permission and frozen-content revalidation.
    if event.project_id != task.project_id or event.kind != 'assessment' or event.content.get('result_id') != result.pk:
        raise ValidationError('教学观察与原任务结果不一致。')
    expected = {'task_id': str(task.pk), 'question_hash': task_question_hash(question),
                'answer_hash': _hash(result.user_answer.strip()), 'assistance': task.assistance,
                'score': result.score, 'max_score': result.max_score, 'label_source': task_label_source(task, result)}
    if any(event.content.get(key) != value for key, value in expected.items()):
        raise ValidationError('教学观察的原始证据已变化。')
    if use.method_version_id and use.method_version.digest != canonical_hash(method_snapshot(use.strategy)):
        raise ValidationError('教学方法的冻结依据已变化。')
    reply, completed = verified_strategy_reply(use)
    timing = bool(reply and result.graded_at
                  and result.exam.created_at > max(completed, reply.timestamp)
                  and result.exam.created_at >= max(use.created_at, task.created_at)
                  and result.graded_at >= result.exam.created_at)
    from quizzes.models import ExamQuestionResult
    prior = ExamQuestionResult.objects.filter(exam__user_id=task.project.user_id,
        exam__created_at__lt=result.exam.created_at).exclude(pk=result.pk).values('question_id', 'question_snapshot')
    repeated = any((result.question_id is not None and row['question_id'] == result.question_id)
        or (row['question_snapshot'].get('text') and task_prompt_hash(row['question_snapshot']) == task_prompt_hash(question))
        for row in prior)
    from .learning_library import unconfirmed_strategy_use_ids
    trials = LearningStrategyUse.objects.filter(project=task.project, created_at__gte=use.created_at,
        created_at__lte=result.exam.created_at).exclude(pk=use.pk)
    overlaps = trials.exclude(pk__in=unconfirmed_strategy_use_ids(task.project.user_id, trials)).exists()
    overlaps = overlaps or overlapping_public_use(task, use.created_at, result.exam.created_at)
    from . import learning_diagnostics
    task_id = str(task.pk)
    disclosed = learning_diagnostics.active(task.project_id) and task_id in learning_diagnostics.excluded_tasks(
        learning_diagnostics.read_sources(task.project, {task_id}))
    reasons = []
    if not timing:
        reasons.append('no_completed_prior_teaching')
    if task.assistance != 'independent':
        reasons.append('assistance_not_independent')
    if repeated:
        reasons.append('repeated_question')
    if overlaps:
        reasons.append('overlapping_methods')
    if not use.decision or use.decision.get('status') != 'observed':
        reasons.append('unobserved_assignment')
    if disclosed:
        reasons.append('same_instance_solution_disclosed')
    snapshot = {**expected, 'schema': SCHEMA, 'use_id': use.pk, 'result_id': result.pk,
                'method_version_id': use.method_version_id, 'purpose': task.purpose,
                'question_hash': expected['question_hash'], 'assistance_source': 'submission_report',
                'prompt_hash': task_prompt_hash(question), 'novelty_verified': False,
                'timing_verified': timing, 'repeated': repeated, 'overlapping_methods': overlaps, 'disclosed': disclosed,
                'status': 'uncertain' if reasons else 'independent_reported_observation',
                'reasons': reasons, 'causal_claim': False, 'independent_label_verified': False,
                'exposure': use.exposure, 'graded_at': result.graded_at.isoformat() if result.graded_at else None}
    LearningStrategyOutcome.objects.get_or_create(use=use, result=result,
        defaults={'task': task, 'event': event, 'snapshot': snapshot})
