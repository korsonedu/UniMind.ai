from django.conf import settings
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from zoneinfo import ZoneInfo


class LearningSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    session_id = models.UUIDField()
    kind = models.CharField(max_length=10, choices=[('video', '听课'), ('practice', '做题')])
    course = models.ForeignKey('courses.Course', on_delete=models.SET_NULL, null=True, blank=True)
    question_ids = models.JSONField(default=list, blank=True)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(help_text='最近一次实际学习的时间，不含之后的挂机时间')
    active_seconds = models.PositiveIntegerField(default=0, help_text='实际播放或练习页面可见的秒数')
    focused_seconds = models.PositiveIntegerField(default=0, help_text='学习期间页面可见且窗口获得焦点的秒数，仅作专注参考')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'session_id'], name='unique_user_learning_session')]
        indexes = [models.Index(fields=['user', 'started_at'])]


class LearningProduct(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price_cents = models.PositiveIntegerField(default=0)
    duration_days = models.PositiveIntegerField(default=30)
    monthly_ai_calls = models.PositiveIntegerField(default=100)
    modules = models.ManyToManyField('courses.CourseModule', blank=True, related_name='learning_products')
    is_active = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return self.name

    def snapshot(self):
        return {'name': self.name, 'duration_days': self.duration_days,
                'monthly_ai_calls': self.monthly_ai_calls,
                'modules': list(self.modules.values_list('id', flat=True))}


class LearningGrant(models.Model):
    request_id = models.UUIDField(null=True, blank=True, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='learning_grants')
    product = models.ForeignKey(LearningProduct, on_delete=models.PROTECT, related_name='grants')
    order = models.OneToOneField('payments.Order', on_delete=models.PROTECT, null=True, blank=True, related_name='learning_grant')
    snapshot = models.JSONField(default=dict)
    source = models.CharField(max_length=20, choices=[('payment', '个人购买'), ('course', '课程配套'), ('admin', '管理员赠送')])
    starts_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    revoked = models.BooleanField(default=False)

    class Meta:
        ordering = ['-starts_at', '-id']


class LearningUsage(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='learning_usage')
    month = models.DateField()
    ai_calls = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'month'], name='unique_user_learning_month')]


class StudentCohort(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='批次名称')
    target_year = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)], verbose_name='目标届别',
        help_text='例如2027届；实际考试日期单独设置，不要求与届别同年。')
    exam_date = models.DateField(null=True, blank=True, verbose_name='实际考试日期')
    starts_on = models.DateField(verbose_name='服务开始日期（上海）')
    ends_on = models.DateField(verbose_name='服务结束日期（含当日）')
    is_active = models.BooleanField(default=False, verbose_name='启用批次')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-target_year', 'name']
        constraints = [models.CheckConstraint(condition=models.Q(ends_on__gte=models.F('starts_on')),
                       name='cohort_service_dates_ordered')]

    @property
    def state(self):
        if not self.is_active:
            return 'disabled'
        today = timezone.localdate(timezone=ZoneInfo('Asia/Shanghai'))
        return 'scheduled' if today < self.starts_on else 'expired' if today > self.ends_on else 'active'

    def __str__(self):
        return f'{self.target_year}届 · {self.name}'


class CourseStudentStatus(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='course_student_status')
    is_course_student = models.BooleanField(default=False)
    cohort = models.ForeignKey(StudentCohort, null=True, blank=True, on_delete=models.PROTECT, related_name='student_statuses')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)


class WeeklyAIQuotaConfig(models.Model):
    experience_calls = models.PositiveIntegerField(null=True, blank=True)
    course_calls = models.PositiveIntegerField(null=True, blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)


class AIAddonProduct(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price_cents = models.PositiveIntegerField(null=True, blank=True)
    ai_calls = models.PositiveIntegerField(null=True, blank=True)
    validity_days = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']

    def snapshot(self):
        return {'kind': 'ai_addon', 'name': self.name, 'ai_calls': self.ai_calls,
                'validity_days': self.validity_days, 'price_cents': self.price_cents}

    @property
    def configured(self):
        return all(value is not None and value > 0 for value in (self.price_cents, self.ai_calls, self.validity_days))


class AIAddonGrant(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_addon_grants')
    product = models.ForeignKey(AIAddonProduct, on_delete=models.PROTECT, related_name='grants')
    order = models.OneToOneField('payments.Order', on_delete=models.PROTECT, related_name='ai_addon_grant')
    snapshot = models.JSONField(default=dict)
    ai_calls = models.PositiveIntegerField()
    used_calls = models.PositiveIntegerField(default=0)
    starts_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()


class WeeklyAIUsage(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='weekly_ai_usage')
    week = models.DateField()
    ai_calls = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'week'], name='unique_user_ai_week')]


class AIUsageReservation(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_reservations')
    request_id = models.UUIDField()
    attempt_id = models.UUIDField()
    fingerprint = models.CharField(max_length=64, blank=True)
    week = models.DateField()
    status = models.CharField(max_length=12, choices=[('pending', '处理中'), ('succeeded', '已完成'), ('released', '已释放')], default='pending')
    addon = models.ForeignKey(AIAddonGrant, null=True, blank=True, on_delete=models.PROTECT, related_name='reservations')
    unlimited = models.BooleanField(default=False)
    response = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'request_id'], name='unique_user_ai_request')]
