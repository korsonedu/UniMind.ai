from django.urls import path
from .views import (
    NotificationListView,
    MarkAsReadView,
    AdminBroadcastView,
    UnreadCountView,
    NotificationClearView,
)

urlpatterns = [
    # 站内通知
    path('', NotificationListView.as_view(), name='notification-list'),
    path('unread-count/', UnreadCountView.as_view(), name='unread-count'),
    path('read/', MarkAsReadView.as_view(), name='mark-all-read'),
    path('read/<int:pk>/', MarkAsReadView.as_view(), name='mark-read'),
    path('broadcast/', AdminBroadcastView.as_view(), name='admin-broadcast'),
    path('clear/', NotificationClearView.as_view(), name='notification-clear'),
]
