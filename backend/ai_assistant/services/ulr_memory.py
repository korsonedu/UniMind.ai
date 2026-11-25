"""Extract memory from a specific, persisted question and completed answer."""
from hashlib import blake2b

from django.db import connection, transaction
from rest_framework.exceptions import PermissionDenied

from notes.context import conversation_uses_notes
from ai_engine.observability import observe_background
from users.feature_access import has_learning_feature
from ..models import AIChatMessage, Conversation, MemoryExtractionLog, MemoryWriteState, PendingMemoryExtraction
from .dsh_tasks import MEMORY_EXTRACTION_SCHEMA
from .fact_evidence import active as fact_evidence_active
from .memory_core import fact_write_revision
from .memory_service import _build_dsh_extraction_prompt, _memory_message_hash, _merge_memory_candidates
from .ulr_outbox import consume_job, publish_after_commit, publish_job
from .ulr_structured import run_collector


def schedule_memory_extraction(question_id, answer_id):
    if not AIChatMessage.objects.filter(pk=answer_id, role='assistant',
            metadata__learning_turn__message_id=question_id, metadata__learning_turn__completed=True).exists():
        return
    job, _ = PendingMemoryExtraction.objects.get_or_create(
        answer_message_id=answer_id, defaults={'source_message_id': question_id},
    )
    publish_after_commit(publish_memory_extraction, job.pk)


def publish_memory_extraction(job_id):
    from ..tasks import extract_memory_turn

    return publish_job(PendingMemoryExtraction.objects.filter(pk=job_id), lambda job:
        extract_memory_turn.apply_async((job.source_message_id, job.answer_message_id), {'pending_job_id': job.pk},
                                        retry=False, ignore_result=True))


def extract_pending_memory(job_id, question_id, answer_id):
    jobs = PendingMemoryExtraction.objects.filter(pk=job_id, source_message_id=question_id, answer_message_id=answer_id)
    # An older delivery for the same question may already hold the extraction lock.
    return consume_job(jobs, lambda job, _:
        extract_answer_memory(job.source_message_id, job.answer_message_id, redelivered=True),
        retry_provider_failure=True) or 0


def question_for_answer(question_id, answer_id, *, lock=False):
    messages = AIChatMessage.objects.select_related('user', 'bot')
    if lock:
        messages = messages.select_for_update(of=('self',))
    question = messages.filter(pk=question_id, role='user').first()
    if (not question or not question.bot or not question.bot.is_xiaoyu or not question.bot.is_active
            or not question.user.is_active or not question.content.strip()):
        return None
    if not messages.filter(pk=answer_id, role='assistant', user_id=question.user_id, bot_id=question.bot_id,
                           conversation_id=question.conversation_id, metadata__learning_turn__message_id=question_id,
                           metadata__learning_turn__completed=True).exists():
        return None
    try:
        allowed = (has_learning_feature(question.user, 'ai.assistant')
                   and has_learning_feature(question.user, 'full.report'))
    except PermissionDenied:
        return None
    if not allowed:
        return None
    if conversation_uses_notes(question.user, question.conversation_id):
        return None
    return question


def extract_answer_memory(question_id, answer_id, *, redelivered=False):
    original = question_for_answer(question_id, answer_id)
    if original is None:
        return 0
    conversations = Conversation.objects.filter(user_id=original.user_id, bot_id=original.bot_id,
                                                 conversation_id=original.conversation_id)
    conversation_pk = conversations.values_list('pk', flat=True).first()
    if conversation_pk is None:
        return 0
    message_hash = _memory_message_hash(original.content)
    identity = {'user_id': original.user_id, 'conversation_id': str(original.conversation_id), 'message_hash': message_hash}
    records = MemoryExtractionLog.objects.filter(**identity)
    postgres = connection.vendor == 'postgresql'
    if postgres:
        digest = blake2b(f'{conversation_pk}:{message_hash}'.encode(), digest_size=8, person=b'ulr-memory').digest()
        key = int.from_bytes(digest, 'big', signed=True)
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_try_advisory_lock(%s)', [key])
            if not cursor.fetchone()[0]:
                if not redelivered:
                    return 0
                cursor.execute('SELECT pg_advisory_lock(%s)', [key])
    try:
        current = question_for_answer(question_id, answer_id)
        if current is None or current.content != original.content or records.exists():
            return 0
        write_revision = fact_write_revision(current.user) if fact_evidence_active() else None
        with observe_background('ulr', f'memory:{current.conversation_id}',
                                source_message_id=question_id, answer_message_id=answer_id):
            result = run_collector(_build_dsh_extraction_prompt([{'role': 'user', 'content': current.content}]),
                operation='assistant.memory_extract', name='submit_memories',
                instruction='只提交用户明确陈述的长期事实及原话。没有明确依据时返回空列表。',
                schema=MEMORY_EXTRACTION_SCHEMA, max_tokens=800, temperature=0.2)
        candidates = result['memories']
        with transaction.atomic():
            if not conversations.filter(pk=conversation_pk).select_for_update().exists():
                return 0
            current = question_for_answer(question_id, answer_id, lock=True)
            if current is None or current.content != original.content:
                return 0
            log, created = MemoryExtractionLog.objects.get_or_create(**identity, defaults={
                'source_message_id': question_id, 'answer_message_id': answer_id, 'candidate_count': len(candidates),
            })
            if not created:
                return 0
            if write_revision is None or MemoryWriteState.objects.select_for_update().get(
                    user_id=current.user_id).revision == write_revision:
                log.saved_count = _merge_memory_candidates(current.user, candidates, current.content,
                    identity['conversation_id'], ulr=True, write_revision=write_revision, question=current)
            log.save(update_fields=['saved_count'])
            return log.saved_count
    finally:
        if postgres:
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_advisory_unlock(%s)', [key])
