from django.db import models
from django.conf import settings

class ResumeRecord(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='resumes')
    original_file = models.FileField(upload_to='resumes/', null=True, blank=True)
    parsed_content = models.TextField(blank=True, help_text="OCR 解析的原始文本")
    optimized_content = models.JSONField(default=dict, blank=True, help_text="AI 润色后的结构化数据")
    predicted_questions = models.JSONField(default=list, blank=True, help_text="AI 针对简历预测的陷阱题")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}'s Resume ({self.created_at.date()})"

class InterviewSession(models.Model):
    SESSION_TYPES = (
        ('resume', '简历深挖'),
        ('english', '英语口语'),
        ('professional', '专业课(431)'),
        ('mixed', '综合面试')
    )
    STYLE_CHOICES = (
        ('friendly', '和蔼可亲(引导为主)'),
        ('pressure', '压力测试(刁钻追问)')
    )
    STATUS_CHOICES = (
        ('ongoing', '进行中'),
        ('completed', '已完成'),
        ('analyzing', '复盘分析中')
    )
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='interview_sessions')
    session_type = models.CharField(max_length=20, choices=SESSION_TYPES, default='professional')
    interviewer_style = models.CharField(max_length=20, choices=STYLE_CHOICES, default='friendly')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ongoing', db_index=True)
    
    radar_scores = models.JSONField(default=dict, blank=True, help_text="五维雷达图打分")
    overall_feedback = models.TextField(blank=True, help_text="面试总体评价")
    
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.get_session_type_display()} [{self.get_status_display()}]"

class InterviewTurn(models.Model):
    SPEAKER_CHOICES = (
        ('interviewer', '面试官'),
        ('candidate', '考生')
    )
    
    session = models.ForeignKey(InterviewSession, on_delete=models.CASCADE, related_name='turns')
    turn_number = models.IntegerField(default=1)
    speaker = models.CharField(max_length=20, choices=SPEAKER_CHOICES)
    content_text = models.TextField(blank=True, help_text="识别或生成的文本")
    audio_url = models.URLField(blank=True, help_text="对应的音频文件URL（TTS生成或STT录音）")
    latency_ms = models.IntegerField(default=0, help_text="响应延迟")
    feedback_for_turn = models.TextField(blank=True, help_text="针对本轮发言的 AI 批注（仅考生发言有）")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['turn_number', 'created_at']

    def __str__(self):
        return f"Session {self.session.id} Turn {self.turn_number}: {self.speaker}"
