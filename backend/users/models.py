from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings

class User(AbstractUser):
    ROLE_CHOICES = (
        ('student', '学生'),
        ('admin', '管理员'),
    )
    MEMBERSHIP_TIER_CHOICES = (
        ('free', 'Free'), ('starter', 'Starter'), ('growth', 'Growth'), ('enterprise', 'Enterprise'),
    )
    INSTITUTION_ROLE_CHOICES = (
        ('owner', '机构所有者'),
        ('teacher', '教师'),
        ('student', '学员'),
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='student')
    nickname = models.CharField(max_length=100, blank=True, verbose_name="昵称")
    elo_score = models.IntegerField(default=1000)
    has_completed_initial_assessment = models.BooleanField(default=False)
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
    trial_ends_at = models.DateTimeField(null=True, blank=True, verbose_name="试用到期时间（已废弃，保留兼容）")
    MEMBERSHIP_SOURCE_CHOICES = (
        ('trial', '试用'), ('code', '激活码'), ('payment', '付费'), ('admin', '管理员'),
    )
    membership_source = models.CharField(max_length=20, choices=MEMBERSHIP_SOURCE_CHOICES, null=True, blank=True, verbose_name="会员来源")
    verification_code = models.CharField(max_length=128, blank=True, verbose_name="验证码哈希")
    verification_code_sent_at = models.DateTimeField(null=True, blank=True, verbose_name="验证码发送时间")
    institution_role = models.CharField(max_length=20, choices=INSTITUTION_ROLE_CHOICES, default='student', verbose_name="机构内角色")
    institution = models.ForeignKey('Institution', on_delete=models.SET_NULL, null=True, blank=True, related_name='students', verbose_name="所属机构")
    failed_login_count = models.IntegerField(default=0, verbose_name="连续登录失败次数")
    locked_until = models.DateTimeField(null=True, blank=True, verbose_name="锁定截止时间")
    dashboard_config = models.JSONField(default=dict, blank=True, verbose_name="小宇 Dashboard 配置")
    agreed_to_terms = models.BooleanField(default=False, verbose_name="已同意用户协议")
    agreed_to_terms_at = models.DateTimeField(null=True, blank=True, verbose_name="同意协议时间")

    @property
    def avatar_url(self):
        seed = self.avatar_seed or self.username
        return f"/api/users/avatar/{self.avatar_style}/{seed}/"

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
    CODE_TYPE_CHOICES = (('trial', '试用'), ('formal', '正式'))
    code = models.CharField(max_length=50, unique=True, verbose_name="激活码")
    code_type = models.CharField(max_length=10, choices=CODE_TYPE_CHOICES, default='formal', verbose_name="码类型")
    membership_tier = models.CharField(max_length=20, choices=User.MEMBERSHIP_TIER_CHOICES, default='growth', verbose_name="会员等级")
    duration_days = models.IntegerField(default=30, verbose_name="有效天数")
    is_used = models.BooleanField(default=False, verbose_name="是否已使用")
    used_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="used_codes")
    used_at = models.DateTimeField(null=True, blank=True, verbose_name="使用时间")
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
        ('free', 'Free'), ('starter', 'Starter'), ('growth', 'Growth'), ('enterprise', 'Enterprise'),
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
    custom_domain = models.CharField(max_length=200, blank=True, verbose_name="自定义域名")
    invite_slug = models.CharField(max_length=40, blank=True, unique=True, verbose_name="邀请链接 slug")
    logo = models.ImageField(upload_to='institution_logos/', blank=True, verbose_name="机构 Logo")
    business_type = models.CharField(max_length=200, blank=True, verbose_name="主营业务", help_text="您主要讲授的课程，如金融431、CPA、法考、教资等。此项与模拟面试、AI助教等多个功能关联，请务必正确填写。")
    student_scale = models.CharField(
        max_length=20,
        choices=[
            ('1-50', '1-50 人'),
            ('50-200', '50-200 人'),
            ('200-500', '200-500 人'),
            ('500+', '500+ 人'),
        ],
        blank=True,
        default='',
        verbose_name="学员规模",
    )
    description = models.TextField(blank=True, verbose_name="机构简介")
    notes = models.TextField(blank=True, verbose_name="管理员备注")
    storage_used_bytes = models.BigIntegerField(default=0, verbose_name="已用存储(字节)")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_institutions', verbose_name="创建人")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    _PLAN_STUDENT_LIMITS = {'free': 30, 'starter': 50, 'growth': 200, 'enterprise': 999999}

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

    def save(self, *args, **kwargs):
        if not self.invite_slug:
            import secrets
            self.invite_slug = secrets.token_urlsafe(12)
        super().save(*args, **kwargs)

    def regenerate_invite_slug(self):
        import secrets
        self.invite_slug = secrets.token_urlsafe(12)
        self.save(update_fields=['invite_slug'])

    def __str__(self):
        return self.name


