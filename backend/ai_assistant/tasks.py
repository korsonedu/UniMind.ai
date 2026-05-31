import logging
import os

from celery import shared_task
from django.db import connections

from ai_engine.service import AICallError
from ai_service import AIService
from .models import AIChatMessage, Bot
from .services.tenant_memory import TenantMemoryManager

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


def _store_insights(user, insights, source="meta_cognition"):
    """Store insights as semantic memories via mem0."""
    if not user.institution_id:
        return

    manager = TenantMemoryManager(institution_id=user.institution_id)

    for insight in insights:
        message = f"[系统分析] {insight['text']}"
        manager.add(
            user_id=user.id,
            message=message,
            metadata={
                "source": source,
                "insight_type": insight["type"],
            },
        )


@shared_task(
    bind=True,
    soft_time_limit=600,
    time_limit=660,
    acks_late=True,
)
def reflect_teacher_patterns(self):
    """Daily meta-cognition for teachers: analyze question generation patterns.

    For each active teacher (institution admin) with mem0 enabled, analyzes:
    - Question type preferences (objective vs subjective)
    - Difficulty preferences
    - Subject focus areas
    - Quality trends (ARC pipeline pass rate)
    - Generation frequency and active hours
    """
    if not USE_MEM0:
        logger.info("reflect_teacher_patterns: USE_MEM0=false, skipping")
        return

    from django.utils import timezone
    from datetime import timedelta
    from django.contrib.auth import get_user_model
    from django.db.models import Count
    from django.db.models.functions import ExtractHour
    from quizzes.models import Question, ContentPipelineTask

    User = get_user_model()
    now = timezone.now()
    cutoff = now - timedelta(days=30)

    # Get institution admins who used exam_generator recently
    exam_bot = Bot.objects.filter(bot_type='exam_generator').first()
    if not exam_bot:
        logger.info("reflect_teacher_patterns: no exam_generator bot found")
        return

    active_teacher_ids = (
        AIChatMessage.objects.filter(
            timestamp__gte=cutoff,
            bot=exam_bot,
            role='user',
        )
        .values_list('user_id', flat=True)
        .distinct()
    )
    teachers = User.objects.filter(
        id__in=active_teacher_ids,
        is_institution_admin=True,
        institution__isnull=False,
    ).select_related('institution')

    processed = 0
    errors = 0

    for teacher in teachers:
        try:
            insights = _analyze_teacher(teacher, exam_bot, cutoff, now)
            if insights:
                _store_insights(teacher, insights, source="exam_meta_cognition")
                processed += 1
        except Exception:
            logger.exception("reflect_teacher_patterns failed for user %d", teacher.id)
            errors += 1

    logger.info("reflect_teacher_patterns done: processed=%d, errors=%d", processed, errors)


