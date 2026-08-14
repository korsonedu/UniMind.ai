from django.db import models
from django.conf import settings
from django.utils import timezone
from core.fields import EncryptedCharField, EncryptedTextField


class InstitutionUsageLog(models.Model):
    """机构用量日志（按月聚合）"""
    institution = models.ForeignKey(
        'Institution', on_delete=models.CASCADE, related_name='usage_logs',
    )
    period_start = models.DateField(verbose_name='计费周期起始')

    # 月计型用量字段
    ai_generation_count = models.IntegerField(default=0, verbose_name='AI 出题次数(旧)')
    ai_question_count = models.IntegerField(default=0, verbose_name='AI 出题次数')
    ai_call_total_count = models.IntegerField(default=0, verbose_name='AI 调用总次数(不含ASR)')
    pdf_export_count = models.IntegerField(default=0, verbose_name='模拟考试PDF次数')
    interview_count = models.IntegerField(default=0, verbose_name='面试场次')

    class Meta:
        unique_together = [('institution', 'period_start')]
        verbose_name = '机构用量日志'
        verbose_name_plural = '机构用量日志'
        ordering = ['-period_start']

    def __str__(self):
        return f'{self.institution.name} — {self.period_start}: q={self.ai_question_count} ai={self.ai_call_total_count}'


class InstitutionAuditLog(models.Model):
    """机构操作审计日志"""
    institution = models.ForeignKey(
        'Institution', on_delete=models.CASCADE, related_name='audit_logs',
    )
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='institution_audit_actions',
    )
    action = models.CharField(max_length=50, verbose_name='操作类型')
    detail = models.TextField(blank=True, verbose_name='详情')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='操作时间')

    class Meta:
        verbose_name = '机构操作日志'
        verbose_name_plural = '机构操作日志'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.institution.name} — {self.action} @ {self.created_at}'


# ── Layer 2: 机构自有收款配置（Pro 版）──


class InstitutionNotificationConfig(models.Model):
    """机构通知配置 — 到期复习提醒的渠道和频率设置"""
    institution = models.OneToOneField(
        'Institution', on_delete=models.CASCADE, related_name='notification_config',
        verbose_name='所属机构',
    )
    enabled = models.BooleanField(default=False, verbose_name='启用到期提醒')
    channel = models.CharField(
        max_length=20,
        choices=[('email', '邮件'), ('feishu', '飞书')],
        default='email',
        verbose_name='通知渠道',
    )
    due_threshold = models.IntegerField(
        default=5,
        verbose_name='触发阈值',
        help_text='学生到期题目超过此数量时发送通知',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '机构通知配置'
        verbose_name_plural = '机构通知配置'

    def __str__(self):
        status = "开" if self.enabled else "关"
        return f'{self.institution.name} 通知配置 ({status})'
