from django.db import models
from django.conf import settings

class AIChatMessage(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=20) # 'user' or 'assistant'
    content = models.TextField()
    bot = models.ForeignKey('Bot', on_delete=models.CASCADE, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

class Bot(models.Model):
    name = models.CharField(max_length=100)
    avatar = models.ImageField(upload_to='bot_avatars/', blank=True, null=True)
    system_prompt = models.TextField()
    is_exclusive = models.BooleanField(default=False, verbose_name="是否为专属导师")
    is_active = models.BooleanField(default=True)
    institution = models.ForeignKey(
        'users.Institution', on_delete=models.CASCADE,
        null=True, blank=True, related_name='bots',
        verbose_name="所属机构",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class BotVisibility(models.Model):
    """机构对全局 bot 的可见性控制。"""
    institution = models.ForeignKey(
        'users.Institution', on_delete=models.CASCADE,
        related_name='hidden_bots',
    )
    bot = models.ForeignKey(
        Bot, on_delete=models.CASCADE,
        related_name='hidden_for',
    )
    is_visible = models.BooleanField(default=True, verbose_name="是否对学员可见")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('institution', 'bot')]
        verbose_name = '机器人可见性'
        verbose_name_plural = '机器人可见性'

    def __str__(self):
        return f"{self.institution.name} - {self.bot.name}: {'可见' if self.is_visible else '隐藏'}"
