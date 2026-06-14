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
    """Cleanup stale semantic memories: delete all memories for users inactive > 90 days."""
    from django.contrib.auth import get_user_model
    from .models import AIChatMessage
    from django.utils import timezone
    from datetime import timedelta

    User = get_user_model()
    now = timezone.now()
    cutoff = now - timedelta(days=90)

    # Find users with recent activity per institution
    active_user_ids = set(
        AIChatMessage.objects.filter(timestamp__gte=cutoff)
        .values_list('user_id', flat=True)
        .distinct()
    )

    # Find institutions that have any users
    inst_ids = (
        User.objects.filter(institution_id__isnull=False)
        .values_list('institution_id', flat=True)
        .distinct()
    )

    deleted_total = 0
    for inst_id in inst_ids:
        try:
            manager = TenantMemoryManager(institution_id=inst_id)
            # Get all users in this institution
            inst_user_ids = User.objects.filter(
                institution_id=inst_id
            ).values_list('id', flat=True)

            for uid in inst_user_ids:
                if uid in active_user_ids:
                    continue
                # User inactive > 90 days — delete their semantic memories
                try:
                    manager.delete_all(user_id=uid)
                    deleted_total += 1
                except Exception:
                    logger.exception("cleanup_stale_memories: failed to delete mem0 for user %d", uid)
        except Exception:
            logger.exception("cleanup_stale_memories: failed for institution %d", inst_id)

    if deleted_total:
        logger.info("cleanup_stale_memories: cleaned semantic memories for %d inactive users", deleted_total)


@shared_task(
    soft_time_limit=30,
    time_limit=60,
    acks_late=True,
)
def record_trajectory_async(
    user_id: int,
    bot_id: int,
    conversation_id: str,
    messages: list,
    tool_calls: list,
    tool_outputs: list,
    prompt_variant: str = 'baseline'
):
    """异步记录对话轨迹到数据库，并自动评估 outcome。"""
    from .models import AITrajectory

    try:
        trajectory = AITrajectory.objects.create(
            user_id=user_id,
            bot_id=bot_id,
            conversation_id=conversation_id,
            messages=messages,
            tool_calls=tool_calls,
            tool_outputs=tool_outputs,
            prompt_variant=prompt_variant,
        )
        logger.info(
            "Async recorded trajectory %d for user %d, conversation %s",
            trajectory.id, user_id, conversation_id
        )
        # 启发式自动评估
        from .services.trajectory_recorder import _auto_evaluate_trajectory
        _auto_evaluate_trajectory(trajectory)

        # 提取可复用规律（仅限成功/部分成功的轨迹）
        if trajectory.outcome in ('success', 'partial'):
            experience_extract_task.delay(trajectory.id)
    except Exception:
        logger.exception("Failed to async record trajectory for user %d", user_id)
    finally:
        connections.close_all()


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
            operation='assistant.chat.title',
        )
        title = (result or '').strip()[:120]

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


