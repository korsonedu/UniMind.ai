from django.contrib import admin
from .models import Order, PaymentTransaction, Invoice


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'plan', 'billing_cycle', 'amount_cents', 'gateway', 'status', 'created_at']
    list_filter = ['status', 'gateway', 'plan', 'billing_cycle']
    search_fields = ['user__email', 'gateway_order_id']
    readonly_fields = ['created_at', 'paid_at', 'gateway_order_id']


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ['id', 'order', 'gateway', 'gateway_txn_id', 'status', 'created_at']
    list_filter = ['gateway', 'status']
    search_fields = ['gateway_txn_id']
    readonly_fields = ['created_at']


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['id', 'order', 'invoice_number', 'created_at']
    search_fields = ['invoice_number']
    readonly_fields = ['created_at']
