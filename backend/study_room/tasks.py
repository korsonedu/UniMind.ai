import logging
from datetime import timedelta
from django.utils import timezone
from celery import shared_task
from django.contrib.auth import get_user_model
from core.prompt_manager import PromptManager
from ai_service import AIService
from quizzes.models import KnowledgePoint, UserKnowledgeState
from .models import StudyPlan, WeeklyTask
from .planner import build_macro_progress

logger = logging.getLogger(__name__)
User = get_user_model()

@shared_task
def generate_weekly_study_plan_for_all():
    """
    每周日晚调度，为所有设定了 StudyPlan 的用户生成下一周的 AI 学习计划
    """
    plans = StudyPlan.objects.all()
    for plan in plans:
        try:
            _generate_plan_for_user(plan)
        except Exception as e:
            logger.error(f"Failed to generate weekly plan for user {plan.user.username}: {e}")

def _generate_plan_for_user(plan):
    user = plan.user
    now = timezone.now().date()
    days_remaining = (plan.target_date - now).days
    
    if days_remaining <= 0:
        return
        
    progress = build_macro_progress(user=user, plan=plan)
    metrics = progress.get("metrics") or {}
    ideal_rate = float(metrics.get("ideal_rate") or 0.0)
    actual_rate = float(metrics.get("actual_rate") or 0.0)
    status_light = "绿灯（进度正常）" if metrics.get("status_light") == "green" else "红灯（进度落后）"
    
    # 获取薄弱点名称，用于 AI 参考
    weak_states = UserKnowledgeState.objects.filter(user=user, mastery_score__lt=0.6).select_related("knowledge_point")[:5]
    weak_kps = [s.knowledge_point.name for s in weak_states]
    
    prompt_config = PromptManager.get_prompt_config(
        "AI_WEEKLY_PLANNER", 
        "你是一个严谨的考研宏观规划导师。根据考生的剩余时间、学习进度（红绿灯）和薄弱点，为下周生成具体的任务清单。输出JSON: {'weekly_summary': '整体评价与建议', 'tasks': [{'title': '任务名称', 'description': '任务详情描述', 'kp_name': '关联考点名称'}]}。"
    )
    
    user_prompt = (
        f"距离考试天数：{days_remaining}\n"
        f"目标分数：{plan.target_score}\n"
        f"每天可用时间：{plan.daily_hours} 小时\n"
        f"当前进度状态：{status_light}\n"
        f"需重点关注的薄弱点：{', '.join(weak_kps)}\n"
        "请生成下周计划JSON。"
    )
    
    response = AIService.simple_chat_text(
        system_prompt=prompt_config.content,
        user_prompt=user_prompt,
        operation="study_room.weekly_planner",
        temperature=prompt_config.temperature,
    )
    
    parsed = AIService.extract_json(response) or {}
    
    # Save the weekly summary to the plan
    weekly_summary = parsed.get('weekly_summary', '')
    if weekly_summary:
        plan.weekly_summary = str(weekly_summary)
        plan.save(update_fields=['weekly_summary'])

    tasks_data = parsed.get('tasks', []) if isinstance(parsed, dict) else []
    if not isinstance(tasks_data, list):
        tasks_data = []
    
    # 清理旧的未完成任务，避免堆积重复计划。
    WeeklyTask.objects.filter(user=user, status__in=['pending', 'in_progress']).delete()
    
    week_start = now
    week_end = now + timedelta(days=7)
    
    for t_data in tasks_data[:20]:
        if not isinstance(t_data, dict):
            continue
        kp_name = t_data.get('kp_name')
        kp = KnowledgePoint.objects.filter(name=kp_name).first() if kp_name else None
        title = str(t_data.get('title') or '').strip() or '学习任务'
        description = str(t_data.get('description') or '').strip()
        WeeklyTask.objects.create(
            user=user,
            title=title[:200],
            description=description,
            knowledge_point=kp,
            week_start=week_start,
            week_end=week_end
        )

    # AI 未返回可用任务时，兜底至少生成 3 条规则任务。
    if not tasks_data:
        fallback_titles = [
            "复习薄弱知识点并输出错因清单",
            "完成一组计时训练并复盘",
            "整理本周知识图谱阻塞节点",
        ]
        for title in fallback_titles:
            WeeklyTask.objects.create(
                user=user,
                title=title,
                description=f"进度状态：{status_light}；理想速率 {ideal_rate:.2f}/日，实际速率 {actual_rate:.2f}/日。",
                week_start=week_start,
                week_end=week_end,
            )
