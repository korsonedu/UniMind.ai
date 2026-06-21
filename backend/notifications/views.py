from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q, Count, Exists, OuterRef
from django.utils import timezone

from .models import Notification, Announcement, AnnouncementRead
from .serializers import (
    NotificationSerializer,
    AnnouncementSerializer,
    AnnouncementReadSerializer,
)
from users.models import User
from users.permissions import (
    IsAdmin,
    IsPlatformAdmin,
    IsInstitutionOwner,
    is_platform_admin,
    is_institution_admin,
)


# ── 权限类 ───────────────────────────────────────────────────────────

class CanCreateAnnouncement(permissions.BasePermission):
    """平台管理员或机构所有者可创建公告。"""
    message = '仅机构所有者或平台管理员可发布公告。'

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return is_platform_admin(request.user) or request.user.institution_role == 'owner'


class CanEditAnnouncement(permissions.BasePermission):
    """发布者本人或平台管理员可编辑/删除；机构公告仅发布者和超管可操作。"""
    message = '无权限编辑此公告。'

    def has_object_permission(self, request, view, obj):
        if is_platform_admin(request.user):
            return True
        return obj.publisher == request.user


# ── 已有的 Notification 视图（不变）─────────────────────────────────

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
        title = request.data.get('title', '')
        content = request.data.get('content', '')

        if not title or not content:
            return Response({'error': '标题和内容必填'}, status=400)

        if len(content) > 50:
            return Response({'error': '内容不能超过50字'}, status=400)

        if is_platform_admin(request.user):
            user_qs = User.objects.all()
        else:
            inst = request.user.institution
            if inst:
                user_qs = User.objects.filter(institution=inst, is_active=True)
            else:
                user_qs = User.objects.filter(institution__isnull=True)

        batch = []
        total = 0
        for u in user_qs.iterator(chunk_size=2000):
            batch.append(Notification(recipient=u, title=title, content=content, ntype='system'))
            total += 1
            if len(batch) >= 2000:
                Notification.objects.bulk_create(batch)
                batch = []
        if batch:
            Notification.objects.bulk_create(batch)

        return Response({'status': 'ok', 'count': total})


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
    """返回用户可看见的已发布公告 queryset（不含 annotation）。"""
    qs = Announcement.objects.filter(status='published')

    if is_platform_admin(user):
        return qs

    inst = user.institution
    role = user.institution_role

    inst_q = Q(is_platform=False, institution=inst)

    if role == 'owner':
        plat_q = Q(is_platform=True, audience__in=['institution_owners', 'all_teachers', 'everyone'])
    elif role == 'teacher':
        plat_q = Q(is_platform=True, audience__in=['all_teachers', 'everyone'])
    else:
        plat_q = Q(is_platform=True, audience='everyone')

    if inst:
        return qs.filter(inst_q | plat_q)
    return qs.filter(plat_q)


def _annotate_user_read(qs, user):
    """给 queryset 加上 is_read / read_count annotation。"""
    read_subq = AnnouncementRead.objects.filter(
        announcement=OuterRef('pk'),
        user=user,
    )
    return qs.annotate(
        is_read=Exists(read_subq),
        read_count=Count('reads'),
    )


class AnnouncementListCreateView(generics.ListCreateAPIView):
    serializer_class = AnnouncementSerializer
    permission_classes = [permissions.IsAuthenticated, CanCreateAnnouncement]

    def get_queryset(self):
        user = self.request.user
        qs = _visible_announcements_for(user)

        # 筛选参数
        audience = self.request.query_params.get('audience')
        if audience and is_platform_admin(user):
            valid = ['institution_owners', 'all_teachers', 'everyone']
            if audience in valid:
                qs = qs.filter(audience=audience)

        status_q = self.request.query_params.get('status')
        if status_q and is_platform_admin(user):
            valid_status = ['draft', 'published', 'archived']
            if status_q in valid_status:
                qs = qs.filter(status=status_q)

        qs = qs.select_related('publisher')
        qs = _annotate_user_read(qs, user)
        return qs


class AnnouncementDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AnnouncementSerializer
    permission_classes = [permissions.IsAuthenticated, CanEditAnnouncement]
    lookup_field = 'pk'

    def get_queryset(self):
        qs = Announcement.objects.select_related('publisher')
        return _annotate_user_read(qs, self.request.user)

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
