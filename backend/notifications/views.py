from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Notification
from .serializers import NotificationSerializer
from users.models import User
from users.permissions import IsAdmin

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

        users = User.objects.all()
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
