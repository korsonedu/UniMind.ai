"""
Synchronous conversation title generation.
Called inline from SSE view after first assistant response completes.
Uses the server DSH task when enabled; otherwise keeps the legacy model path.
"""
import logging
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.exceptions import PermissionDenied

from ai_service import AIService
from ai_engine.observability import observe_background

logger = logging.getLogger(__name__)

TITLE_MAX_CHARS = 80


def _fallback_title(user_msg):
    """Deterministic short title when the DSH task is unavailable."""
    from .language import message_language
    limit = TITLE_MAX_CHARS if message_language(user_msg) == 'en' else 15
    return ' '.join(str(getattr(user_msg, 'content', '') or '').split())[:limit]


def _generate_title_via_dsh(prompt):
    from ai_assistant.services.dsh_tasks import run_structured

    result = run_structured('assistant.title', prompt)
    if not isinstance(result, dict):
        return ''
    return str(result.get('title') or '').strip()[:TITLE_MAX_CHARS]


def _authorized_title_inputs(messages, user_msg, assistant_msg, *, lock_transcripts=False):
    from notes.context import prepare_note_context
    from users.permissions import has_capability
    from .course_context import current_transcript_sources
    from .ulr_capabilities import visible_course_ids, visible_practice_review_sources
    from .ulr_history import (
        SOURCE_FIELDS, bound_practice_answers, legacy_transcript_excerpts, match_legacy_transcript_excerpts,
        reply_practice_reviews, reply_question_answers, reply_sources, reply_transcript_sources,
    )

    rows = {row['pk']: row for row in messages.filter(pk__in=[user_msg.pk, assistant_msg.pk])
            .values('pk', 'content', **SOURCE_FIELDS)}
    question, answer = rows.get(user_msg.pk), rows.get(assistant_msg.pk)
    if not question or not answer or question['content'] != user_msg.content or answer['content'] != assistant_msg.content:
        return None
    courses, notes, selection = reply_sources(question, answer)
    transcripts = reply_transcript_sources(question, answer)
    excerpts = legacy_transcript_excerpts(answer['cards'], transcripts)
    courses.update(course for course, _, _ in transcripts)
    courses.update(course for course, _, _ in excerpts)
    question_answers = reply_question_answers(answer)
    practice_reviews = reply_practice_reviews(answer)
    user = get_user_model().objects.filter(pk=user_msg.user_id, is_active=True).first()
    if selection or not user:
        return None
    try:
        if (not has_capability(user, 'ai.assistant') or visible_course_ids(user, courses) != courses
                or bound_practice_answers(user, question_answers)
                or visible_practice_review_sources(user, practice_reviews) != practice_reviews):
            return None
        matched = match_legacy_transcript_excerpts(excerpts)
        transcripts.update(matched.values())
        if len(matched) != len(excerpts) or current_transcript_sources(transcripts, lock=lock_transcripts) != transcripts:
            return None
        if notes:
            _, sources = prepare_note_context(user, user_msg.bot, user_msg.conversation_id, user_msg.content)
            if not notes <= {(source['note_id'], source['version']) for source in sources}:
                return None
    except PermissionDenied:
        return None
    return courses, notes, question_answers, practice_reviews, transcripts


def schedule_conversation_title(conversation, answer_id, expected_title):
    from ..models import PendingConversationTitle
    from .ulr_outbox import publish_after_commit

    job = PendingConversationTitle.objects.create(conversation=conversation, answer_message_id=answer_id,
                                                   expected_title=expected_title)
    publish_after_commit(publish_conversation_title, job.pk)


def publish_conversation_title(job_id):
    from ..models import PendingConversationTitle
    from ..tasks import generate_conversation_title
    from .ulr_outbox import publish_job

    def send(job):
        conversation = job.conversation
        if conversation.title != job.expected_title:
            return False
        generate_conversation_title.apply_async(
            (str(conversation.conversation_id), conversation.user_id, conversation.bot_id),
            {'expected_title': job.expected_title, 'answer_message_id': job.answer_message_id, 'pending_job_id': job.pk},
            retry=False, ignore_result=True,
        )

    return publish_job(PendingConversationTitle.objects.select_related('conversation').filter(pk=job_id), send)


def generate_pending_title(job_id):
    from ..models import PendingConversationTitle
    from .ulr_outbox import consume_job

    def generate(job, claimed):
        conversation = job.conversation
        return sync_generate_title(str(conversation.conversation_id), conversation.user_id, conversation.bot_id,
                                   expected_title=job.expected_title, ulr=True, answer_message_id=job.answer_message_id,
                                   pending_job=claimed)

    return consume_job(PendingConversationTitle.objects.select_related('conversation').filter(pk=job_id), generate)


