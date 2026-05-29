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


# ──────────────────────────────────────────────
# 平台数据分析
# ──────────────────────────────────────────────

class AnalyticsEvent(models.Model):
    """轻量级业务事件，用于平台统计分析（仅超管可见）。"""
    EVENT_TYPES = [
        ('user_login', '用户登录'),
        ('diagnostic_start', '诊断开始'),
        ('diagnostic_complete', '诊断完成'),
        ('quiz_attempt', '刷题'),
        ('ai_chat_start', 'AI对话开始'),
        ('course_view', '课程浏览'),
        ('course_complete', '课程完成'),
        ('pdf_export', 'PDF导出'),
        ('invite_click', '邀请链接点击'),
    ]
    event_type = models.CharField(max_length=50, choices=EVENT_TYPES, db_index=True)
    user = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='analytics_events', verbose_name="用户",
    )
    institution = models.ForeignKey(
        'users.Institution', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='analytics_events', verbose_name="机构",
    )
    properties = models.JSONField(default=dict, blank=True, verbose_name="属性")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="发生时间")

    class Meta:
        db_table = 'core_analytics_event'
        verbose_name = '分析事件'
        verbose_name_plural = '分析事件'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['event_type', 'created_at']),
            models.Index(fields=['institution', 'created_at']),
        ]

    def __str__(self):
        return f"{self.get_event_type_display()} — {self.user or '-'} @ {self.created_at:%Y-%m-%d}"


class DailyPlatformStats(models.Model):
    """每日平台聚合指标快照，超管 Dashboard 专用。"""
    date = models.DateField(unique=True, verbose_name="日期")

    # 用户
    total_users = models.IntegerField(default=0, verbose_name="总用户数")
    new_users = models.IntegerField(default=0, verbose_name="新增用户")
    dau = models.IntegerField(default=0, verbose_name="DAU")
    wau = models.IntegerField(default=0, verbose_name="WAU")
    mau = models.IntegerField(default=0, verbose_name="MAU")

    # 机构
    total_institutions = models.IntegerField(default=0, verbose_name="总机构数")
    new_institutions = models.IntegerField(default=0, verbose_name="新增机构")
    active_institutions = models.IntegerField(default=0, verbose_name="活跃机构")

    # 学习
    quiz_attempts = models.IntegerField(default=0, verbose_name="答题次数")
    quiz_correct_rate = models.FloatField(default=0, verbose_name="答题正确率")
    diagnostic_completions = models.IntegerField(default=0, verbose_name="诊断完成数")

    # AI
    ai_chat_sessions = models.IntegerField(default=0, verbose_name="AI对话次数")
    ai_calls_total = models.IntegerField(default=0, verbose_name="AI调用总量")

    # 课程
    course_views = models.IntegerField(default=0, verbose_name="课程浏览")
    course_completions = models.IntegerField(default=0, verbose_name="课程完成")
    pdf_exports = models.IntegerField(default=0, verbose_name="PDF导出")

    # 留存
    day1_retention = models.FloatField(default=0, verbose_name="次日留存率")
    day7_retention = models.FloatField(default=0, verbose_name="7日留存率")
    day30_retention = models.FloatField(default=0, verbose_name="30日留存率")

    class Meta:
        db_table = 'core_daily_platform_stats'
        verbose_name = '每日平台统计'
        verbose_name_plural = '每日平台统计'
        ordering = ['-date']

    def __str__(self):
        return f"平台统计 {self.date}"


class NPSSurvey(models.Model):
    """NPS 问卷响应，用于产品满意度追踪。"""
    user = models.ForeignKey(
        'users.User', on_delete=models.CASCADE,
        related_name='nps_surveys', verbose_name="用户",
    )
    score = models.IntegerField(verbose_name="评分 (0-10)")
    feedback = models.TextField(blank=True, default='', verbose_name="文字反馈")
    source = models.CharField(
        max_length=50, default='auto',
        choices=[('auto', '系统弹出'), ('manual', '主动提交')],
        verbose_name="来源",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="提交时间")

    class Meta:
        db_table = 'core_nps_survey'
        verbose_name = 'NPS问卷'
        verbose_name_plural = 'NPS问卷'
        ordering = ['-created_at']

    @property
    def category(self):
        """NPS 分类：promoter / passive / detractor"""
        if self.score >= 9:
            return 'promoter'
        elif self.score >= 7:
            return 'passive'
        return 'detractor'

    def __str__(self):
        return f"NPS {self.score} ({self.category}) — {self.user}"
