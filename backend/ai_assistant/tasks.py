import logging
import os

from celery import shared_task
from django.db import connections

from ai_engine.service import AICallError
from ai_service import AIService
from .models import AIChatMessage, Bot

logger = logging.getLogger(__name__)

USE_MEM0 = os.getenv('USE_MEM0', 'false').lower() == 'true'


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


@shared_task(
    bind=True,
    soft_time_limit=600,
    time_limit=660,
    acks_late=True,
)
def reflect_user_learning(self):
    """Daily meta-cognition: analyze user learning data and generate higher-order memories.

    For each active user with mem0 enabled, analyzes:
    - Wrong answer patterns (which topics are consistently weak)
    - Study frequency and recency
    - Knowledge mastery gaps

    Generates structured insights stored as semantic memories via mem0.
    """
    if not USE_MEM0:
        logger.info("reflect_user_learning: USE_MEM0=false, skipping")
        return

    from django.utils import timezone
    from datetime import timedelta
    from django.contrib.auth import get_user_model
    from quizzes.models import QuizExam, Question

    User = get_user_model()
    now = timezone.now()
    cutoff = now - timedelta(days=7)

    # Get users active in the last 7 days
    active_user_ids = (
        AIChatMessage.objects.filter(timestamp__gte=cutoff)
        .values_list('user_id', flat=True)
        .distinct()
    )
    users = User.objects.filter(
        id__in=active_user_ids,
        institution__isnull=False,
    ).select_related('institution')

    processed = 0
    errors = 0

    for user in users:
        try:
            insights = _analyze_user(user, cutoff, now)
            if insights:
                _store_insights(user, insights)
                processed += 1
        except Exception:
            logger.exception("reflect_user_learning failed for user %d", user.id)
            errors += 1
        finally:
            connections.close_all()

    logger.info("reflect_user_learning done: processed=%d, errors=%d", processed, errors)


def _analyze_user(user, cutoff, now):
    """Analyze a single user's learning data and return insights."""
    from quizzes.models import QuizExam

    insights = []

    # 1. Analyze wrong answer patterns from recent exams
    recent_exams = QuizExam.objects.filter(
        user=user,
        submitted_at__gte=cutoff,
    ).order_by('-submitted_at')[:10]

    if recent_exams:
        total_questions = 0
        total_wrong = 0
        for exam in recent_exams:
            results = exam.results or {}
            questions = results.get('questions', [])
            for q in questions:
                total_questions += 1
                if not q.get('is_correct', True):
                    total_wrong += 1

        if total_questions > 0:
            error_rate = total_wrong / total_questions
            if error_rate > 0.6:
                insights.append({
                    "type": "study_pattern",
                    "text": f"用户近一周做题错误率 {error_rate:.0%}（{total_wrong}/{total_questions}），整体掌握度较低，建议加强基础复习。",
                })
            elif error_rate < 0.2:
                insights.append({
                    "type": "study_pattern",
                    "text": f"用户近一周做题正确率 {(1-error_rate):.0%}，掌握度良好，可以尝试更高难度。",
                })

    # 2. Study frequency
    chat_count = AIChatMessage.objects.filter(
        user=user, role='user', timestamp__gte=cutoff
    ).count()

    if chat_count >= 20:
        insights.append({
            "type": "engagement",
            "text": "用户近一周高频使用（20+次对话），学习积极性很高。",
        })
    elif chat_count <= 2:
        insights.append({
            "type": "engagement",
            "text": "用户近一周使用频率很低（≤2次），可能需要激励或遇到了困难。",
        })

    # 3. Time pattern (simplified: check active hours)
    from django.db.models import Count
    from django.db.models.functions import ExtractHour

    hourly = (
        AIChatMessage.objects.filter(
            user=user, role='user', timestamp__gte=cutoff
        )
        .annotate(hour=ExtractHour('timestamp'))
        .values('hour')
        .annotate(cnt=Count('id'))
        .order_by('-cnt')
    )

    if hourly:
        peak_hour = hourly[0]['hour']
        if 22 <= peak_hour or peak_hour < 6:
            insights.append({
                "type": "time_pattern",
                "text": "用户主要在深夜学习（22点后），建议注意休息。",
            })
        elif 6 <= peak_hour < 12:
            insights.append({
                "type": "time_pattern",
                "text": "用户习惯在上午学习，是高效学习者。",
            })

    return insights


def _store_insights(user, insights):
    """Store insights as semantic memories via mem0."""
    from ai_assistant.services.tenant_memory import TenantMemoryManager

    if not user.institution_id:
        return

    manager = TenantMemoryManager(institution_id=user.institution_id)

    for insight in insights:
        message = f"[系统分析] {insight['text']}"
        manager.add(
            user_id=user.id,
            message=message,
            metadata={
                "source": "meta_cognition",
                "insight_type": insight["type"],
            },
        )
