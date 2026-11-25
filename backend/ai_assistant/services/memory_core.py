"""Canonical personal facts, shared by DSH, legacy prompts and user controls."""
import hashlib
import json
import math

from django.db import transaction
from django.db.models import F
from django.dispatch import Signal
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from ai_assistant.models import AgentMemory, MemoryWriteState

reply_completed = Signal()
project_context_prepared = Signal()


def prism_active():
    from django.conf import settings
    return getattr(settings, 'UNIMIND_PRISM_MODE', 'off') == 'active'


def semantic_writes_allowed():
    from django.conf import settings
    from .fact_evidence import active
    return not (active() or prism_active() or getattr(settings, 'UNIMIND_DSH_MEMORY_ENABLED', False)
                or getattr(settings, 'UNIMIND_DSH_GENERATION_ENABLED', False))


def active_facts(user, *, include_inactive=False):
    rows = AgentMemory.objects.filter(user=user)
    if not include_inactive:
        rows = rows.filter(is_active=True)
    from .fact_evidence import active
    # Legacy teaching instructions are not autobiographical facts. Keep user edits.
    return rows.exclude(source='auto', key__startswith='experience:') if prism_active() or active() else rows


def fact_snapshot(user, *, project=None, now=None):
    from . import fact_evidence
    if fact_evidence.active():
        snapshot = fact_evidence.current(user, project=project, now=now)
        snapshot['items'] = snapshot['items'][:20]
        text = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=str)
        return {'version': hashlib.sha256(text.encode()).hexdigest(), **snapshot}
    # This exact ordering/serialization is also the existing DSH concurrency token.
    rows = list(active_facts(user).order_by('-confidence', '-updated_at', 'id').values(
        'id', 'memory_type', 'key', 'value', 'source', 'updated_at')[:20])
    text = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str)
    return {'version': hashlib.sha256(text.encode()).hexdigest(), 'items': rows}


def question_facts(user, context=None):
    """Use the same verified conversation scope across all model readers."""
    from .fact_evidence import active
    project = None
    if active() and context:
        from ai_assistant.models import AIChatMessage, Conversation
        question = AIChatMessage.objects.filter(pk=context.get('message_id'), user=user, role='user',
            bot_id=context.get('bot_id'), conversation_id=context.get('conversation_id')).first()
        if question:
            conversation = Conversation.objects.select_related('project').filter(user=user,
                conversation_id=question.conversation_id, project__user=user).first()
            project = conversation.project if conversation else None
    return fact_snapshot(user, project=project)


def fact_prompt(user, limit=10, *, chat_context=None):
    from . import fact_evidence
    if fact_evidence.active():
        snapshot = question_facts(user, chat_context)
        view = {'items': snapshot['items'][:limit], 'unavailable': snapshot['unavailable']}
        return ('## 用户记忆\n' + json.dumps(view, ensure_ascii=False, default=str) + '\n'
            + fact_evidence.CONTEXT_POLICY) if view['items'] or view['unavailable'] else ''
    rows = active_facts(user).order_by('-confidence', '-use_count', '-updated_at')[:limit]
    lines, used, size = [], [], 0
    for row in rows:
        source = '用户设置' if row.source == 'manual' else '历史对话'
        line = f'- {row.key}：{row.value}（来源：{source}）'
        if size + len(line) > 800:
            break
        lines.append(line)
        used.append(row.pk)
        size += len(line)
    if used:
        active_facts(user).filter(pk__in=used).update(use_count=F('use_count') + 1, last_used_at=timezone.now())
    return '## 用户记忆\n以下是关于该用户的已知信息，请在回答中参考：\n' + '\n'.join(lines) if lines else ''


@transaction.atomic
def invalidate_fact_writes(user_id):
    MemoryWriteState.objects.get_or_create(user_id=user_id)
    state = MemoryWriteState.objects.select_for_update().get(user_id=user_id)
    state.revision += 1
    state.save(update_fields=['revision'])


def fact_write_revision(user):
    return MemoryWriteState.objects.get_or_create(user=user)[0].revision


@transaction.atomic
def merge_fact(user, *, memory_type, key, value, confidence, source, evidence='', conversation_id='', write_revision=None):
    """Atomic automatic merge; user edits and disabled facts always take priority."""
    if memory_type not in dict(AgentMemory.MEMORY_TYPES) or not key or not value:
        return 0
    if not math.isfinite(confidence) or not 0 <= confidence <= 1:
        return 0
    if write_revision is not None:
        state = MemoryWriteState.objects.select_for_update().get(user=user)
        if state.revision != write_revision:
            return 0
    values = {'value': value, 'confidence': confidence, 'source': source,
              'evidence': evidence, 'source_conversation_id': conversation_id or ''}
    row, created = AgentMemory.objects.get_or_create(user=user, memory_type=memory_type, key=key, defaults=values)
    if created:
        return 1
    # Conditional update prevents a late extraction overwriting a concurrent user edit.
    return AgentMemory.objects.filter(pk=row.pk, user=user, is_active=True, confidence__lt=confidence).exclude(
        source='manual').update(**values, updated_at=timezone.now())


@transaction.atomic
def save_manual_fact(data, instance=None):
    from .fact_evidence import active, current
    update_time = True
    if active():
        if not data and instance is not None:
            return instance
        if 'confidence' in data and (not math.isfinite(data['confidence']) or not 0 <= data['confidence'] <= 1):
            raise ValidationError({'confidence': '置信度需要处于0至1之间。'})
        values = dict(data)
        user = instance.user if instance else data['user']
        invalidate_fact_writes(user.pk)
        content_edit = instance is None or bool({'key', 'value', 'memory_type', 'confidence'} & data.keys())
        update_time = content_edit
        if content_edit:
            if instance:
                known = next((row for row in current(user, include_inactive=True)['items'] if row['id'] == instance.pk), None)
                if 'value' not in values and known is None:
                    raise ValidationError({'value': '当前没有有效记忆值，请填写要保存的内容。'})
                if known:
                    values = {'value': known['value'], 'confidence': known['confidence'], **values}
            values.update(source='manual', evidence='', source_conversation_id='')
    else:
        values = {**data, 'source': 'manual', 'evidence': '', 'source_conversation_id': ''}
    if instance is None:
        return AgentMemory.objects.create(**values)
    rows = AgentMemory.objects.filter(pk=instance.pk, user_id=instance.user_id)
    if update_time:
        values['updated_at'] = timezone.now()
    if not rows.update(**values):
        raise NotFound('这条记忆已删除。')
    return rows.get()


def record_completed_reply(reply):
    """One completion entry point for DSH, polling, SSE and WebSocket."""
    if reply.metadata.get('prism_clarification'):
        return
    from .teaching_sidecar import observe, record_turn_completion
    from .prism_memory import mode, safely, schedule
    observe(record_turn_completion, reply)
    turn = reply.metadata.get('learning_turn', {})
    if reply.role == 'assistant' and turn.get('completed') and reply.content.strip():
        from .fact_evidence import active
        if active():
            from .method_adoption import record_completion
            observe(record_completion, reply)
        observe(reply_completed.send, sender=type(reply), reply=reply)
    if mode() == 'off' or reply.role != 'assistant' or not turn.get('completed') or not reply.content.strip():
        return
    from ai_assistant.models import AIChatMessage
    question = AIChatMessage.objects.filter(pk=turn.get('message_id'), user_id=reply.user_id,
        bot_id=reply.bot_id, conversation_id=reply.conversation_id, role='user').select_related('user', 'bot').first()
    if question:
        safely(schedule, question, reply)
