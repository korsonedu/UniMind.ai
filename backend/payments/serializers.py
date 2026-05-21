from rest_framework import serializers

from payments.models import Order, Invoice


class CreateOrderSerializer(serializers.Serializer):
    plan = serializers.ChoiceField(choices=[('solo', 'Solo'), ('plus', 'Plus'), ('pro', 'Pro')])
    billing_cycle = serializers.ChoiceField(choices=[('monthly', 'Monthly'), ('annual', 'Annual')])
    gateway = serializers.ChoiceField(choices=[('stripe', 'Stripe'), ('wechat', 'WeChat Pay'), ('alipay', 'Alipay')])


class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = [
            'id', 'plan', 'billing_cycle', 'amount_cents', 'status',
            'gateway', 'paid_at', 'created_at', 'expires_at',
        ]


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = ['id', 'order', 'invoice_number', 'pdf_file', 'created_at']
