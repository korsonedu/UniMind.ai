from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/ai/chat/(?P<bot_id>\d+)/$', consumers.AgentChatConsumer.as_asgi()),
]