class Class(models.Model):
    """机构下的班级，支持将学生分组管理。"""
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name='classes', verbose_name="所属机构")
    name = models.CharField(max_length=200, verbose_name="班级名称")
    students = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='classes', blank=True, verbose_name="学员")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = '班级'
        verbose_name_plural = '班级'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['institution', 'name'], name='unique_class_name_per_institution'),
        ]

    def __str__(self):
        return f"{self.institution.name} - {self.name}"


# ── Plan features utility ──
DEFAULT_DURATION_DAYS = 30
DURATION_PERMANENT = 0
MAX_DURATION_DAYS = 365

PLAN_FEATURES: dict[str, list[str]] = {
    'free': [
        'quiz.manual', 'quiz.exam', 'wrong.review', 'basic.stats',
        'ai.generate', 'course.video',
    ],
    'starter': [
        'quiz.manual', 'quiz.exam', 'wrong.review', 'basic.stats',
        'ai.generate', 'memorix.review', 'full.report',
        'ai.assistant', 'course.video',
        'ai.bot.custom',
    ],
    'growth': [
        'quiz.manual', 'quiz.exam', 'wrong.review', 'basic.stats',
        'ai.generate', 'memorix.review', 'full.report', 'knowledge.graph',
        'ai.assistant', 'course.video', 'video.outline', 'faq.system',
        'pdf.mock', 'study.room', 'multi.teacher', 'class.compare', 'data.export',
        'interview.mock', 'ai.bot.custom',
    ],
    'enterprise': [
        'quiz.manual', 'quiz.exam', 'wrong.review', 'basic.stats',
        'ai.generate', 'memorix.review', 'full.report', 'knowledge.graph',
        'ai.assistant', 'course.video', 'video.outline', 'faq.system',
        'pdf.mock', 'study.room', 'multi.teacher', 'class.compare', 'data.export',
        'interview.mock', 'ai.bot.custom',
        'brand.custom', 'api.access', 'student.payment',
        'private.deploy', 'i18n.custom', 'sso.saml', 'audit.log',
        'dedicated.support', 'sla.99.9',
    ],
}


def get_plan_features(plan: str) -> list[str]:
    return PLAN_FEATURES.get(plan, PLAN_FEATURES.get('free', []))


def has_plan_feature(institution, feature: str) -> bool:
    """检查机构是否具备指定功能。"""
    if institution is None:
        return False
    return feature in get_plan_features(institution.plan)


def compute_expiry(duration_days: int):
    if duration_days <= 0:
        return None
    from django.utils import timezone
    return timezone.now() + timezone.timedelta(days=duration_days)


# ── 0022-0023 PlanInviteCode ──
class PlanInviteCode(models.Model):
    PLAN_CHOICES = [
        ('free', 'Free'), ('starter', 'Starter'), ('growth', 'Growth'), ('enterprise', 'Enterprise'),
    ]
    CODE_TYPE_CHOICES = (('trial', '试用'), ('formal', '正式'))
    code = models.CharField(max_length=16, unique=True, verbose_name="邀请码")
    code_type = models.CharField(max_length=10, choices=CODE_TYPE_CHOICES, default='formal', verbose_name="码类型")
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
    def validate_and_use(cls, code: str):
        """验证并消耗方案邀请码。返回 (valid: bool, result: str|tuple)"""
        from django.utils import timezone
        obj = cls.objects.select_for_update().filter(code=code).first()
        if not obj:
            return False, '邀请码不存在'
        if not obj.is_active:
            return False, '邀请码已被停用'
        if obj.is_exhausted:
            return False, '邀请码已达到使用次数上限'
        plan = obj.plan
        duration_days = obj.duration_days
        obj.used_count += 1
        obj.used_at = timezone.now()
        obj.save(update_fields=['used_count', 'used_at'])
        return True, (plan, duration_days)

    @classmethod
    def generate(cls, plan, created_by, count=1, max_uses=1, duration_days=30, note='', code_type='formal'):
        import secrets, string
        if code_type == 'trial':
            plan = 'growth'
            duration_days = 7
        codes = []
        for _ in range(count):
            raw = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(12))
            code = f'{raw[:4]}-{raw[4:8]}-{raw[8:12]}'
            obj = cls.objects.create(
                code=code, code_type=code_type, plan=plan, max_uses=max_uses,
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
)
