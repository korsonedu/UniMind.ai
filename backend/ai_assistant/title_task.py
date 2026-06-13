@shared_task(
    soft_time_limit=30,
    time_limit=60,
    acks_late=True,
)
def generate_conversation_title(conversation_id: str, user_id: int, bot_id: int):
    """用 LLM 总结首轮对话，生成会话标题。"""
    from .models import Conversation, AIChatMessage as Msg

    try:
        # 已有标题则跳过
        if Conversation.objects.filter(conversation_id=conversation_id, title__gt='').exists():
            return

        # 取首轮 user + assistant 消息
        msgs = list(
            Msg.objects
            .filter(conversation_id=conversation_id, user_id=user_id)
            .order_by('timestamp')[:4]
        )
        user_msg = next((m for m in msgs if m.role == 'user'), None)
        assistant_msg = next((m for m in msgs if m.role == 'assistant'), None)
        if not user_msg or not assistant_msg:
            return

        prompt = (
            f"用户: {user_msg.content[:300]}\n"
            f"助手: {assistant_msg.content[:300]}\n\n"
            "为以上对话生成一个简短标题（≤15个字），直接输出标题，不要引号、不要前缀。"
        )

        ai = AIService()
        result = ai.simple_chat_text(
            system_prompt="你是标题生成器。为对话生成简短标题（≤15字），直接输出标题。",
            user_prompt=prompt,
        )
        title = result.strip()[:120] if result else ''

        if title:
            Conversation.objects.update_or_create(
                conversation_id=conversation_id,
                defaults={
                    'user_id': user_id,
                    'bot_id': bot_id,
                    'title': title,
                },
            )
            logger.info("Generated title '%s' for conversation %s", title, conversation_id)
    except Exception:
        logger.exception("Failed to generate title for conversation %s", conversation_id)
    finally:
        connections.close_all()
