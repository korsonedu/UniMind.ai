from django.db import models
from django.conf import settings

class Notification(models.Model):
    TYPES = (
        ('qa_reply', '答疑回复'),
        ('system', '系统通知'),
        ('memorix_reminder', '复习提醒'),
        ('performance_alert', '绩效告警'),
        ('bulk_init', '初始化题库'),
        ('join_request', '加入申请'),
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


class Announcement(models.Model):
    AUDIENCE_CHOICES = (
        ('institution_owners', '仅机构所有者'),
        ('all_teachers', '全部老师'),
        ('everyone', '所有人'),
    )
    STATUS_CHOICES = (
        ('draft', '草稿'),
        ('published', '已发布'),
        ('archived', '已归档'),
    )

    publisher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='announcements')
    title = models.CharField(max_length=200)
    content = models.TextField()
    audience = models.CharField(max_length=20, choices=AUDIENCE_CHOICES, default='everyone')
    institution = models.ForeignKey('users.Institution', on_delete=models.CASCADE, null=True, blank=True, related_name='announcements')
    is_platform = models.BooleanField(default=False, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{'平台' if self.is_platform else '机构'}] {self.publisher.username} - {self.title}"


class AnnouncementRead(models.Model):
    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE, related_name='reads')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='announcement_reads')
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('announcement', 'user')
