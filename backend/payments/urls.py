from django.conf import settings
from django.urls import path

from payments.views import (
    CreateCheckoutSessionView, OrderStatusView, OrderHistoryView,
    InvoiceListView, WebhookView, SimulatePaymentView,
)

urlpatterns = [
    path('create-session/', CreateCheckoutSessionView.as_view(), name='payment-create-session'),
    path('orders/<int:order_id>/', OrderStatusView.as_view(), name='payment-order-status'),
    path('orders/', OrderHistoryView.as_view(), name='payment-order-history'),
    path('invoices/', InvoiceListView.as_view(), name='payment-invoices'),
    path('webhook/', WebhookView.as_view(), name='payment-webhook'),
]

# Only include simulate endpoint in development
if getattr(settings, 'DEBUG', False):
    urlpatterns += [path('orders/<int:order_id>/simulate/', SimulatePaymentView.as_view(), name='payment-simulate')]
