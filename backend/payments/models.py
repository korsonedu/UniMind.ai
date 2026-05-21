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
    plan = models.CharField(max_length=20, choices=[('solo', 'Solo'), ('plus', 'Plus'), ('pro', 'Pro')])
    billing_cycle = models.CharField(max_length=10, choices=BILLING_CHOICES)
    amount_cents = models.IntegerField(verbose_name='金额（分）')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    gateway = models.CharField(max_length=20, choices=[('stripe', 'Stripe'), ('wechat', 'WeChat Pay'), ('alipay', 'Alipay')])
    gateway_order_id = models.CharField(max_length=128, blank=True, unique=True, null=True, verbose_name='网关订单号')
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
