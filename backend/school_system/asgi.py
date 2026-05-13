"""
ASGI config for school_system project.
"""

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "school_system.settings")

django_asgi_app = get_asgi_application()

from interviews.routing import websocket_urlpatterns as interviews_ws
from notifications.routing import websocket_urlpatterns as notifications_ws

websocket_urlpatterns = interviews_ws + notifications_ws

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})
