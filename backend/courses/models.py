from django.db import models
from django.conf import settings

from quizzes.models import KnowledgePoint


def institution_upload_path(instance, filename):
    """按机构隔离的文件上传路径"""
    institution_id = instance.institution_id or "public"
    return f"institutions/{institution_id}/{filename}"


class Album(models.Model):
    name = models.CharField(max_length=100, verbose_name="专辑名称")
    description = models.TextField(blank=True, verbose_name="专辑描述")
    cover_image = models.ImageField(upload_to='album_covers/', blank=True, null=True)
    institution = models.ForeignKey("users.Institution", on_delete=models.SET_NULL, null=True, blank=True, related_name="albums", verbose_name="所属机构")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Course(models.Model):
    title = models.CharField(max_length=200)
    album_obj = models.ForeignKey(Album, on_delete=models.SET_NULL, null=True, blank=True, related_name='courses', verbose_name="所属专辑")
    description = models.TextField(blank=True, null=True)
    knowledge_point = models.ForeignKey(KnowledgePoint, on_delete=models.SET_NULL, null=True, blank=True, related_name='courses', verbose_name="挂载知识点")
    cover_image = models.ImageField(upload_to=institution_upload_path, blank=True, null=True)
    video_file = models.FileField(upload_to=institution_upload_path, blank=True, null=True)
    elo_reward = models.IntegerField(default=50, verbose_name="观看完成奖励 ELO")
    courseware = models.FileField(upload_to=institution_upload_path, blank=True, null=True, verbose_name="课件")
    reference_materials = models.FileField(upload_to=institution_upload_path, blank=True, null=True, verbose_name="参考资料")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="专辑内排序")
    ai_outline_enabled = models.BooleanField(default=True, verbose_name="启用AI智能大纲")
    institution = models.ForeignKey("users.Institution", on_delete=models.SET_NULL, null=True, blank=True, related_name="courses", verbose_name="所属机构")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # 如果是更新操作，清理旧文件
        if self.pk:
            try:
                old_instance = Course.objects.get(pk=self.pk)
                # 清理旧的视频文件
                if old_instance.video_file and old_instance.video_file != self.video_file:
                    old_instance.video_file.delete(save=False)
                # 清理旧的封面图片
                if old_instance.cover_image and old_instance.cover_image != self.cover_image:
                    old_instance.cover_image.delete(save=False)
                # 清理旧的课件
                if old_instance.courseware and old_instance.courseware != self.courseware:
                    old_instance.courseware.delete(save=False)
                # 清理旧的参考资料
                if old_instance.reference_materials and old_instance.reference_materials != self.reference_materials:
                    old_instance.reference_materials.delete(save=False)
            except Course.DoesNotExist:
                pass

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # 删除时清理所有文件
        if self.video_file:
            self.video_file.delete(save=False)
        if self.cover_image:
            self.cover_image.delete(save=False)
        if self.courseware:
            self.courseware.delete(save=False)
        if self.reference_materials:
            self.reference_materials.delete(save=False)

        super().delete(*args, **kwargs)


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
    institution = models.ForeignKey("users.Institution", on_delete=models.SET_NULL, null=True, blank=True, related_name="startup_materials", verbose_name="所属机构")
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


class CourseTag(models.Model):
    institution = models.ForeignKey("users.Institution", on_delete=models.CASCADE, related_name="course_tags")
    name = models.CharField(max_length=50, verbose_name="标签名")
    slug = models.SlugField(max_length=60, verbose_name="URL标识")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('institution', 'slug')

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class CourseTagRelation(models.Model):
    course = models.ForeignKey('Course', on_delete=models.CASCADE, related_name='tag_relations')
    tag = models.ForeignKey(CourseTag, on_delete=models.CASCADE, related_name='course_relations')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('course', 'tag')


class TeachingPlan(models.Model):
    """教学计划：按班级+学科，按周规划教学进度。"""
    institution = models.ForeignKey('users.Institution', on_delete=models.CASCADE, related_name='teaching_plans')
    class_obj = models.ForeignKey('users.Class', on_delete=models.CASCADE, related_name='teaching_plans')
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    subject = models.CharField(max_length=100, verbose_name='学科', help_text='如 金融431、高中数学')
    semester = models.CharField(max_length=50, verbose_name='学期', help_text='如 2026-春季')
    week_count = models.PositiveSmallIntegerField(default=18, verbose_name='教学周数')
    weekly_plans = models.JSONField(null=True, blank=True, verbose_name='周计划', help_text='[{week:1,topic:"",objectives:"",kp_ids:[],materials:""}]')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_teaching_plans')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = [('class_obj', 'subject', 'semester')]

    def __str__(self):
        return f'{self.title} ({self.semester})'


class LessonPlan(models.Model):
    """教案：单课教学设计，支持 AI 生成。"""
    teaching_plan = models.ForeignKey(TeachingPlan, on_delete=models.CASCADE, null=True, blank=True, related_name='lesson_plans')
    institution = models.ForeignKey('users.Institution', on_delete=models.CASCADE, related_name='lesson_plans')
    title = models.CharField(max_length=500, verbose_name='课题')
    objectives = models.TextField(blank=True, verbose_name='教学目标')
    knowledge_points = models.ManyToManyField('quizzes.KnowledgePoint', blank=True, related_name='lesson_plans', verbose_name='知识点')
    activities = models.JSONField(null=True, blank=True, verbose_name='教学活动', help_text='[{name:"导入",duration:5,description:""}]')
    materials = models.JSONField(null=True, blank=True, verbose_name='教学材料', help_text='["PPT","视频","实验器材"]')
    ai_generated = models.JSONField(null=True, blank=True, verbose_name='AI 生成内容', help_text='LLM 生成的教案详细内容')
    duration_minutes = models.PositiveSmallIntegerField(default=45, verbose_name='课时(分钟)')
    week_number = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='所属周')
    order = models.PositiveIntegerField(default=0, verbose_name='排序')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_lesson_plans')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['teaching_plan', 'week_number', 'order']

    def __str__(self):
        return self.title
