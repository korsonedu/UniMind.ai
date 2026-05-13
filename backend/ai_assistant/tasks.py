import logging

from celery import shared_task
from django.db import connections

from ai_engine.service import AICallError
from ai_service import AIService
from .models import AIChatMessage, Bot
from .utils import get_student_academic_context

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=120,
    time_limit=180,
    acks_late=True,
)
def process_ai_chat_async(self, user_id: int, bot_id: int, user_message: str, pending_msg_id: int, history_limit: int = 10):
    from users.models import User

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error("process_ai_chat_async: user not found user_id=%s", user_id)
        return

    try:
        bot = Bot.objects.get(id=bot_id) if bot_id else None
    except Bot.DoesNotExist:
        logger.error("process_ai_chat_async: bot not found bot_id=%s", bot_id)
        return

    history_objs = AIChatMessage.objects.filter(
        user=user, bot=bot
    ).order_by('-timestamp')[:history_limit]
    history_msgs = [
        {"role": h.role, "content": h.content}
        for h in reversed(history_objs)
        if h.content != "[Thinking...]"
    ]

    student_context = ""
    if bot and bot.is_exclusive:
        student_context = get_student_academic_context(user)

    try:
        res = AIService.chat_with_assistant(bot, history_msgs, user_message, student_context)

        pending_msg = AIChatMessage.objects.filter(id=pending_msg_id).first()
        if not pending_msg:
            return

        if res and 'choices' in res:
            ai_content = res['choices'][0]['message']['content']
            ai_content = ai_content.replace('\\[', ' $$ ').replace('\\]', ' $$ ').replace('\\(', ' $ ').replace('\\)', ' $ ')

            finish_reason = res['choices'][0].get('finish_reason')
            if finish_reason == 'length':
                ai_content += "\n\n(已达到单次回复上限...)"

            pending_msg.content = ai_content
            pending_msg.save()
        else:
            pending_msg.content = "AI 助教暂时无法响应，请稍后再试。"
            pending_msg.save()

    except AICallError as exc:
        logger.warning("AI chat retryable error: %s", exc)
        pending_msg = AIChatMessage.objects.filter(id=pending_msg_id).first()
        if pending_msg:
            pending_msg.content = "AI 助教暂时无法响应，请稍后再试。"
            pending_msg.save()
        if exc.retryable and self.request.retries < self.max_retries:
            raise self.retry(exc=exc)

    except Exception as exc:
        logger.exception("AI chat failed: user_id=%s bot_id=%s", user_id, bot_id)
        pending_msg = AIChatMessage.objects.filter(id=pending_msg_id).first()
        if pending_msg:
            pending_msg.content = "AI 助教暂时无法响应，请稍后再试。"
            pending_msg.save()

    finally:
        connections.close_all()
