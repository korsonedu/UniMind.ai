from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification
from .serializers import (
    NotificationSerializer,
)
from users.models import User
from users.permissions import (
    IsAdmin,
    is_platform_admin,
)


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