@shared_task(
    soft_time_limit=120,
    time_limit=180,
    acks_late=True,
)
def precompute_user_profile(user_id: int):
    """
    预计算用户画像并缓存到 Redis。
    
    触发时机：
    - 用户登录时
    - 对话结束时
    - 定时任务（每天一次）
    """
    from django.core.cache import cache
    from .services.memory_analyzer import analyze_user_profile
    
    cache_key = f"user_profile:{user_id}"
    
    try:
        from users.models import User
        user = User.objects.get(id=user_id)
        
        # 获取用户记忆
        memories = []
        
        # 结构化记忆
        from .models import AgentMemory
        agent_memories = AgentMemory.objects.filter(
            user=user, is_active=True
        ).order_by('-confidence')[:20]
        for m in agent_memories:
            memories.append({'key': m.key, 'value': m.value})
        
        # 语义记忆（如果启用）
        USE_MEM0 = os.getenv('USE_MEM0', 'false').lower() == 'true'
        if USE_MEM0 and user.institution_id:
            try:
                from .services.tenant_memory import TenantMemoryManager
                manager = TenantMemoryManager(institution_id=user.institution_id)
                semantic_memories = manager.get_all(user_id=user.id)[:20]
                memories.extend(semantic_memories)
            except Exception:
                logger.warning("Failed to get semantic memories for user %d", user_id)
        
        if not memories:
            logger.info("No memories found for user %d, skipping profile precomputation", user_id)
            return
        
        # 分析用户画像
        profile = analyze_user_profile(memories)
        
        if profile and profile.confidence >= 0.6:
            # 缓存 24 小时
            cache.set(cache_key, {
                'learning_style': profile.learning_style,
                'response_length': profile.response_length,
                'interaction_style': profile.interaction_style,
                'cognitive_state': profile.cognitive_state,
                'domain_expertise': profile.domain_expertise,
                'confidence': profile.confidence,
            }, timeout=86400)
            logger.info("Precomputed and cached user profile for user %d (confidence=%.2f)", user_id, profile.confidence)
        else:
            logger.info("User profile analysis below threshold for user %d, not caching", user_id)
    
    except User.DoesNotExist:
        logger.warning("User %d not found for profile precomputation", user_id)
    except Exception:
        logger.exception("Failed to precompute user profile for user %d", user_id)
    finally:
        connections.close_all()


# ──────────────────────────────────────────────
#  经验路由器（Phase 1）：规律提取
# ──────────────────────────────────────────────

@shared_task(
    soft_time_limit=120,
    time_limit=180,
    acks_late=True,
)
def experience_extract_task(trajectory_id: int):
    """
    从一条对话轨迹中提取可复用规律，经过路由验证后写入 Experience 表。

    Phase 1 管线：extract → validate → dedup → save
    """
    from .models import AITrajectory
    from .services.experience_extractor import extract_experiences, save_experiences
    from .services.experience_router import validate_routing, find_duplicates, merge_experiences

    try:
        trajectory = AITrajectory.objects.select_related('user', 'bot').get(id=trajectory_id)
    except AITrajectory.DoesNotExist:
        logger.warning("experience_extract_task: trajectory %d not found", trajectory_id)
        return

    # 1. 提取
    experiences = extract_experiences(trajectory)
    if not experiences:
        logger.info("experience_extract_task: no experiences extracted from trajectory %d", trajectory_id)
        return

    # 2. 保存
    saved = save_experiences(trajectory, experiences)
    if not saved:
        return

    # 3. 验证路由 + 去重
    for exp in saved:
        if not validate_routing(exp):
            exp.status = 'retired'
            exp.save(update_fields=['status'])
            continue

        duplicates = find_duplicates(exp)
        if duplicates:
            merge_experiences(duplicates[0], exp)
        else:
            logger.info(
                "experience_extract_task: new experience %d '%s' (dim=%s, scope=%s)",
                exp.id, exp.title, exp.dimension, exp.scope_type,
            )

    logger.info(
        "experience_extract_task: processed trajectory %d → %d experiences (%d saved)",
        trajectory_id, len(experiences),
        len([e for e in saved if e.status == 'active']),
    )


@shared_task(
    soft_time_limit=60,
    time_limit=90,
    acks_late=True,
)
def apply_experience_decay_task():
    """定期执行经验权重衰减。（建议每天执行）"""
    from .services.experience_router import apply_decay
    affected = apply_decay()
    logger.info("apply_experience_decay_task: affected %d experiences", affected)
    return affected


