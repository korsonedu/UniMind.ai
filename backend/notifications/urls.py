from django.urls import path
from .views import (
    NotificationListView,
    MarkAsReadView,
    AdminBroadcastView,
    UnreadCountView,
    NotificationClearView,
    AnnouncementListCreateView,
    AnnouncementDetailView,
    AnnouncementMarkReadView,
    AnnouncementUnreadCountView,
)

urlpatterns = [
    # 站内通知
    path('', NotificationListView.as_view(), name='notification-list'),
    path('unread-count/', UnreadCountView.as_view(), name='unread-count'),
    path('read/', MarkAsReadView.as_view(), name='mark-all-read'),
    path('read/<int:pk>/', MarkAsReadView.as_view(), name='mark-read'),
    path('broadcast/', AdminBroadcastView.as_view(), name='admin-broadcast'),
    path('clear/', NotificationClearView.as_view(), name='notification-clear'),

    # 公告系统
    path('announcements/', AnnouncementListCreateView.as_view(), name='announcement-list'),
    path('announcements/<int:pk>/', AnnouncementDetailView.as_view(), name='announcement-detail'),
    path('announcements/<int:pk>/read/', AnnouncementMarkReadView.as_view(), name='announcement-mark-read'),
    path('announcements/unread-count/', AnnouncementUnreadCountView.as_view(), name='announcement-unread-count'),
]
