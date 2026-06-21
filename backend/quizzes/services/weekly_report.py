"""学习周报服务 — 聚合学生一周学习数据。"""
from datetime import timedelta
from django.utils import timezone


def build_weekly_report_data(student) -> dict:
    now = timezone.now()
    week_start = now - timedelta(days=7)

    from quizzes.models import ReviewLog, UserKnowledgeState, OnlineExamAttempt
    from users.models import DailyCheckIn

    # 复习次数
    reviews = ReviewLog.objects.filter(user=student, review_time__gte=week_start).count()

    # 正确率 — 基于 Grade 评分: Good(3)/Easy(4) 视为掌握良好
    good_reviews = ReviewLog.objects.filter(
        user=student, review_time__gte=week_start, grade__in=[3, 4]
    ).count()
    accuracy = round(good_reviews / max(reviews, 1) * 100)

    # 新增掌握知识点
    new_mastered = UserKnowledgeState.objects.filter(
        user=student, mastery_score__gte=80,
        updated_at__gte=week_start,
    ).count()

    # 签到天数
    checkins = DailyCheckIn.objects.filter(
        user=student, date__gte=week_start.date()
    ).count()

    # 考试次数
    exams_taken = OnlineExamAttempt.objects.filter(
        user=student, started_at__gte=week_start
    ).count()

    # 总学习时长（估算：每次复习约 2 分钟）
    total_minutes = reviews * 2

    return {
        'student_name': student.nickname or student.username,
        'week_start': week_start.date().isoformat(),
        'week_end': now.date().isoformat(),
        'reviews': reviews,
        'accuracy': accuracy,
        'new_mastered_kps': new_mastered,
        'checkins': checkins,
        'exams_taken': exams_taken,
        'total_minutes': total_minutes,
    }
