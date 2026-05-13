import requests
from rest_framework import generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Q
from django.core.files.storage import default_storage
from django.conf import settings
from .models import ChatMessage
from users.models import DailyPlan
from .serializers import ChatMessageSerializer
from users.views import IsMember


def _task_state_message_q() -> Q:
    return (
        Q(content__contains='💪')
        | Q(content__contains='✅')
        | Q(content__contains='❌')
        | Q(content__contains='开始了“')
        | Q(content__contains='📅')
        | Q(content__contains='制定')
    )


class ChatMessageListView(generics.ListCreateAPIView):
    queryset = ChatMessage.objects.all().order_by('timestamp')
    serializer_class = ChatMessageSerializer
    permission_classes = [IsMember]

    def perform_create(self, serializer):
        related_plan_id = self.request.data.get('related_plan_id')
        related_plan = None
        if related_plan_id:
            try:
                related_plan = DailyPlan.objects.get(id=related_plan_id, user=self.request.user)
            except DailyPlan.DoesNotExist:
                pass
        
        serializer.save(user=self.request.user, related_plan=related_plan)

class UndoBroadcastView(APIView):
    permission_classes = [IsMember]

    def post(self, request, pk):
        try:
            message = ChatMessage.objects.get(pk=pk, user=request.user)

            latest_user_message = ChatMessage.objects.filter(user=request.user).order_by('-timestamp', '-id').first()
            latest_task_state_message = (
                ChatMessage.objects.filter(user=request.user)
                .filter(_task_state_message_q())
                .order_by('-timestamp', '-id')
                .first()
            )
            can_undo = (
                (latest_user_message and message.id == latest_user_message.id)
                or (latest_task_state_message and message.id == latest_task_state_message.id)
            )
            if not can_undo:
                return Response({'error': '只能撤回本人最后一条消息或最后一条任务状态消息'}, status=400)

            if message.related_plan:
                # Revert plan status
                plan = message.related_plan
                plan.is_completed = False
                plan.completed_at = None
                plan.save()
            
            # Delete message
            message.delete()
            return Response({'status': 'success'})
        except ChatMessage.DoesNotExist:
            return Response({'error': 'Message not found'}, status=404)

class ImageUploadView(APIView):
    permission_classes = [IsMember]
    def post(self, request):
        file = request.FILES.get('image')
        if not file:
            return Response({'error': 'No file uploaded'}, status=400)

        file_name = default_storage.save(f'chat_images/{file.name}', file)
        file_url = request.build_absolute_uri(settings.MEDIA_URL + file_name)

        return Response({'url': file_url})


class GiphySearchView(APIView):
    """Proxy GIPHY search/tending through our backend to avoid exposing API key."""
    permission_classes = [IsMember]

    def get(self, request):
        api_key = getattr(settings, 'GIPHY_API_KEY', '')
        if not api_key:
            return Response({'error': 'GIPHY not configured'}, status=503)

        q = request.GET.get('q', '')
        offset = request.GET.get('offset', '0')

        if q:
            url = 'https://api.giphy.com/v1/gifs/search'
            params = {'api_key': api_key, 'q': q, 'offset': offset, 'limit': 24, 'rating': 'pg'}
        else:
            url = 'https://api.giphy.com/v1/gifs/trending'
            params = {'api_key': api_key, 'offset': offset, 'limit': 24, 'rating': 'pg'}

        try:
            r = requests.get(url, params=params, timeout=5)
            r.raise_for_status()
            return Response(r.json())
        except requests.RequestException:
            return Response({'error': 'GIPHY temporarily unavailable'}, status=502)
