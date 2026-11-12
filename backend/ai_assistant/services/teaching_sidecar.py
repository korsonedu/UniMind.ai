"""Observational RSI sidecar. No candidate activation or teaching-effect claims."""
import hashlib
import json
import logging
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import PermissionDenied, ValidationError

from ai_assistant.models import (
    AIChatMessage, Conversation, LearningStrategy, LearningStrategyOutcome,
    LearningStrategyUse, LearningStrategyVersion, ProjectLearningEvent,
    TeachingMechanismVersion,
)

logger = logging.getLogger(__name__)
SCHEMA = 'rsi-sidecar-6ab-v1'
SOURCES = {
    'G': ['prompts/ai_assistant/bots/xiaoyu/project_learning.txt',
          'prompts/ai_assistant/bots/xiaoyu/dsh_system_prompt.txt',
          'ai_assistant/services/project_learning.py', 'ai_assistant/services/dsh_service.py'],
    'S': ['ai_assistant/services/learning_library.py', 'ai_assistant/services/bayesian_evidence.py'],
    'E': ['prompts/quizzes/grading_prompt.txt', 'ai_assistant/services/learning_guidance.py',
          'ai_assistant/services/learning_task_evidence.py', 'ai_assistant/services/learning_tasks.py',
          'quizzes/services/ai_task_service.py', 'quizzes/services/question_generator.py',
          'ai_assistant/services/dsh_tasks.py', 'ai_assistant/services/dsh_generation.py'],
    'M': ['ai_assistant/services/teaching_sidecar.py'],
}


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def observe(callback, *args, **kwargs):
    """An observation failure must not roll back a completed teaching operation."""
    try:
        with transaction.atomic():
            return callback(*args, **kwargs)
    except Exception as exc:
        logger.warning('rsi_observation_error action=%s error_type=%s', callback.__name__, type(exc).__name__)
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
    models = {key: get_model_for_task(operation)['model'] for key, operation in
              [('chat', 'assistant.chat.planner'), ('grade', 'quizzes.grade')]}
    bundle = {}
    for kind, paths in SOURCES.items():
        content = {'schema': SCHEMA, 'role': 'reserved_not_running' if kind == 'M' else 'existing_runtime_descriptor',
                   'selection': 'model_directed_nonrandom' if kind == 'S' else None,
                   'sources': {path: hashlib.sha256((Path(settings.BASE_DIR) / path).read_bytes()).hexdigest()
                               for path in paths},
                   'models': models, 'provider_weights_pinned': False, 'candidate_activation': False}
        content['routes'] = {key: bool(getattr(settings, key, False)) for key in
            ('UNIMIND_DSH_GENERATION_ENABLED', 'UNIMIND_DSH_GRADING_ENABLED', 'UNIMIND_DSH_XIAOYU_ENABLED')}
        content['model_config_hash'] = hashlib.sha256((Path(settings.BASE_DIR) / 'ai_engine/config.py').read_bytes()).hexdigest()
        row = _store_mechanism(kind, content, None, None)
        bundle[kind] = {'id': row.pk, 'digest': row.digest}
    return bundle


def freeze_turn(project, message, snapshot):
    if message.user_id != project.user_id or message.role != 'user' or not Conversation.objects.filter(
            user_id=project.user_id, project=project, conversation_id=message.conversation_id).exists():
        raise PermissionDenied('当前教学提问不属于本人项目。')
    if message.metadata.get('rsi_sidecar'):
        return message.metadata['rsi_sidecar']
    if AIChatMessage.objects.filter(user_id=message.user_id, bot_id=message.bot_id,
            conversation_id=message.conversation_id, role='assistant',
            metadata__learning_turn__message_id=message.pk).exists():
        return None  # Do not instrument an already completed historical turn retroactively.
    frozen = {'schema': SCHEMA, 'mode': 'observational', 'project_id': project.pk,
              'bundle': current_bundle(), 'context_hash': canonical_hash(snapshot),
              'frozen_at': timezone.now().isoformat()}
    message.metadata['rsi_sidecar'] = frozen
    message.save(update_fields=['metadata'])
    return frozen


def _method_snapshot(strategy):
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
    snapshot = _method_snapshot(strategy)
    generator_id = (strategy.source_event.message.metadata.get('rsi_sidecar', {}).get('bundle', {}).get('G') or {}).get('id')
    generator = TeachingMechanismVersion.objects.filter(pk=generator_id, kind='G', owner__isnull=True).first()
    row, _ = LearningStrategyVersion.objects.get_or_create(strategy=strategy, digest=canonical_hash(snapshot),
        defaults={'snapshot': snapshot, 'generator': generator})
    return row


def record_strategy_use(use, *, created):
    if not created or use.decision:
        return
    use = LearningStrategyUse.objects.select_related('strategy__source_event', 'message', 'project').get(pk=use.pk)
    validate_strategy_use(use.project, use.pk)
    version = ensure_method_version(use.strategy)
    frozen = use.message.metadata.get('rsi_sidecar')
    eligible = []
    for strategy in LearningStrategy.objects.filter(user_id=use.project.user_id, is_retired=False,
            source_event__message__isnull=False).select_related('source_event__message').order_by('pk'):
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
    use.exposure = {'status': 'assigned', 'adherence': 'unverified'}
    use.save(update_fields=['method_version', 'decision', 'exposure'])


