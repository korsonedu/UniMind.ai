from django.db import models
from django.conf import settings

class StudyTask(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    task_name = models.CharField(max_length=200)
    duration_minutes = models.IntegerField(default=25)
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


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
    institution = models.ForeignKey("users.Institution", on_delete=models.SET_NULL, null=True, blank=True, related_name="chat_messages", verbose_name="所属机构")

    class Meta:
        ordering = ['timestamp']