def sync_generate_title(conversation_id, user_id, bot_id, *, expected_title='', ulr=False, answer_message_id=None,
                        pending_job=None):
    """Synchronously generate a conversation title from the first exchange."""
    from ..models import Conversation, AIChatMessage as Msg

    try:
        conversation = Conversation.objects.filter(conversation_id=conversation_id, user_id=user_id, bot_id=bot_id)
        if conversation.exclude(title=expected_title).exists() or (ulr and not conversation.exists()):
            return None

        messages = Msg.objects.filter(conversation_id=conversation_id, user_id=user_id)
        if ulr:
            messages = messages.filter(bot_id=bot_id, bot__is_active=True).exclude(content='[Thinking...]')
        if ulr and answer_message_id is not None:
            assistant_msg = messages.filter(pk=answer_message_id, role='assistant',
                                            metadata__learning_turn__completed=True).first()
            question_id = assistant_msg.metadata['learning_turn'].get('message_id') if assistant_msg else None
            user_msg = messages.filter(pk=question_id, role='user').first() if type(question_id) is int else None
        else:
            msgs = list(messages.order_by('timestamp', 'pk')[:4])
            assistant_msg = next((m for m in msgs if m.role == 'assistant'), None)
            if ulr and assistant_msg:
                msgs = reversed(msgs[:msgs.index(assistant_msg)])
            user_msg = next((m for m in msgs if m.role == 'user'), None)
        if not user_msg or not assistant_msg:
            return None

        from .language import message_language
        english = message_language(user_msg) == 'en'
        instruction = (Path(settings.BASE_DIR) / 'prompts/ai_assistant/title_generation.txt').read_text()
        instruction = instruction.replace('{language}', 'English' if english else 'Simplified Chinese').replace('{limit}', '8 words and 80 characters' if english else '15 characters')
        prompt = (
            f"用户: {user_msg.content[:300]}\n"
            f"助手: {assistant_msg.content[:300]}\n\n"
            f"{instruction}"
        )

        with observe_background('ulr' if ulr else 'legacy', f'title:{assistant_msg.conversation_id}',
                                source_message_id=user_msg.pk, answer_message_id=assistant_msg.pk):
            if ulr:
                from .dsh_tasks import TITLE_SCHEMA
                from .ulr_structured import run_collector
                source_snapshot = _authorized_title_inputs(messages, user_msg, assistant_msg)
                if source_snapshot is None:
                    return None
                try:
                    result = run_collector(prompt, operation='assistant.title', name='submit_title',
                        instruction=(Path(settings.BASE_DIR) / 'prompts/ai_assistant/title_task.txt').read_text(),
                        schema=TITLE_SCHEMA, max_tokens=64, temperature=0.2)
                    title = result['title'].strip() or _fallback_title(user_msg)
                except ValueError:
                    title = _fallback_title(user_msg)
            elif getattr(settings, 'UNIMIND_DSH_TITLE_ENABLED', False) or getattr(settings, 'UNIMIND_DSH_GENERATION_ENABLED', False):
                try:
                    title = _generate_title_via_dsh(prompt) or _fallback_title(user_msg)
                except Exception:
                    logger.warning("DSH title generation failed for conversation %s", conversation_id, exc_info=True)
                    title = _fallback_title(user_msg)
            else:
                ai = AIService()
                result = ai.simple_chat_text(
                    system_prompt=instruction,
                    user_prompt=prompt,
                    operation='assistant.chat.title',
                )
                title = result.strip() if result else ''

        title = title[:TITLE_MAX_CHARS if english else 15]
        if ulr:
            if not title:
                return None
            with transaction.atomic():
                if not conversation.filter(title=expected_title).select_for_update().exists():
                    return None
                if _authorized_title_inputs(messages, user_msg, assistant_msg, lock_transcripts=True) != source_snapshot:
                    return None
                updated = conversation.filter(title=expected_title).update(title=title)
                # Consume the claim with the title write, even if the title stays the same.
                if pending_job is not None and not pending_job.delete()[0]:
                    transaction.set_rollback(True)
                    return None
            return title if updated else None
        if title:
            conversation, _ = Conversation.objects.get_or_create(
                conversation_id=conversation_id, user_id=user_id, defaults={'bot_id': bot_id},
            )
            if not Conversation.objects.filter(pk=conversation.pk, title=expected_title).update(title=title):
                return None
            logger.info("Generated title '%s' for conversation %s", title, conversation_id)
            return title
    except Exception:
        if pending_job is not None:
            raise
        logger.exception("Failed to generate title for conversation %s", conversation_id)
    return None