def record_tool_result(user, context, name, arguments, result):
    if not context:
        return
    message = AIChatMessage.objects.select_for_update().filter(pk=context.get('message_id'), user=user,
        role='user', bot_id=context.get('bot_id'), conversation_id=context.get('conversation_id')).first()
    if not message or not message.metadata.get('rsi_sidecar'):
        return
    project_id = message.metadata['rsi_sidecar']['project_id']
    if not Conversation.objects.filter(user=user, project_id=project_id, conversation_id=message.conversation_id).exists():
        return
    entry = {'tool': name, 'arguments_hash': canonical_hash(arguments), 'result_hash': canonical_hash(result)}
    entries = message.metadata.get('rsi_observations', [])
    if entry not in entries:
        entries.append(entry)
        message.metadata['rsi_observations'] = entries
        message.save(update_fields=['metadata'])


def record_turn_completion(reply):
    turn = reply.metadata.get('learning_turn', {})
    if reply.role != 'assistant' or not turn.get('completed'):
        return
    trigger = AIChatMessage.objects.filter(pk=turn.get('message_id'), user_id=reply.user_id,
        bot_id=reply.bot_id, conversation_id=reply.conversation_id, role='user').first()
    if not trigger:
        return
    for use in LearningStrategyUse.objects.filter(message=trigger, project__user_id=reply.user_id):
        if use.decision and use.exposure.get('status') == 'assigned':
            use.exposure = {'status': 'reply_completed', 'adherence': 'unverified',
                'reply_id': reply.pk, 'reply_hash': canonical_hash(reply.content),
                'completed_at': turn.get('completed_at'), 'saved_at': reply.timestamp.isoformat()}
            use.save(update_fields=['exposure'])


def validate_strategy_use(project, use_id):
    use = LearningStrategyUse.objects.select_related('strategy__source_event__message', 'message').filter(
        pk=use_id, project=project, strategy__user_id=project.user_id, strategy__is_retired=False,
        strategy__source_event__message__user_id=project.user_id, message__user_id=project.user_id).first()
    if not use or not Conversation.objects.filter(user_id=project.user_id,
            conversation_id=use.message.conversation_id, project=project).exists():
        raise ValidationError('教学方法使用记录已失效或不属于当前项目。')
    return use


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
    if use.method_version_id and use.method_version.digest != canonical_hash(_method_snapshot(use.strategy)):
        raise ValidationError('教学方法的冻结依据已变化。')
    reply = AIChatMessage.objects.filter(pk=use.exposure.get('reply_id'), user_id=task.project.user_id,
        bot_id=use.message.bot_id, conversation_id=use.message.conversation_id, role='assistant',
        metadata__learning_turn__message_id=use.message_id, metadata__learning_turn__completed=True).first()
    completed = parse_datetime(reply.metadata['learning_turn'].get('completed_at', '')) if reply else None
    exposure_matches = bool(reply and use.exposure.get('reply_hash') == canonical_hash(reply.content)
        and use.exposure.get('completed_at') == reply.metadata['learning_turn'].get('completed_at')
        and use.exposure.get('saved_at') == reply.timestamp.isoformat())
    timing = bool(exposure_matches and completed and timezone.is_aware(completed) and result.graded_at
                  and result.exam.created_at > max(completed, reply.timestamp)
                  and result.exam.created_at >= max(use.created_at, task.created_at)
                  and result.graded_at >= result.exam.created_at)
    from quizzes.models import ExamQuestionResult
    prior = ExamQuestionResult.objects.filter(exam__user_id=task.project.user_id,
        exam__created_at__lt=result.exam.created_at).exclude(pk=result.pk).values('question_id', 'question_snapshot')
    repeated = any((result.question_id is not None and row['question_id'] == result.question_id)
        or (row['question_snapshot'].get('text') and task_prompt_hash(row['question_snapshot']) == task_prompt_hash(question))
        for row in prior)
    overlaps = LearningStrategyUse.objects.filter(project=task.project, created_at__gte=use.created_at,
        created_at__lte=result.exam.created_at).exclude(pk=use.pk).exists()
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
    snapshot = {**expected, 'schema': SCHEMA, 'use_id': use.pk, 'result_id': result.pk,
                'method_version_id': use.method_version_id, 'purpose': task.purpose,
                'question_hash': expected['question_hash'], 'assistance_source': 'submission_report',
                'prompt_hash': task_prompt_hash(question), 'novelty_verified': False,
                'timing_verified': timing, 'repeated': repeated, 'overlapping_methods': overlaps,
                'status': 'uncertain' if reasons else 'independent_reported_observation',
                'reasons': reasons, 'causal_claim': False, 'independent_label_verified': False,
                'exposure': use.exposure, 'graded_at': result.graded_at.isoformat() if result.graded_at else None}
    LearningStrategyOutcome.objects.get_or_create(use=use, result=result,
        defaults={'task': task, 'event': event, 'snapshot': snapshot})
