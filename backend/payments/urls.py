from django.urls import path

from payments.views import (
    CreateCheckoutSessionView, OrderStatusView, OrderHistoryView,
    WebhookView,
    CouponValidateView, CouponListCreateView, CouponDetailView,
    MyReferralView,
)

urlpatterns = [
    path('create-session/', CreateCheckoutSessionView.as_view(), name='payment-create-session'),
    path('orders/<int:order_id>/', OrderStatusView.as_view(), name='payment-order-status'),
    path('orders/', OrderHistoryView.as_view(), name='payment-order-history'),
    path('coupons/validate/', CouponValidateView.as_view(), name='coupon-validate'),
    path('coupons/', CouponListCreateView.as_view(), name='coupon-list'),
    path('coupons/<int:pk>/', CouponDetailView.as_view(), name='coupon-detail'),
    path('referral/', MyReferralView.as_view(), name='my-referral'),
    path('webhook/', WebhookView.as_view(), name='payment-webhook'),
]

