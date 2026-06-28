"""
ASGI config for school_system project.
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "school_system.settings")

django_asgi_app = get_asgi_application()

from interviews.routing import websocket_urlpatterns as interviews_ws
from notifications.routing import websocket_urlpatterns as notifications_ws
from ai_assistant.routing import websocket_urlpatterns as ai_assistant_ws
from study_room.routing import websocket_urlpatterns as study_room_ws
from core.ws_auth import TokenAuthMiddlewareStack

websocket_urlpatterns = interviews_ws + notifications_ws + ai_assistant_ws + study_room_ws

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": TokenAuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})
