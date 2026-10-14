from django.contrib import admin
from core.admin_base import PlatformModelAdmin
from .models import Order, PaymentTransaction, Invoice


class PaymentRecordAdmin(PlatformModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(PaymentRecordAdmin):
    list_display = ['id', 'user', 'product', 'plan', 'amount_cents', 'gateway', 'status', 'created_at']
    list_filter = ['status', 'gateway', 'plan', 'billing_cycle']
    search_fields = ['user__email', 'gateway_order_id']
    readonly_fields = ['created_at', 'paid_at', 'gateway_order_id']


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(PaymentRecordAdmin):
    list_display = ['id', 'order', 'gateway', 'gateway_txn_id', 'status', 'created_at']
    list_filter = ['gateway', 'status']
    search_fields = ['gateway_txn_id']
    readonly_fields = ['created_at']


@admin.register(Invoice)
class InvoiceAdmin(PaymentRecordAdmin):
    list_display = ['id', 'order', 'invoice_number', 'created_at']
    search_fields = ['invoice_number']
    readonly_fields = ['created_at']