def _analyze_teacher(teacher, exam_bot, cutoff, now):
    """Analyze a single teacher's question generation patterns."""
    from quizzes.models import Question, ContentPipelineTask

    insights = []
    inst = teacher.institution

    # 1. Question type preferences
    recent_questions = Question.objects.filter(
        institution=inst,
        created_at__gte=cutoff,
    )
    total_qs = recent_questions.count()
    if total_qs > 0:
        obj_count = recent_questions.filter(q_type='objective').count()
        subj_count = total_qs - obj_count
        if obj_count > subj_count * 2:
            insights.append({
                "type": "question_preference",
                "text": f"该教师近30天出题以客观题为主（{obj_count}/{total_qs}），偏好选择题/判断题。",
            })
        elif subj_count > obj_count * 2:
            insights.append({
                "type": "question_preference",
                "text": f"该教师近30天出题以主观题为主（{subj_count}/{total_qs}），偏好简答/论述/名词解释。",
            })

        # 2. Difficulty distribution
        from django.db.models import Q
        hard_count = recent_questions.filter(
            Q(difficulty_level='hard') | Q(difficulty_level='extreme')
        ).count()
        easy_count = recent_questions.filter(
            Q(difficulty_level='entry') | Q(difficulty_level='easy')
        ).count()
        if hard_count > total_qs * 0.5:
            insights.append({
                "type": "difficulty_preference",
                "text": f"该教师偏好高难度题目（hard/extreme占{hard_count}/{total_qs}），注重拔高训练。",
            })
        elif easy_count > total_qs * 0.5:
            insights.append({
                "type": "difficulty_preference",
                "text": f"该教师偏好基础题目（entry/easy占{easy_count}/{total_qs}），注重夯实基础。",
            })

        # 3. Subject focus
        subjects = (
            recent_questions
            .values_list('knowledge_point__subject', flat=True)
            .distinct()
        )
        subjects = [s for s in subjects if s]
        if len(subjects) == 1:
            insights.append({
                "type": "subject_focus",
                "text": f"该教师专注{subjects[0]}学科出题。",
            })
        elif len(subjects) > 3:
            insights.append({
                "type": "subject_focus",
                "text": f"该教师跨{len(subjects)}个学科出题，覆盖面广。",
            })

    # 4. Quality trends from ARC pipeline
    pipeline_tasks = ContentPipelineTask.objects.filter(
        created_by=teacher,
        created_at__gte=cutoff,
    )
    total_pipelines = pipeline_tasks.count()
    if total_pipelines > 0:
        completed = pipeline_tasks.filter(status='completed').count()
        failed = pipeline_tasks.filter(status='failed').count()
        if completed > 0:
            pass_rate = completed / total_pipelines
            if pass_rate < 0.5:
                insights.append({
                    "type": "quality_trend",
                    "text": f"ARC管线通过率较低（{completed}/{total_pipelines}），建议优化出题模板或调整难度。",
                })
            elif pass_rate > 0.8:
                insights.append({
                    "type": "quality_trend",
                    "text": f"ARC管线通过率良好（{completed}/{total_pipelines}），出题质量稳定。",
                })

    # 5. Generation frequency
    chat_count = AIChatMessage.objects.filter(
        user=teacher, bot=exam_bot, role='user', timestamp__gte=cutoff
    ).count()
    if chat_count >= 30:
        insights.append({
            "type": "usage_frequency",
            "text": f"该教师近30天高频使用命题官（{chat_count}次），是核心用户。",
        })
    elif chat_count <= 3:
        insights.append({
            "type": "usage_frequency",
            "text": "该教师近30天很少使用命题官，可能需要引导或遇到了问题。",
        })

    # 6. Active hours
    hourly = (
        AIChatMessage.objects.filter(
            user=teacher, bot=exam_bot, role='user', timestamp__gte=cutoff
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
                "text": "该教师主要在深夜备课出题，工作强度较大。",
            })
        elif 6 <= peak_hour < 9:
            insights.append({
                "type": "time_pattern",
                "text": "该教师习惯在早晨备课出题，时间管理良好。",
            })

    return insights


@shared_task(
    bind=True,
    soft_time_limit=300,
    time_limit=360,
    acks_late=True,
)
def cleanup_stale_memories(self):
    """Weekly cleanup of stale structured memories.

    Rules:
    - use_count=0 and updated_at > 30 days → soft delete
    - confidence < 0.3 and updated_at > 60 days → soft delete
    """
    from django.utils import timezone
    from datetime import timedelta
    from .models import AgentMemory

    now = timezone.now()
    deleted_count = 0

    # Rule 1: never used, old enough
    qs1 = AgentMemory.objects.filter(
        is_active=True,
        use_count=0,
        updated_at__lt=now - timedelta(days=30),
    )
    count1 = qs1.update(is_active=False)
    deleted_count += count1

    # Rule 2: low confidence, old enough
    qs2 = AgentMemory.objects.filter(
        is_active=True,
        confidence__lt=0.3,
        updated_at__lt=now - timedelta(days=60),
    )
    count2 = qs2.update(is_active=False)
    deleted_count += count2

    logger.info("cleanup_stale_memories: soft-deleted %d memories (rule1=%d, rule2=%d)", deleted_count, count1, count2)

    # Cleanup mem0 semantic memories if enabled
    if USE_MEM0:
        _cleanup_semantic_memories()

    return deleted_count


def _cleanup_semantic_memories():
    """Cleanup stale semantic memories via mem0."""
    from django.contrib.auth import get_user_model
    from .models import AIChatMessage
    from django.utils import timezone
    from datetime import timedelta

    User = get_user_model()
    now = timezone.now()
    cutoff = now - timedelta(days=90)

    # Find institutions with active users in last 90 days
    active_inst_ids = (
        AIChatMessage.objects.filter(timestamp__gte=cutoff)
        .values_list('user__institution_id', flat=True)
        .distinct()
    )

    for inst_id in active_inst_ids:
        if not inst_id:
            continue
        try:
            manager = TenantMemoryManager(institution_id=inst_id)
            all_memories = manager.get_all()
            logger.info("cleanup_stale_memories: institution %d has %d semantic memories", inst_id, len(all_memories))
        except Exception:
            logger.exception("cleanup_stale_memories: failed for institution %d", inst_id)
