from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings

class User(AbstractUser):
    ROLE_CHOICES = (
        ('student', '学生'),
        ('admin', '管理员'),
    )
    MEMBERSHIP_TIER_CHOICES = (
        ('free', '免费'), ('basic', '基础'), ('pro', '专业'),
    )
    INSTITUTION_ROLE_CHOICES = (
        ('admin', '机构管理员'), ('student', '学员'),
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='student')
    nickname = models.CharField(max_length=100, blank=True, verbose_name="昵称")
    elo_score = models.IntegerField(default=1000)
    has_completed_initial_assessment = models.BooleanField(default=False)
    elo_reset_count = models.IntegerField(default=0)
    avatar_style = models.CharField(max_length=50, default='avataaars')
    avatar_seed = models.CharField(max_length=100, blank=True)
    last_active = models.DateTimeField(auto_now_add=True)
    current_task = models.CharField(max_length=200, blank=True, null=True)
    current_timer_end = models.DateTimeField(blank=True, null=True)
    today_focused_minutes = models.IntegerField(default=0)
    today_completed_tasks = models.JSONField(default=list, blank=True)
    allow_broadcast = models.BooleanField(default=True)
    show_others_broadcast = models.BooleanField(default=True)
    bio = models.TextField(blank=True, null=True)
    is_member = models.BooleanField(default=False, verbose_name="是否会员")
    email_verified = models.BooleanField(default=False, verbose_name="邮箱已验证")
    membership_expires_at = models.DateTimeField(null=True, blank=True, verbose_name="会员到期时间")
    membership_tier = models.CharField(max_length=20, choices=MEMBERSHIP_TIER_CHOICES, default='free', verbose_name="会员等级")
    trial_ends_at = models.DateTimeField(null=True, blank=True, verbose_name="试用到期时间")
    verification_code = models.CharField(max_length=8, blank=True, verbose_name="验证码")
    verification_code_sent_at = models.DateTimeField(null=True, blank=True, verbose_name="验证码发送时间")
    institution_role = models.CharField(max_length=20, choices=INSTITUTION_ROLE_CHOICES, default='student', verbose_name="机构内角色")
    institution = models.ForeignKey('Institution', on_delete=models.SET_NULL, null=True, blank=True, related_name='students', verbose_name="所属机构")

    @property
    def is_platform_admin(self):
        """超级管理员：is_superuser 且未绑定机构"""
        return self.is_superuser and self.institution_id is None

    @property
    def avatar_url(self):
        seed = self.avatar_seed or self.username
        return f"https://api.dicebear.com/7.x/{self.avatar_style}/svg?seed={seed}"

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = 'admin'
        if self.role == 'admin':
            self.is_staff = True
            self.is_member = True
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-elo_score']


class ActivationCode(models.Model):
    code = models.CharField(max_length=50, unique=True, verbose_name="激活码")
    is_used = models.BooleanField(default=False, verbose_name="是否已使用")
    used_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="used_codes")
    used_at = models.DateTimeField(null=True, blank=True, verbose_name="使用时间")
    duration_days = models.IntegerField(default=30, verbose_name="有效天数")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} ({'已用' if self.is_used else '可用'})"


class DailyPlan(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.CharField(max_length=200)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']


class SystemConfig(models.Model):
    school_name = models.CharField(max_length=100, default='宇艺（UniMind.ai）')
    school_short_name = models.CharField(max_length=20, default='宇艺', verbose_name="网校缩写")
    school_description = models.TextField(default='UNIMIND.AI')
    school_logo = models.ImageField(upload_to="school_logos/", blank=True, null=True)
    invite_code = models.CharField(max_length=50, default="UNIMIND2026", verbose_name="邀请码")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.school_name


# ── 0015 PermissionGroup / UserTag / UserAccessProfile ──
class PermissionGroup(models.Model):
    key = models.CharField(max_length=50, unique=True, verbose_name="权限组键")
    name = models.CharField(max_length=80, verbose_name="权限组名称")
    description = models.CharField(max_length=200, blank=True, verbose_name="权限组说明")
    permissions = models.JSONField(blank=True, default=list, verbose_name="权限点列表")
    is_active = models.BooleanField(default=True, verbose_name="是否启用")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']


class UserTag(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name="标签名")
    color = models.CharField(max_length=20, default='slate', verbose_name="颜色标识")
    description = models.CharField(max_length=200, blank=True, verbose_name="标签说明")
    is_active = models.BooleanField(default=True, verbose_name="是否启用")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']


class UserAccessProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='access_profile')
    permission_groups = models.ManyToManyField(PermissionGroup, blank=True, related_name='users')
    tags = models.ManyToManyField(UserTag, blank=True, related_name='users')
    extra_permissions = models.JSONField(blank=True, default=list, verbose_name="附加权限点")
    blocked_permissions = models.JSONField(blank=True, default=list, verbose_name="屏蔽权限点")
    note = models.CharField(max_length=200, blank=True, verbose_name="管理备注")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']


# ── 0016 UserProfile ──
class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    student_type = models.CharField(max_length=20, choices=[('cross_major', '跨考'), ('same_major', '本专业')], default='same_major', verbose_name="考生类型")
    target_university = models.CharField(max_length=100, blank=True, verbose_name="目标院校")
    tags = models.ManyToManyField(UserTag, blank=True, related_name='user_profiles', verbose_name="用户标签")

    class Meta:
        ordering = ['-id']


