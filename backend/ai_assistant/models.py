from django.db import models
from django.conf import settings

class AIChatMessage(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=20) # 'user' or 'assistant'
    content = models.TextField()
    bot = models.ForeignKey('Bot', on_delete=models.CASCADE, null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True, help_text="工具返回的结构化数据（如生成的题目、管线 task_id）")
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

class Bot(models.Model):
    BOT_TYPE_CHOICES = (
        ('assistant', '助教'),
        ('planner', '学习规划师'),
        ('exam_generator', '出题助手'),
    )
    name = models.CharField(max_length=100)
    avatar = models.ImageField(upload_to='bot_avatars/', blank=True, null=True)
    system_prompt = models.TextField()
    bot_type = models.CharField(max_length=20, choices=BOT_TYPE_CHOICES, default='assistant', verbose_name="机器人类型")
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


class AgentMemory(models.Model):
    """Agent 持久记忆：跨会话记住用户偏好、学业背景、教师上下文。"""
    MEMORY_TYPES = (
        ('preference', '偏好'),
        ('academic', '学业'),
        ('interaction', '交互'),
        ('teacher_context', '教师上下文'),
    )
    SOURCE_CHOICES = (
        ('auto', 'AI提取'),
        ('manual', '用户设置'),
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='agent_memories')
    memory_type = models.CharField(max_length=20, choices=MEMORY_TYPES, default='preference', db_index=True)
    key = models.CharField(max_length=200, verbose_name="记忆键", help_text="如: 偏好数学推导风格")
    value = models.TextField(verbose_name="记忆值", help_text="如: 喜欢用具体例子先引入，再给出严格证明")
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='auto')
    confidence = models.FloatField(default=0.5, help_text="置信度 0-1")
    last_used_at = models.DateTimeField(null=True, blank=True)
    use_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['user', 'memory_type', 'is_active']),
        ]

    def __str__(self):
        return f"[{self.memory_type}] {self.key}: {self.value[:30]}"


class StudyPlan(models.Model):
    STATUS_CHOICES = (
        ('active', '进行中'),
        ('completed', '已完成'),
        ('archived', '已归档'),
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='study_plans')
    bot = models.ForeignKey('Bot', on_delete=models.SET_NULL, null=True, blank=True, related_name='plans')
    title = models.CharField(max_length=200, verbose_name="计划标题")
    summary = models.TextField(blank=True, verbose_name="AI 生成的计划摘要")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', db_index=True)
    plan_data = models.JSONField(default=dict, help_text="AI 生成的完整计划 JSON，包含 tasks 数组")
    auto_generated = models.BooleanField(default=False, help_text="是否由 AI 自动生成")
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} - {self.title}"
