from django.conf import settings
from django.urls import path

from payments.views import (
    CreateCheckoutSessionView, OrderStatusView, OrderHistoryView,
    InvoiceListView, WebhookView, SimulatePaymentView,
    CreateSubscriptionView, SubscriptionStatusView,
    CouponValidateView, CouponListCreateView, CouponDetailView,
    MyReferralView,
)

urlpatterns = [
    path('create-session/', CreateCheckoutSessionView.as_view(), name='payment-create-session'),
    path('orders/<int:order_id>/', OrderStatusView.as_view(), name='payment-order-status'),
    path('orders/', OrderHistoryView.as_view(), name='payment-order-history'),
    path('invoices/', InvoiceListView.as_view(), name='payment-invoices'),
    path('subscriptions/', CreateSubscriptionView.as_view(), name='payment-create-subscription'),
    path('subscriptions/me/', SubscriptionStatusView.as_view(), name='payment-subscription-me'),
    path('coupons/validate/', CouponValidateView.as_view(), name='coupon-validate'),
    path('coupons/', CouponListCreateView.as_view(), name='coupon-list'),
    path('coupons/<int:pk>/', CouponDetailView.as_view(), name='coupon-detail'),
    path('referral/', MyReferralView.as_view(), name='my-referral'),
    path('webhook/', WebhookView.as_view(), name='payment-webhook'),
]

# Only include simulate endpoint in development
if getattr(settings, 'DEBUG', False):
    urlpatterns += [path('orders/<int:order_id>/simulate/', SimulatePaymentView.as_view(), name='payment-simulate')]
