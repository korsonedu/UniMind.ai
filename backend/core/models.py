from django.db import models


class PromptTemplate(models.Model):
    """
    Prompt 模板（过渡期保留 — Phase 2 将迁移至文件系统）。

    注意：model_provider 字段已移除，AI 模型配置统一在 settings.py 的
    AI_MODEL_CONFIG 字典中维护。
    """
    name = models.CharField(max_length=100, unique=True, help_text="例如: AI_QUESTION_REVIEWER")
    version = models.CharField(max_length=20, help_text="例如: v1.2.0")
    content = models.TextField(help_text="Prompt 的系统指令内容, 支持 Jinja2/F-string 变量占位符")
    agent_role = models.CharField(
        max_length=50,
        choices=[('AUTHOR', '出题者'), ('REVIEWER', '审核者'), ('CLASSIFIER', '分类器'),
                 ('GRADER', '评分者'), ('ASSISTANT', '助教'), ('PARSER', '解析器')],
        default='AUTHOR'
    )
    temperature = models.FloatField(default=0.7)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.version})"


TASK_TYPE_CHOICES = (
    ('chat', 'AI 助教对话'),
    ('generate_author', '出题 — Author'),
    ('generate_reviewer', '出题 — Reviewer'),
    ('generate_classifier', '出题 — Classifier'),
    ('grade_subjective', '主观题评分'),
    ('parse_text', '文本解析'),
    ('generate_answer', '生成题目解析'),
    ('essay_grade', '作文精细评分'),
    ('interview', '模拟面试'),
    ('schema_repair', 'JSON 结构修复'),
    ('fallback', '通用回退'),
)


class PromptQualityLog(models.Model):
    """追踪 prompt 版本在各任务中的效果。"""
    prompt_name = models.CharField(max_length=100, default='', verbose_name="Prompt 名称")
    task_type = models.CharField(max_length=30, choices=TASK_TYPE_CHOICES, verbose_name="任务类型")
    pipeline_task = models.ForeignKey('quizzes.ContentPipelineTask', on_delete=models.SET_NULL, null=True, blank=True, related_name='prompt_logs')
    prompt_version = models.CharField(max_length=20, verbose_name="使用的 Prompt 版本")
    accepted = models.BooleanField(default=False, verbose_name="结果是否被接受")
    quality_score = models.FloatField(null=True, blank=True, verbose_name="质量分 (0-1)")
    error_message = models.TextField(blank=True, verbose_name="错误信息")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="额外元数据")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['prompt_name', '-created_at']),
            models.Index(fields=['task_type', 'accepted']),
        ]

    def __str__(self):
        return f"PromptQualityLog #{self.id} ({self.task_type} v{self.prompt_version})"


class SecurityAuditLog(models.Model):
    """安全审计日志 — 等保二级要求：登录/权限/异常操作记录，保留≥6个月。"""

    EVENT_CHOICES = (
        ('login_success', '登录成功'),
        ('login_failure', '登录失败'),
        ('login_locked', '账号锁定'),
        ('password_change', '密码变更'),
        ('permission_change', '权限变更'),
        ('admin_action', '管理操作'),
    )

    event_type = models.CharField(max_length=30, choices=EVENT_CHOICES, verbose_name="事件类型")
    user = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='security_audit_logs', verbose_name="用户",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP 地址")
    user_agent = models.CharField(max_length=255, blank=True, verbose_name="User-Agent")
    detail = models.TextField(blank=True, verbose_name="详情")
    request_id = models.CharField(max_length=64, blank=True, verbose_name="Request ID")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="发生时间")

    class Meta:
        verbose_name = '安全审计日志'
        verbose_name_plural = '安全审计日志'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['event_type', '-created_at']),
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return f"{self.get_event_type_display()} — {self.user or 'anonymous'} @ {self.created_at}"
