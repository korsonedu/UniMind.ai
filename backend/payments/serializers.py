from rest_framework import serializers

from payments.models import Order, Invoice, Coupon


class CreateOrderSerializer(serializers.Serializer):
    plan = serializers.ChoiceField(choices=[('starter', 'Starter'), ('growth', 'Growth'), ('enterprise', 'Enterprise')])
    billing_cycle = serializers.ChoiceField(choices=[('monthly', 'Monthly'), ('annual', 'Annual')])
    gateway = serializers.ChoiceField(choices=[('stub', 'Stub (开发)'), ('stripe', 'Stripe'), ('wechat', 'WeChat Pay'), ('alipay', 'Alipay'), ('airwallex', 'Airwallex')])
    coupon_code = serializers.CharField(max_length=50, required=False, allow_blank=True, default='')


class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = [
            'id', 'plan', 'billing_cycle', 'amount_cents', 'status',
            'gateway', 'coupon_code', 'discount_cents', 'paid_at', 'created_at', 'expires_at',
        ]


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = ['id', 'order', 'invoice_number', 'pdf_file', 'created_at']


class CouponSerializer(serializers.ModelSerializer):
    institution_name = serializers.CharField(source='institution.name', read_only=True)
    discount_value = serializers.IntegerField(min_value=1, help_text='percent: 1-100; fixed: 分（至少 1）')

    class Meta:
        model = Coupon
        fields = [
            'id', 'code', 'discount_type', 'discount_value', 'min_order_cents',
            'max_uses', 'current_uses', 'max_uses_per_user', 'expires_at',
            'is_active', 'institution', 'institution_name', 'plan_restriction', 'created_at',
        ]
        read_only_fields = ['id', 'current_uses', 'created_at']


class CouponValidateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=50)
    plan = serializers.ChoiceField(choices=[('starter', 'Starter'), ('growth', 'Growth'), ('enterprise', 'Enterprise')])
    billing_cycle = serializers.ChoiceField(choices=[('monthly', 'Monthly'), ('annual', 'Annual')])
