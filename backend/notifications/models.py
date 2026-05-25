from django.db import models
from django.conf import settings

class Notification(models.Model):
    TYPES = (
        ('qa_reply', '答疑回复'),
        ('system', '系统通知'),
        ('memorix_reminder', '复习提醒'),
        ('performance_alert', '绩效告警'),
    )
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    ntype = models.CharField(max_length=20, choices=TYPES, default='system', db_index=True)
    title = models.CharField(max_length=200)
    content = models.TextField()
    link = models.CharField(max_length=500, blank=True, null=True)
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.recipient.username} - {self.title}"
