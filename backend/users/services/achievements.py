"""
预置成就定义 + 自动解锁信号。
用法：在 AppConfig.ready() 中调用 seed_achievements() + connect_achievement_signals()
"""
from django.db.models.signals import post_save
from django.dispatch import receiver


PRESET_ACHIEVEMENTS = [
    # 连续打卡
    {'key': 'streak_3', 'name': '三日坚持', 'description': '连续打卡 3 天', 'icon': '🔥', 'category': 'streak', 'threshold': 3},
    {'key': 'streak_7', 'name': '周常打卡', 'description': '连续打卡 7 天', 'icon': '🔥', 'category': 'streak', 'threshold': 7},
    {'key': 'streak_30', 'name': '月度战神', 'description': '连续打卡 30 天', 'icon': '💪', 'category': 'streak', 'threshold': 30},
    # 刷题里程碑
    {'key': 'questions_10', 'name': '初出茅庐', 'description': '累计刷题 10 道', 'icon': '📝', 'category': 'question', 'threshold': 10},
    {'key': 'questions_100', 'name': '百题斩', 'description': '累计刷题 100 道', 'icon': '⚔️', 'category': 'question', 'threshold': 100},
    {'key': 'questions_500', 'name': '刷题狂魔', 'description': '累计刷题 500 道', 'icon': '📚', 'category': 'question', 'threshold': 500},
    # 首次诊断
    {'key': 'first_diagnostic', 'name': '认识自己', 'description': '完成首次诊断测试', 'icon': '🔍', 'category': 'diagnostic', 'threshold': 1},
    # 知识点掌握
    {'key': 'master_5', 'name': '小有所成', 'description': '掌握 5 个知识点', 'icon': '⭐', 'category': 'mastery', 'threshold': 5},
    {'key': 'master_20', 'name': '学识渊博', 'description': '掌握 20 个知识点', 'icon': '🌟', 'category': 'mastery', 'threshold': 20},
    # 考试成绩
    {'key': 'exam_90', 'name': '学霸认证', 'description': '单次考试成绩 90% 以上', 'icon': '🎓', 'category': 'exam', 'threshold': 90},
]


def seed_achievements():
    """幂等创建预置成就。每次启动调用，已存在的跳过。"""
    from users.models import Achievement
    for a in PRESET_ACHIEVEMENTS:
        Achievement.objects.get_or_create(key=a['key'], defaults=a)


def check_and_unlock(user):
    """检查用户各项数据，解锁符合条件的成就。"""
    from users.models import Achievement, UserAchievement
    from django.utils import timezone

    # 已解锁的 key set
    unlocked = set(
        UserAchievement.objects.filter(user=user)
        .select_related('achievement')
        .values_list('achievement__key', flat=True)
    )

    def unlock(ach_key):
        if ach_key in unlocked:
            return
        ach = Achievement.objects.get(key=ach_key)
        UserAchievement.objects.create(user=user, achievement=ach)

    # 连续打卡
    from users.models import DailyCheckIn
    latest = DailyCheckIn.objects.filter(user=user).order_by('-date').first()
    streak = latest.streak if latest else 0

    # 检查今天是否签到（如果最近签到不是今天，streak 重置的 handle 在签到逻辑中）
    from datetime import date
    if latest and latest.date == date.today():
        if streak >= 30:
            unlock('streak_30')
        if streak >= 7:
            unlock('streak_7')
        if streak >= 3:
            unlock('streak_3')

    # 刷题里程碑
    from quizzes.models import QuizAttempt
    total = QuizAttempt.objects.filter(user=user).count()
    if total >= 500:
        unlock('questions_500')
    if total >= 100:
        unlock('questions_100')
    if total >= 10:
        unlock('questions_10')

    # 首次诊断
    if user.has_completed_initial_assessment:
        unlock('first_diagnostic')

    # 知识点掌握
    from quizzes.models import UserQuestionStatus
    mastered = UserQuestionStatus.objects.filter(
        user=user, is_mastered=True,
    ).values('question__qmatrixentry__knowledge_point').distinct().count()
    if mastered >= 20:
        unlock('master_20')
    if mastered >= 5:
        unlock('master_5')

    # 考试成绩 — 由考试提交信号触发


def connect_achievement_signals():
    """注册信号处理器：在关键操作后自动检查成就解锁。"""
    from django.db.models.signals import post_save
    from users.models import DailyCheckIn

    @receiver(post_save, sender=DailyCheckIn)
    def _on_checkin(sender, instance, created, **kwargs):
        if created:
            check_and_unlock(instance.user)

    # 诊断完成已在 views 中直接设置 has_completed_initial_assessment=True，
    # achievement 的 first_diagnostic 由 check_and_unlock 根据该字段解锁。
    # 考试成就 (exam_90) 待考试系统稳定后再接信号。
