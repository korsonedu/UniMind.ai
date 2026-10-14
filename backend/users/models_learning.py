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
