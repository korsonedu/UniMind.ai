from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q
from django.utils import timezone

from .models import Notification, Announcement, AnnouncementRead
from .serializers import (
    NotificationSerializer,
    AnnouncementSerializer,
    AnnouncementReadSerializer,
)
from users.models import User
from users.permissions import IsAdmin, IsPlatformAdmin, IsInstitutionOwner, is_platform_admin


# ── 现有 Notification 视图（保持不变）─────────────────────────────────

class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)


class MarkAsReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk=None):
        if pk:
            Notification.objects.filter(recipient=request.user, pk=pk).update(is_read=True)
        else:
            Notification.objects.filter(recipient=request.user).update(is_read=True)
        return Response({'status': 'ok'})


class AdminBroadcastView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        from django.db.models import Q
        title = request.data.get('title', '')
        content = request.data.get('content', '')

        if not title or not content:
            return Response({'error': '标题和内容必填'}, status=400)

        if len(content) > 50:
            return Response({'error': '内容不能超过50字'}, status=400)

        if is_platform_admin(request.user):
            users = User.objects.all()
        else:
            inst = request.user.institution
            if inst:
                users = User.objects.filter(institution=inst, is_active=True)
            else:
                users = User.objects.filter(institution__isnull=True)

        notifications = [
            Notification(recipient=u, title=title, content=content, ntype='system')
            for u in users
        ]
        Notification.objects.bulk_create(notifications)

        return Response({'status': 'ok', 'count': len(notifications)})


class UnreadCountView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return Response({'unread_count': count})


class NotificationClearView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request):
        Notification.objects.filter(recipient=request.user).delete()
        return Response({'status': 'ok'})


# ── 公告系统 ─────────────────────────────────────────────────────────

def _visible_announcements_for(user):
    """返回用户可看见的已发布公告 queryset。"""
    qs = Announcement.objects.filter(status='published')

    if is_platform_admin(user):
        return qs

    inst = user.institution
    role = user.institution_role

    # 机构公告：自己机构的
    inst_q = Q(is_platform=False, institution=inst)

    # 平台公告：按 audience 过滤
    if role == 'owner':
        plat_q = Q(is_platform=True, audience__in=['institution_owners', 'all_teachers', 'everyone'])
    elif role == 'teacher':
        plat_q = Q(is_platform=True, audience__in=['all_teachers', 'everyone'])
    else:
        # student 或无机构
        plat_q = Q(is_platform=True, audience='everyone')

    if inst:
        return qs.filter(inst_q | plat_q)
    return qs.filter(plat_q)


class AnnouncementListCreateView(generics.ListCreateAPIView):
    serializer_class = AnnouncementSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return _visible_announcements_for(self.request.user)

    def check_permissions(self, request):
        super().check_permissions(request)
        if request.method == 'POST':
            # 创建公告：超管或机构所有者
            from users.permissions import is_institution_admin
            if not is_platform_admin(request.user) and request.user.institution_role != 'owner':
                self.permission_denied(request, message='仅机构所有者或平台管理员可发布公告')


class AnnouncementDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AnnouncementSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'pk'

    def get_queryset(self):
        user = self.request.user
        if is_platform_admin(user):
            return Announcement.objects.all()
        return Announcement.objects.filter(publisher=user)

    def perform_update(self, serializer):
        instance = serializer.instance
        if instance.status == 'draft' and serializer.validated_data.get('status') == 'published':
            serializer.validated_data['published_at'] = timezone.now()
        serializer.save()


class AnnouncementMarkReadView(APIView):
    """标记公告已读"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            announcement = _visible_announcements_for(request.user).get(pk=pk)
        except Announcement.DoesNotExist:
            return Response({'error': '公告不存在'}, status=404)

        AnnouncementRead.objects.get_or_create(
            announcement=announcement,
            user=request.user,
        )
        return Response({'status': 'ok'})


class AnnouncementUnreadCountView(APIView):
    """用户未读公告数"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        visible_ids = _visible_announcements_for(request.user).values_list('id', flat=True)
        read_ids = AnnouncementRead.objects.filter(
            user=request.user,
            announcement_id__in=visible_ids,
        ).values_list('announcement_id', flat=True)
        unread = len(visible_ids) - len(read_ids)
        return Response({'unread_count': unread})
