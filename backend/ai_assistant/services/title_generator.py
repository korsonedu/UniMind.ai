"""
Synchronous conversation title generation.
Called inline from SSE view after first assistant response completes.
Uses the server DSH task when enabled; otherwise keeps the legacy model path.
"""
import logging

from django.conf import settings

from ai_service import AIService

logger = logging.getLogger(__name__)

TITLE_MAX_CHARS = 15


def _fallback_title(user_msg):
    """Deterministic short title when the DSH task is unavailable."""
    return ' '.join(str(getattr(user_msg, 'content', '') or '').split())[:TITLE_MAX_CHARS]


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

        prompt = (
            f"用户: {user_msg.content[:300]}\n"
            f"助手: {assistant_msg.content[:300]}\n\n"
            "为以上对话生成一个简短标题（≤15个字），直接输出标题，不要引号、不要前缀。"
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
                system_prompt="你是标题生成器。为对话生成简短标题（≤15字），直接输出标题。",
                user_prompt=prompt,
                operation='assistant.chat.title',
            )
            title = result.strip()[:120] if result else ''

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
