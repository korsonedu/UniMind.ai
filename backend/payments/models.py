from django.conf import settings
from django.db import models


class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('expired', 'Expired'),
        ('refunded', 'Refunded'),
        ('cancelled', 'Cancelled'),
    ]
    BILLING_CHOICES = [
        ('monthly', 'Monthly'),
        ('annual', 'Annual'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='orders')
    institution = models.ForeignKey('users.Institution', on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    plan = models.CharField(max_length=20, choices=[('starter', 'Starter'), ('growth', 'Growth'), ('enterprise', 'Enterprise')])
    billing_cycle = models.CharField(max_length=10, choices=BILLING_CHOICES)
    amount_cents = models.IntegerField(verbose_name='金额（分）')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    gateway = models.CharField(max_length=20, choices=[('stub', 'Stub (开发)'), ('stripe', 'Stripe'), ('wechat', 'WeChat Pay'), ('alipay', 'Alipay')])
    gateway_order_id = models.CharField(max_length=128, blank=True, unique=True, null=True, verbose_name='网关订单号')
    coupon_code = models.CharField(max_length=50, blank=True, default='', verbose_name='使用的优惠码')
    discount_cents = models.IntegerField(default=0, verbose_name='优惠金额(分)')
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True, verbose_name='订单过期时间')

    class Meta:
        ordering = ['-created_at']
        verbose_name = '订单'
        verbose_name_plural = '订单'

    def __str__(self):
        return f'Order #{self.id} — {self.get_plan_display()} ({self.get_status_display()})'


class PaymentTransaction(models.Model):
    """Immutable callback record from payment gateway."""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='transactions')
    gateway = models.CharField(max_length=20)
    gateway_txn_id = models.CharField(max_length=128, unique=True, verbose_name='网关交易号')
    raw_callback = models.JSONField(default=dict, verbose_name='回调原始数据')
    amount_cents = models.IntegerField(null=True, blank=True, verbose_name='实际收款金额（分）')
    status = models.CharField(max_length=20, choices=[('success', 'Success'), ('fail', 'Fail'), ('refund', 'Refund')])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = '交易记录'
        verbose_name_plural = '交易记录'

    def __str__(self):
        return f'TXN {self.gateway_txn_id} — {self.status}'


class Subscription(models.Model):
    """机构订阅——对接 Stripe Subscription。"""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('past_due', 'Past Due'),
        ('canceled', 'Canceled'),
        ('trialing', 'Trialing'),
        ('incomplete', 'Incomplete'),
    ]
    PLAN_CHOICES = [('starter', 'Starter'), ('growth', 'Growth'), ('enterprise', 'Enterprise')]
    BILLING_CHOICES = [('monthly', 'Monthly'), ('annual', 'Annual')]

    institution = models.ForeignKey('users.Institution', on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES)
    billing_cycle = models.CharField(max_length=10, choices=BILLING_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='incomplete', db_index=True)
    stripe_subscription_id = models.CharField(max_length=128, unique=True, null=True, blank=True)
    stripe_customer_id = models.CharField(max_length=128, blank=True)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = '订阅'
        verbose_name_plural = '订阅'

    def __str__(self):
        return f'{self.get_plan_display()} {self.get_billing_cycle_display()} ({self.get_status_display()})'


class Invoice(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='invoice')
    invoice_number = models.CharField(max_length=32, unique=True, verbose_name='发票号')
    pdf_file = models.FileField(upload_to='invoices/', blank=True, verbose_name='PDF 发票')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = '发票'
        verbose_name_plural = '发票'

    def __str__(self):
        return self.invoice_number


class Coupon(models.Model):
    DISCOUNT_CHOICES = [
        ('percent', '百分比折扣'),
        ('fixed', '固定金额减免'),
    ]
    code = models.CharField(max_length=50, unique=True, db_index=True, verbose_name='优惠码')
    discount_type = models.CharField(max_length=10, choices=DISCOUNT_CHOICES, verbose_name='折扣类型')
    discount_value = models.IntegerField(verbose_name='折扣值', help_text='percent: 1-100; fixed: 分')
    min_order_cents = models.IntegerField(default=0, verbose_name='最低订单金额(分)')
    max_uses = models.IntegerField(default=0, verbose_name='总使用次数上限', help_text='0=无限制')
    current_uses = models.IntegerField(default=0, verbose_name='已使用次数')
    max_uses_per_user = models.IntegerField(default=1, verbose_name='每人限用次数')
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name='过期时间')
    is_active = models.BooleanField(default=True, db_index=True, verbose_name='是否启用')
    institution = models.ForeignKey('users.Institution', on_delete=models.CASCADE, null=True, blank=True,
                                     related_name='coupons', verbose_name='所属机构', help_text='NULL=平台通用')
    plan_restriction = models.CharField(max_length=100, blank=True, verbose_name='适用方案', help_text='逗号分隔，空=全部方案')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_coupons')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = '优惠券'
        verbose_name_plural = '优惠券'

    def __str__(self):
        return f'{self.code} ({self.get_discount_type_display()})'


class UserCouponUse(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='coupon_uses')
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name='user_uses')
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, related_name='coupon_applied')
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'coupon', 'order')
        verbose_name = '优惠券使用记录'
        verbose_name_plural = '优惠券使用记录'


class ReferralCode(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='referral_code')
    code = models.CharField(max_length=20, unique=True, db_index=True, verbose_name='推荐码')
    clicks = models.IntegerField(default=0, verbose_name='点击次数')
    signups = models.IntegerField(default=0, verbose_name='注册数')
    purchases = models.IntegerField(default=0, verbose_name='购买数')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = '推荐码'
        verbose_name_plural = '推荐码'

    def __str__(self):
        return f'{self.user.username} — {self.code}'


class ReferralRecord(models.Model):
    referrer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='referrals_made')
    referee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='referred_by_records')
    reward_granted = models.BooleanField(default=False)
    reward_amount_cents = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('referrer', 'referee')
        ordering = ['-created_at']
        verbose_name = '推荐记录'
        verbose_name_plural = '推荐记录'

    def __str__(self):
        return f'{self.referrer.username} → {self.referee.username}'
