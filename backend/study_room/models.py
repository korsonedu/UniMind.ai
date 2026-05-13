from django.db import models
from django.conf import settings

class StudyTask(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    task_name = models.CharField(max_length=200)
    duration_minutes = models.IntegerField(default=25)
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class StudyPlan(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='macro_study_plan')
    target_date = models.DateField(verbose_name="目标考试日期")
    target_score = models.IntegerField(default=130, verbose_name="目标分数")
    daily_hours = models.FloatField(default=4.0, verbose_name="每日可用学习时长")
    weekly_summary = models.TextField(blank=True, null=True, verbose_name="AI周报摘要")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class WeeklyTask(models.Model):
    STATUS_CHOICES = [
        ('pending', '未开始'), ('in_progress', '进行中'), ('completed', '已完成'),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='weekly_tasks')
    title = models.CharField(max_length=200, verbose_name="任务标题")
    description = models.TextField(blank=True, verbose_name="任务说明")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    week_start = models.DateField(null=True, blank=True, verbose_name="计划周开始时间")
    week_end = models.DateField(null=True, blank=True, verbose_name="计划周结束时间")
    knowledge_point = models.ForeignKey('quizzes.KnowledgePoint', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


from users.models import DailyPlan

class ChatMessage(models.Model):
    MESSAGE_TYPE_CHOICES = [
        ('chat', '聊天消息'), ('task_start', '任务开始'), ('task_stop', '任务中止'),
        ('task_complete', '任务完成'), ('plan_complete', '计划完成'), ('plan_create', '制定计划'),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    related_plan = models.ForeignKey(DailyPlan, on_delete=models.CASCADE, null=True, blank=True, related_name='broadcast_messages')
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPE_CHOICES, default='chat', verbose_name="消息类型")

    class Meta:
        ordering = ['timestamp']
