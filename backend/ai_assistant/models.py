from django.db import models
from django.conf import settings
import uuid

class AIChatMessage(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=20) # 'user' or 'assistant'
    content = models.TextField()
    bot = models.ForeignKey('Bot', on_delete=models.CASCADE, null=True, blank=True)
    conversation_id = models.UUIDField(default=uuid.uuid4, db_index=True, help_text="会话 ID，用于区分不同对话")
    metadata = models.JSONField(default=dict, blank=True, help_text="工具返回的结构化数据（如生成的题目、管线 task_id）")
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

class Bot(models.Model):
    BOT_TYPE_CHOICES = (
        ('planner', '学习教练'),
        ('exam_generator', '命题官'),
    )
    name = models.CharField(max_length=100)
    avatar = models.ImageField(upload_to='bot_avatars/', blank=True, null=True)
    system_prompt = models.TextField()
    bot_type = models.CharField(max_length=20, choices=BOT_TYPE_CHOICES, default='planner', verbose_name="机器人类型")
    is_exclusive = models.BooleanField(default=False, verbose_name="是否为专属导师")
    is_active = models.BooleanField(default=True)
    institution = models.ForeignKey(
        'users.Institution', on_delete=models.CASCADE,
        null=True, blank=True, related_name='bots',
        verbose_name="所属机构",
    )
    institution_personality = models.JSONField(
        default=dict, blank=True,
        verbose_name="机构人格配置",
        help_text="机构自定义人格配置：教学风格、知识范围、语气等",
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
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'memory_type', 'key'],
                name='uniq_user_memory_type_key',
            ),
        ]
        indexes = [
            models.Index(fields=['user', 'memory_type', 'is_active']),
            models.Index(fields=['user', 'is_active', 'confidence']),
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


class ActionCardInteraction(models.Model):
    """追踪学生通过 Action Card 的交互行为（点击、完成）。

    面向 VC 的数据基础：哪些卡片被学生实际使用了、转化率如何。
    """
    ACTION_TYPES = (
        ('video', '视频'), ('quiz', '做题'), ('review', '复习'),
        ('course', '课程'), ('chart', '图表'), ('plan', '计划'), ('exam', '考试'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='card_interactions')
    card_title = models.CharField(max_length=200, verbose_name="卡片标题")
    card_action_type = models.CharField(max_length=20, choices=ACTION_TYPES, verbose_name="动作类型")
    card_action_url = models.CharField(max_length=500, verbose_name="跳转 URL")
    card_icon = models.CharField(max_length=20, blank=True, default='', verbose_name="图标类型")
    card_description = models.TextField(blank=True, default='', verbose_name="卡片描述")

    clicked = models.BooleanField(default=True, verbose_name="已点击")
    completed = models.BooleanField(default=False, verbose_name="已完成")
    clicked_at = models.DateTimeField(auto_now_add=True, verbose_name="点击时间")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="完成时间")

    metadata = models.JSONField(default=dict, blank=True, help_text="额外数据：题目 ID、课程 ID 等")

    class Meta:
        ordering = ['-clicked_at']
        indexes = [
            models.Index(fields=['user', 'card_action_type']),
            models.Index(fields=['user', 'completed']),
        ]
        verbose_name = '行动卡片交互'
        verbose_name_plural = '行动卡片交互'

    def __str__(self):
        status = '✅' if self.completed else '⬜'
        return f"{status} {self.user} - {self.card_title}"


class AITrajectory(models.Model):
    """Agent 对话轨迹，用于后续 GEPA 自进化优化。"""
    
    OUTCOME_CHOICES = (
        ('success', '成功'),
        ('partial', '部分成功'),
        ('failure', '失败'),
        ('unknown', '未知'),
    )
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='trajectories')
    bot = models.ForeignKey('Bot', on_delete=models.CASCADE, related_name='trajectories')
    conversation_id = models.UUIDField(db_index=True)
    
    # Trajectory 数据
    messages = models.JSONField(help_text="完整对话记录")
    tool_calls = models.JSONField(default=list, help_text="工具调用序列")
    tool_outputs = models.JSONField(default=list, help_text="工具返回结果")
    
    # 结果评估
    outcome = models.CharField(max_length=20, choices=OUTCOME_CHOICES, default='unknown')
    outcome_metrics = models.JSONField(default=dict, help_text="结果指标：掌握率变化、任务完成度等")
    
    # Prompt 变体（用于 A/B 测试）
    prompt_variant = models.CharField(max_length=50, default='baseline', help_text="使用的 prompt 变体标识")
    
    # 元数据
    created_at = models.DateTimeField(auto_now_add=True)
    evaluated_at = models.DateTimeField(null=True, blank=True, help_text="结果评估时间")
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'bot', 'created_at']),
            models.Index(fields=['conversation_id']),
            models.Index(fields=['outcome', 'created_at']),
        ]
        verbose_name = '对话轨迹'
        verbose_name_plural = '对话轨迹'
    
    def __str__(self):
        return f"{self.user} - {self.bot.name} - {self.conversation_id}"
