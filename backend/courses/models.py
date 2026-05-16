from django.db import models
from django.conf import settings

from quizzes.models import KnowledgePoint

class Album(models.Model):
    name = models.CharField(max_length=100, verbose_name="专辑名称")
    description = models.TextField(blank=True, verbose_name="专辑描述")
    cover_image = models.ImageField(upload_to='album_covers/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Course(models.Model):
    title = models.CharField(max_length=200)
    album_obj = models.ForeignKey(Album, on_delete=models.SET_NULL, null=True, blank=True, related_name='courses', verbose_name="所属专辑")
    description = models.TextField(blank=True, null=True)
    knowledge_point = models.ForeignKey(KnowledgePoint, on_delete=models.SET_NULL, null=True, blank=True, related_name='courses', verbose_name="挂载知识点")
    cover_image = models.ImageField(upload_to='course_covers/', blank=True, null=True)
    video_file = models.FileField(upload_to='course_videos/', blank=True, null=True)
    elo_reward = models.IntegerField(default=50, verbose_name="观看完成奖励 ELO")
    courseware = models.FileField(upload_to='courseware/', blank=True, null=True, verbose_name="课件")
    reference_materials = models.FileField(upload_to='references/', blank=True, null=True, verbose_name="参考资料")
    ai_outline_enabled = models.BooleanField(default=True, verbose_name="启用AI智能大纲")
    institution = models.ForeignKey("users.Institution", on_delete=models.SET_NULL, null=True, blank=True, related_name="courses", verbose_name="所属机构")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True)

    def __str__(self):
        return self.title


class CourseOutline(models.Model):
    STATUS_CHOICES = [
        ('pending', '待处理'), ('generating', '生成中'),
        ('completed', '已完成'), ('failed', '失败'),
    ]
    course = models.OneToOneField(Course, on_delete=models.CASCADE, related_name='outline')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="大纲状态")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class OutlineItem(models.Model):
    outline = models.ForeignKey(CourseOutline, on_delete=models.CASCADE, related_name='items')
    title = models.CharField(max_length=200, verbose_name="章节标题")
    timestamp = models.FloatField(verbose_name="时间戳（秒）")
    description = models.TextField(blank=True, verbose_name="内容摘要")
    index = models.PositiveIntegerField(verbose_name="显示排序")

    class Meta:
        ordering = ['index']


class VideoTranscript(models.Model):
    ASR_STATUS_CHOICES = [
        ('pending', '待处理'), ('processing', '转录中'),
        ('completed', '已完成'), ('failed', '失败'),
    ]
    course = models.OneToOneField(Course, on_delete=models.CASCADE, related_name='transcript')
    language = models.CharField(max_length=10, default='zh', verbose_name="语言")
    full_text = models.TextField(blank=True, verbose_name="完整文本")
    asr_status = models.CharField(max_length=20, choices=ASR_STATUS_CHOICES, default='pending', verbose_name="转录状态")
    asr_provider = models.CharField(max_length=50, blank=True, verbose_name="ASR 提供者")
    error_message = models.TextField(blank=True, verbose_name="错误信息")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class TranscriptSegment(models.Model):
    transcript = models.ForeignKey(VideoTranscript, on_delete=models.CASCADE, related_name='segments')
    start_time = models.FloatField(verbose_name="开始时间（秒）")
    end_time = models.FloatField(verbose_name="结束时间（秒）")
    text = models.TextField(verbose_name="文本内容")
    index = models.PositiveIntegerField(verbose_name="片段序号")

    class Meta:
        ordering = ['index']


class CourseVideoQuestion(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='video_questions')
    question_data = models.JSONField(verbose_name="题目数据")
    question_id = models.ForeignKey('quizzes.Question', on_delete=models.SET_NULL, null=True, blank=True, help_text="如果已持久化到主题库则为关联 ID", verbose_name="关联题目")
    is_active = models.BooleanField(default=True, verbose_name="是否有效")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

class StartupMaterial(models.Model):
    name = models.CharField(max_length=200, verbose_name="资料名称")
    description = models.TextField(blank=True, verbose_name="资料简介")
    file = models.FileField(upload_to='startup_materials/', verbose_name="文件")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class VideoProgress(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='progress_records')
    last_position = models.FloatField(default=0, help_text="上次观看位置（秒）")
    is_finished = models.BooleanField(default=False, verbose_name="是否观看完成")
    elo_claimed_at = models.DateTimeField(null=True, blank=True, verbose_name="ELO 奖励领取时间")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'course')

    def __str__(self):
        return f"{self.user.username} - {self.course.title} ({'完成' if self.is_finished else '进行中'})"
