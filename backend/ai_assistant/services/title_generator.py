"""
Synchronous conversation title generation.
Called inline from SSE view after first assistant response completes.
Uses the server DSH task when enabled; otherwise keeps the legacy model path.
"""
import logging
from pathlib import Path

from django.conf import settings

from ai_service import AIService

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


def sync_generate_title(conversation_id, user_id, bot_id, *, expected_title=''):
    """Synchronously generate a conversation title from the first exchange."""
    from ..models import Conversation, AIChatMessage as Msg

    try:
        if Conversation.objects.filter(conversation_id=conversation_id, user_id=user_id, bot_id=bot_id).exclude(title=expected_title).exists():
            return None

        msgs = list(
            Msg.objects
            .filter(conversation_id=conversation_id, user_id=user_id)
            .order_by('timestamp')[:4]
        )
        user_msg = next((m for m in msgs if m.role == 'user'), None)
        assistant_msg = next((m for m in msgs if m.role == 'assistant'), None)
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

        if getattr(settings, 'UNIMIND_DSH_TITLE_ENABLED', False) or getattr(settings, 'UNIMIND_DSH_GENERATION_ENABLED', False):
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
        if title:
            conversation, _ = Conversation.objects.get_or_create(
                conversation_id=conversation_id, user_id=user_id, defaults={'bot_id': bot_id},
            )
            if not Conversation.objects.filter(pk=conversation.pk, title=expected_title).update(title=title):
                return None
            logger.info("Generated title '%s' for conversation %s", title, conversation_id)
            return title
    except Exception:
        logger.exception("Failed to generate title for conversation %s", conversation_id)
    return None
