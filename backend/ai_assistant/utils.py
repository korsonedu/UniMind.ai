import concurrent.futures

_THREAD_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=10, thread_name_prefix='ai-chat')

from django.utils import timezone
from django.db.models import Count, Q, Avg
from quizzes.models import UserQuestionStatus, Question, KnowledgePoint

def get_student_academic_context(user):
    """
    提取解耦的学生学术数据，并生成用于 AI 的 System Prompt 增强文本
    """
    now = timezone.now()
    
    # 1. 基础积分与身份
    elo_score = user.elo_score
    username = user.username
    
    # 2. 统计复习压力（Memorix 到期量）
    urgent_review_count = UserQuestionStatus.objects.filter(
        user=user, 
        next_review_at__lte=now
    ).count()
    
    # 3. 寻找弱项知识点 (按错误次数排序)
    weak_points_data = UserQuestionStatus.objects.filter(user=user, wrong_count__gt=0).values(
        'question__knowledge_point__name'
    ).annotate(
        total_wrong=Count('id')
    ).order_by('-total_wrong')[:3]
    
    weak_points = [item['question__knowledge_point__name'] for item in weak_points_data if item['question__knowledge_point__name']]
    
    # 4. 提取具体的错题样本 (最近错的 5 道题)
    recent_wrongs = UserQuestionStatus.objects.filter(
        user=user, 
        last_correct=False
    ).select_related('question').order_by('-id')[:5]
    
    wrong_samples = []
    for ws in recent_wrongs:
        q = ws.question
        wrong_samples.append(f"- 题目: {q.text}\n  标准答案: {q.correct_answer}\n  错误频次: {ws.wrong_count}次")

    # 5. 优势领域
    strong_points_data = UserQuestionStatus.objects.filter(user=user, last_correct=True).values(
        'question__knowledge_point__name'
    ).annotate(
        total_correct=Count('id')
    ).order_by('-total_correct')[:2]
    
    strong_points = [item['question__knowledge_point__name'] for item in strong_points_data if item['question__knowledge_point__name']]

    # 6. 组装成 AI 提示词
    context_segments = [
        f"当前学生用户: {username}。",
        f"学术天梯积分 (ELO): {elo_score}。",
    ]
    
    if weak_points:
        context_segments.append(f"薄弱知识点: {', '.join(weak_points)}。")
    
    if wrong_samples:
        context_segments.append("该生最近练习中的真实错题样本如下：\n" + "\n".join(wrong_samples))
    
    if strong_points:
        context_segments.append(f"优势领域: {', '.join(strong_points)}。")
        
    if urgent_review_count > 0:
        context_segments.append(f"今日该生有 {urgent_review_count} 道题目已到达间隔重复复习临界点，建议在对话结束时给予温馨提醒。")
    else:
        context_segments.append("该生今日复习任务已完成，状态良好。")

    return "\n".join(context_segments)