# ── 0018 Institution ──
class Institution(models.Model):
    PLAN_CHOICES = [
        ('free', 'Free'), ('solo', 'Solo'), ('plus', 'Plus'), ('pro', 'Pro'),
    ]
    name = models.CharField(max_length=200, verbose_name="机构名称")
    slug = models.SlugField(max_length=100, unique=True, verbose_name="机构标识")
    contact_name = models.CharField(max_length=100, verbose_name="联系人")
    contact_email = models.EmailField(verbose_name="联系邮箱")
    contact_phone = models.CharField(max_length=20, blank=True, verbose_name="联系电话")
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default='free', verbose_name="当前版本")
    plan_expires_at = models.DateTimeField(null=True, blank=True, verbose_name="版本到期时间")
    max_students_override = models.IntegerField(null=True, blank=True, verbose_name="学员上限覆写")
    is_active = models.BooleanField(default=True, verbose_name="是否启用")
    invite_code = models.CharField(max_length=12, blank=True, unique=True, verbose_name="邀请码")
    custom_domain = models.CharField(max_length=200, blank=True, verbose_name="自定义域名")
    logo = models.ImageField(upload_to='institution_logos/', blank=True, verbose_name="机构 Logo")
    notes = models.TextField(blank=True, verbose_name="管理员备注")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_institutions', verbose_name="创建人")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    _PLAN_STUDENT_LIMITS = {'free': 30, 'solo': 50, 'plus': 200, 'pro': float('inf')}

    @property
    def max_students(self):
        if self.max_students_override is not None:
            return self.max_students_override
        return self._PLAN_STUDENT_LIMITS.get(self.plan, 30)

    @property
    def student_count(self):
        return self.students.filter(institution_role='student').count()

    @property
    def is_plan_active(self):
        if not self.is_active:
            return False
        if self.plan_expires_at is None:
            return True
        from django.utils import timezone
        return self.plan_expires_at > timezone.now()

    class Meta:
        verbose_name = '机构'
        verbose_name_plural = '机构'
        ordering = ['-created_at']

    def __str__(self):
        return self.name


# ── Plan features utility ──
DEFAULT_DURATION_DAYS = 30
DURATION_PERMANENT = 0
MAX_DURATION_DAYS = 365

PLAN_FEATURES: dict[str, list[str]] = {
    'free': [
        'quiz.manual', 'quiz.exam', 'wrong.review', 'basic.stats',
        'ai.generate', 'course.video',
    ],
    'solo': [
        'quiz.manual', 'quiz.exam', 'wrong.review', 'basic.stats',
        'ai.generate', 'memorix.review', 'full.report', 'knowledge.graph',
        'ai.assistant', 'course.video', 'video.outline',
    ],
    'plus': [
        'quiz.manual', 'quiz.exam', 'wrong.review', 'basic.stats',
        'ai.generate', 'memorix.review', 'full.report', 'knowledge.graph',
        'ai.assistant', 'course.video', 'video.outline', 'faq.system',
        'pdf.mock', 'study.room', 'multi.teacher', 'class.compare', 'data.export',
    ],
    'pro': [
        'quiz.manual', 'quiz.exam', 'wrong.review', 'basic.stats',
        'ai.generate', 'memorix.review', 'full.report', 'knowledge.graph',
        'ai.assistant', 'course.video', 'video.outline', 'faq.system',
        'pdf.mock', 'study.room', 'multi.teacher', 'class.compare', 'data.export',
        'brand.custom', 'api.access', 'student.payment',
        'private.deploy', 'i18n.custom', 'sso.saml', 'audit.log',
        'dedicated.support', 'sla.99.9',
    ],
}


def get_plan_features(plan: str) -> list[str]:
    return PLAN_FEATURES.get(plan, PLAN_FEATURES.get('free', []))


def compute_expiry(duration_days: int):
    if duration_days <= 0:
        return None
    from django.utils import timezone
    return timezone.now() + timezone.timedelta(days=duration_days)


# ── 0022-0023 PlanInviteCode ──
class PlanInviteCode(models.Model):
    PLAN_CHOICES = [
        ('free', 'Free'), ('solo', 'Solo'), ('plus', 'Plus'), ('pro', 'Pro'),
    ]
    code = models.CharField(max_length=16, unique=True, verbose_name="邀请码")
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, verbose_name="对应方案")
    max_uses = models.IntegerField(default=1, verbose_name="可使用次数")
    used_count = models.IntegerField(default=0, verbose_name="已使用次数")
    is_active = models.BooleanField(default=True, verbose_name="是否有效")
    duration_days = models.IntegerField(default=30, verbose_name="有效天数（0=永久）")
    note = models.CharField(max_length=200, blank=True, verbose_name="备注")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_invite_codes')
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = '方案邀请码'
        verbose_name_plural = '方案邀请码'
        ordering = ['-created_at']

    @property
    def is_exhausted(self):
        return self.used_count >= self.max_uses

    @classmethod
    def generate(cls, plan, created_by, count=1, max_uses=1, duration_days=30, note=''):
        import secrets, string
        codes = []
        for _ in range(count):
            raw = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(12))
            code = f'{raw[:4]}-{raw[4:8]}-{raw[8:12]}'
            obj = cls.objects.create(
                code=code, plan=plan, max_uses=max_uses,
                duration_days=duration_days, note=note,
                created_by=created_by,
            )
            codes.append({'id': obj.id, 'code': obj.code})
        return codes

    def __str__(self):
        return self.code


# Commercial models defined in models_commercial.py
from .models_commercial import (
    InstitutionUsageLog,
    InstitutionAuditLog,
    InstitutionPaymentConfig,
    InstitutionProductPrice,
)
