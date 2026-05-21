from django.urls import path

from payments.views import (
    CreateOrderView, OrderStatusView, OrderHistoryView,
    InvoiceListView,
    StripeWebhookView, WechatNotifyView, AlipayNotifyView, AlipayReturnView,
)

urlpatterns = [
    # User-facing
    path('orders/create/', CreateOrderView.as_view(), name='payment-create-order'),
    path('orders/<int:order_id>/', OrderStatusView.as_view(), name='payment-order-status'),
    path('orders/', OrderHistoryView.as_view(), name='payment-order-history'),
    path('invoices/', InvoiceListView.as_view(), name='payment-invoices'),

    # Webhooks (no auth)
    path('stripe/webhook/', StripeWebhookView.as_view(), name='stripe-webhook'),
    path('wechat/notify/', WechatNotifyView.as_view(), name='wechat-notify'),
    path('alipay/notify/', AlipayNotifyView.as_view(), name='alipay-notify'),
    path('alipay/return/', AlipayReturnView.as_view(), name='alipay-return'),
]
