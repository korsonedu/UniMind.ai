from django.conf import settings
from django.db import models
from django.utils import timezone


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


class CourseStudentStatus(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='course_student_status')
    is_course_student = models.BooleanField(default=False)
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
