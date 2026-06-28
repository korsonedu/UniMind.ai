from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/study-room/$', consumers.StudyRoomConsumer.as_asgi()),
]
