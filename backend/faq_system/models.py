from django.db import models
from django.conf import settings

class Question(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='faq_system_questions')
    content = models.TextField(verbose_name="问题描述")
    attachment = models.FileField(upload_to='qa_attachments/', blank=True, null=True, verbose_name="附件")
    is_solved = models.BooleanField(default=False, verbose_name="是否已解决")
    is_starred = models.BooleanField(default=False, verbose_name="是否星标")
    likes = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='liked_questions', blank=True, verbose_name="点赞用户")
    followers = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='followed_questions', blank=True, verbose_name="关注者")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

class Answer(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='answers')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField(verbose_name="回复内容")
    is_teacher = models.BooleanField(default=False, verbose_name="是否教师回答")
    likes = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='liked_answers', blank=True, verbose_name="点赞用户")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