@shared_task(
    soft_time_limit=30,
    time_limit=60,
    acks_late=True,
)
def experience_verify_on_answer(user_id: int, kp_id: int, score: float, max_score: float):
    """
    学生做题后触发：检查是否有经验规律的适用范围覆盖了当前 KP，
    记录验证数据用于后续反事实对比。

    触发时机：学生提交任意题目答案后。
    当前阶段：只记录数据，不自动更新经验置信度（数据积累后开启）。
    """
    from quizzes.services.knowledge_graph_traversal import get_downstream_kps
    from .models import Experience, ExperienceVerification

    # 1. 找到 scope 匹配当前 KP 的经验
    #    两种匹配方式：
    #    a. 经验 scope=kp_chain，scope_value.kp_id 是当前 KP 的上游
    #    b. 经验 scope=student，scope_value.student_id == user_id
    candidates = Experience.objects.filter(
        status='active',
        confidence__in=['low', 'medium'],
    )

    verified = 0
    for exp in candidates:
        match = False

        if exp.scope_type == 'kp_chain':
            # 检查当前 KP 是否在该经验的 kp_chain 下游
            upstream_id = (exp.scope_value or {}).get('kp_id')
            if upstream_id:
                downstream = get_downstream_kps(upstream_id)
                downstream_ids = {d['kp_id'] for d in downstream}
                if kp_id in downstream_ids:
                    match = True

        elif exp.scope_type == 'student':
            if (exp.scope_value or {}).get('student_id') == user_id:
                match = True

        if not match:
            continue

        # 2. 记录验证数据
        ExperienceVerification.objects.create(
            experience=exp,
            user_id=user_id,
            kp_id=kp_id,
            score=score,
            max_score=max_score,
            score_ratio=round(score / max_score, 4) if max_score > 0 else 0,
        )
        verified += 1

    if verified:
        logger.info(
            "experience_verify_on_answer: user=%d, kp=%d, score=%.1f/%.1f, matched %d experiences",
            user_id, kp_id, score, max_score, verified,
        )
    return verified


@shared_task(
    soft_time_limit=120,
    time_limit=180,
    acks_late=True,
)
def experience_aggregate_verifications():
    """
    周期分析 ExperienceVerification 数据，自动升级经验置信度。

    策略（Phase 3 MVP）：
    - 对每条有足够验证数据（≥10条）的经验
    - 计算平均得分率
    - 得分率 > 0.7 → low→medium
    - 得分率 > 0.8 且 ≥30条 → medium→high
    - 得分率 < 0.4 → 降权/退役

    触发：建议每天执行一次（配 Celery Beat）。
    """
    from django.db.models import Avg, Count
    from .models import Experience, ExperienceVerification

    candidates = Experience.objects.filter(
        status='active',
        confidence__in=['low', 'medium'],
        dimension__in=['prompt', 'memory', 'workflow'],
    )

    upgraded = 0
    downgraded = 0
    retired = 0

    for exp in candidates:
        stats = ExperienceVerification.objects.filter(
            experience=exp,
        ).aggregate(
            count=Count('id'),
            avg_score=Avg('score_ratio'),
        )
        count = stats['count'] or 0
        avg = stats['avg_score'] or 0

        if count < 5:
            continue

        if avg > 0.8 and count >= 30 and exp.confidence == 'medium':
            exp.confidence = 'high'
            exp.weight = float(count) * avg
            exp.save(update_fields=['confidence', 'weight'])
            logger.info("experience_aggregate: exp %d '%s' → high (n=%d, avg=%.2f)", exp.id, exp.title, count, avg)
            upgraded += 1

        elif avg > 0.7 and exp.confidence == 'low':
            exp.confidence = 'medium'
            exp.weight = float(count) * avg
            exp.save(update_fields=['confidence', 'weight'])
            logger.info("experience_aggregate: exp %d '%s' → medium (n=%d, avg=%.2f)", exp.id, exp.title, count, avg)
            upgraded += 1

        elif avg < 0.4 and count >= 10:
            exp.weight *= 0.5
            exp.verify_fail_count += 1
            exp.save(update_fields=['weight', 'verify_fail_count'])
            logger.info("experience_aggregate: exp %d '%s' downgraded (n=%d, avg=%.2f)", exp.id, exp.title, count, avg)
            downgraded += 1

            if exp.verify_fail_count >= 3:
                exp.status = 'retired'
                exp.save(update_fields=['status'])
                logger.info("experience_aggregate: exp %d '%s' retired (3 failures)", exp.id, exp.title)
                retired += 1

    logger.info(
        "experience_aggregate: %d upgraded, %d downgraded, %d retired",
        upgraded, downgraded, retired,
    )
    return {'upgraded': upgraded, 'downgraded': downgraded, 'retired': retired}


# ──────────────────────────────────────────────
#  GEPA 自进化骨架（Phase 7）
# ──────────────────────────────────────────────

@shared_task(
    soft_time_limit=300,
    time_limit=360,
    acks_late=True,
)
def analyze_trajectory_task():
    """分析 Trajectory 数据，计算工具调用成功率与对话完成度。

    每周日凌晨执行，统计周期内的：
    - 各 bot 的 outcome 分布（success / partial / failure）
    - 工具调用频次（从 tool_calls JSON 提取 tool_name）
    - prompt_variant 维度的成功率对比
    """
    from .models import AITrajectory, Bot
    from django.db.models import Count
    from django.utils import timezone
    from datetime import timedelta
    from collections import Counter

    now = timezone.now()
    cutoff = now - timedelta(days=7)

    base_qs = AITrajectory.objects.filter(created_at__gte=cutoff)
    total = base_qs.count()

    if total == 0:
        logger.info("analyze_trajectory_task: no trajectories in the last 7 days, skipping")
        return {"total": 0}

    # 1. 按 outcome 分布
    outcome_stats = (
        base_qs.values('outcome')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    outcome_map = {item['outcome']: item['count'] for item in outcome_stats}
    success_count = outcome_map.get('success', 0)

    # 2. 按 bot 统计
    bot_stats = (
        base_qs.values('bot_id', 'bot__name')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    # 3. 工具调用频次（遍历 tool_calls JSON）
    tool_counter = Counter()
    for trajectory in base_qs.iterator(chunk_size=500):
        for tc in (trajectory.tool_calls or []):
            name = tc.get('name') if isinstance(tc, dict) else None
            if name:
                tool_counter[name] += 1

    # 4. prompt_variant 维度成功率
    variant_stats = (
        base_qs.values('prompt_variant')
        .annotate(total=Count('id'))
    )
    variant_breakdown = []
    for vs in variant_stats:
        variant = vs['prompt_variant']
        success = base_qs.filter(prompt_variant=variant, outcome='success').count()
        variant_breakdown.append({
            'variant': variant,
            'total': vs['total'],
            'success': success,
            'success_rate': round(success / vs['total'], 3) if vs['total'] else 0,
        })

    result = {
        'period': f'{cutoff.date()} ~ {now.date()}',
        'total': total,
        'success_count': success_count,
        'success_rate': round(success_count / total, 3) if total else 0,
        'outcome_distribution': outcome_map,
        'top_tools': tool_counter.most_common(10),
        'bot_breakdown': list(bot_stats),
        'prompt_variant_breakdown': variant_breakdown,
    }

    logger.info("analyze_trajectory_task: %s", result)

    # GEPA 优化建议生成（Phase D2 框架 — 数据积累后生效）
    suggestions = _generate_optimization_suggestions(result)
    if suggestions:
        _store_gepa_suggestions(suggestions)

    return result


def _generate_optimization_suggestions(analysis: dict) -> list[dict]:
    """基于 Trajectory 分析生成优化建议。不自动应用，仅输出供人工审核。"""
    suggestions = []

    # 1. 整体成功率偏低 → Memorix 参数可能过激进
    total = analysis.get('total', 0)
    if total >= 10:
        sr = analysis.get('success_rate', 1)
        if sr < 0.6:
            suggestions.append({
                'target': 'memorix',
                'param': 'alpha',
                'direction': 'decrease',
                'current': 0.60,
                'suggested': max(0.3, 0.60 - (0.6 - sr)),
                'reason': f'Trajectory 成功率 {sr:.0%} < 60%，Memorix α 偏高可能导致题目推送节奏过快',
                'confidence': round(0.6 + (0.6 - sr), 2),
            })

        # 2. 工具调用失败率高 → prompt 需要调整
        outcome_dist = analysis.get('outcome_distribution', {})
        partial = outcome_dist.get('partial', 0)
        failure = outcome_dist.get('failure', 0)
        problem_rate = (partial + failure) / total
        if problem_rate > 0.3:
            suggestions.append({
                'target': 'prompt',
                'param': 'tool_guide',
                'direction': 'improve',
                'current': 'current',
                'suggested': '增强工具使用指南，明确 failure mode 和 fallback 策略',
                'reason': f'工具调用问题率 {problem_rate:.0%} > 30%（partial={partial}, failure={failure}）',
                'confidence': round(min(0.9, problem_rate + 0.1), 2),
            })

        # 3. 某个 bot 表现显著差于其他
        bot_breakdown = analysis.get('bot_breakdown', [])
        if len(bot_breakdown) >= 2:
            for bot in bot_breakdown:
                bot['success_rate'] = bot.get('success_rate', 1)
            worst = min(bot_breakdown, key=lambda b: b.get('success_rate', 1))
            best = max(bot_breakdown, key=lambda b: b.get('success_rate', 1))
            if best.get('success_rate', 0) - worst.get('success_rate', 0) > 0.2:
                suggestions.append({
                    'target': 'bot',
                    'param': 'system_prompt',
                    'direction': 'review',
                    'current': worst.get('bot__name', 'unknown'),
                    'suggested': f"审查 {worst.get('bot__name', '')} 的 system prompt，"
                                 f"成功率 {worst.get('success_rate', 0):.0%} "
                                 f"vs {best.get('bot__name', '')} {best.get('success_rate', 0):.0%}",
                    'reason': 'bot 间成功率差异 > 20%，可能有 prompt 或 tools 配置问题',
                    'confidence': 0.7,
                })

    return suggestions


def _store_gepa_suggestions(suggestions: list[dict]):
    """将建议存入 Redis（GEPA 建议缓存），供后续人工审核或 API 读取。"""
    try:
        from django_redis import get_redis_connection
        redis_conn = get_redis_connection("default")
    except Exception:
        logger.warning("_store_gepa_suggestions: Redis unavailable")
        return

    import json
    from django.utils import timezone

    key = "gepa:suggestions"
    entry = {
        'generated_at': timezone.now().isoformat(),
        'suggestions': suggestions,
    }
    redis_conn.lpush(key, json.dumps(entry, ensure_ascii=False))
    redis_conn.ltrim(key, 0, 49)  # 保留最近 50 条
    redis_conn.expire(key, 86400 * 30)  # TTL 30 天

    logger.info("_store_gepa_suggestions: stored %d suggestions", len(suggestions))


@shared_task(
    soft_time_limit=600,
    time_limit=660,
    acks_late=True,
)
def optimize_prompt_task():
    """GEPA: Generate → Evaluate → Polish → Adapt（Phase 7 骨架）

    从 Redis gepa:suggestions 读取分析建议，分派到对应 handler 执行优化。
    当前为框架阶段：只做分派 + 日志，不自动修改 prompt。
    后续 Phase 实现 LLM 驱动的 prompt 变体自动生成。
    """
    suggestions = _read_gepa_suggestions()
    if not suggestions:
        logger.info("optimize_prompt_task: no suggestions to process")
        return

    logger.info("optimize_prompt_task: processing %d suggestion batches", len(suggestions))

    for batch in suggestions:
        for s in batch.get('suggestions', []):
            target = s.get('target', '')
            try:
                if target == 'memorix':
                    _handle_memorix_suggestion(s)
                elif target == 'prompt':
                    _handle_prompt_suggestion(s)
                elif target == 'bot':
                    _handle_bot_suggestion(s)
                else:
                    logger.warning("Unknown suggestion target: %s", target)
            except Exception:
                logger.exception("Failed to handle suggestion: %s", s.get('reason', ''))


def _read_gepa_suggestions() -> list[dict]:
    """从 Redis 读取最新的 GEPA 建议批次（最近 5 条）。"""
    try:
        from django_redis import get_redis_connection
        redis_conn = get_redis_connection("default")
    except Exception:
        logger.warning("_read_gepa_suggestions: Redis unavailable")
        return []

    import json
    key = "gepa:suggestions"
    raw = redis_conn.lrange(key, 0, 4)  # 最近 5 条
    result = []
    for item in raw:
        try:
            result.append(json.loads(item))
        except json.JSONDecodeError:
            continue
    return result


# ── Suggestion handlers（框架，待后续填充 LLM 驱动逻辑）──

def _handle_memorix_suggestion(s: dict):
    """处理 Memorix alpha 参数调整建议。

    未来：自动调用 Memorix API 调整 alpha。
    当前：仅 log，需人工确认后手动调整。
    """
    logger.info(
        "[GEPA] Memorix suggestion: alpha %s → %s (reason: %s, confidence=%.2f)",
        s.get('current'), s.get('suggested'), s.get('reason'), s.get('confidence', 0)
    )


def _handle_prompt_suggestion(s: dict):
    """处理 prompt/tool_guide 改进建议 → 创建实验 variant。

    未来：调 LLM 生成具体措辞 variant，调用 gepa_variants.create_variant()。
    当前：仅 log + 标记为 needs_review。
    """
    param = s.get('param', 'unknown')
    logger.info(
        "[GEPA] Prompt suggestion: improve %s (reason: %s, confidence=%.2f)",
        param, s.get('reason'), s.get('confidence', 0)
    )


def _handle_bot_suggestion(s: dict):
    """处理 bot system_prompt 审查建议。

    未来：调 LLM 诊断 bot prompt 问题并生成改进 variant。
    当前：仅 log，需人工审查后手动调整。
    """
    logger.info(
        "[GEPA] Bot suggestion: review %s (reason: %s, confidence=%.2f)",
        s.get('current'), s.get('reason'), s.get('confidence', 0)
    )


@shared_task(
    soft_time_limit=60,
    time_limit=90,
    acks_late=True,
)
def pre_grade_single_question(session_id: str, question_id: int, user_answer: str, user_id: int):
    """异步预批改：单题批改后写 Redis 缓存，供 practice_submit_view 聚合。

    Redis key: practice:grade:{session_id}:{question_id}
    TTL: 30min（远超 session 的 24h TTL，足够提交窗口）
    """
    from django.core.cache import cache
    from django.contrib.auth import get_user_model
    from ai_service import AIService
    from ai_assistant.services.grading_engine import GradingEngine
    from ai_assistant.services.memory_system import MemorySystem
    from quizzes.models import Question

    User = get_user_model()
    cache_key = f'practice:grade:{session_id}:{question_id}'

    try:
        user = User.objects.get(id=user_id)
        question = Question.objects.get(id=question_id)
        ai = AIService()

        result = GradingEngine.grade(
            ai=ai,
            question_text=question.text or '',
            user_answer=user_answer,
            correct_answer=question.correct_answer or '',
            q_type=question.q_type or 'objective',
            max_score=question.get_max_score(),
            grading_points=question.grading_points,
            options=question.options,
            subjective_type=question.subjective_type or '主观题',
            user=user,
        )

        cached = {
            'score': result.get('score', 0),
            'max_score': question.get_max_score(),
            'is_correct': result.get('is_correct', False),
            'feedback': result.get('feedback', ''),
            'analysis': result.get('analysis', ''),
            'memorix_rating': result.get('memorix_rating', 2),
            'error_analysis': result.get('error_analysis'),
            'kp_name': question.knowledge_point.name if question.knowledge_point else '',
            'kp_id': question.knowledge_point_id,
        }
        cache.set(cache_key, cached, timeout=1800)  # 30min
        logger.info("pre_grade: session=%s qid=%d cached", session_id, question_id)

    except Exception as exc:
        logger.warning("pre_grade failed session=%s qid=%d: %s", session_id, question_id, exc)
        # 缓存错误标记，submit 时 fallback 到同步批改
        cache.set(cache_key, {'_error': str(exc)}, timeout=300)
