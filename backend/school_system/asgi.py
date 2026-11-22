"""
ASGI config for school_system project.
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import OriginValidator
from django.conf import settings
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "school_system.settings")

django_asgi_app = get_asgi_application()

from notifications.routing import websocket_urlpatterns as notifications_ws
from core.ws_auth import TokenAuthMiddlewareStack

websocket_urlpatterns = notifications_ws


class ConfiguredOriginValidator(OriginValidator):
    """Validate WebSocket Origin against ALLOWED_HOSTS and WS_ALLOWED_ORIGINS."""

    def __init__(self, application):
        allowed_hosts = list(settings.ALLOWED_HOSTS)
        if settings.DEBUG and not settings.IS_PROD and not allowed_hosts:
            allowed_hosts = ["localhost", "127.0.0.1", "[::1]"]
        # The development HTTP wildcard must not disable WebSocket Origin checks.
        allowed_hosts = [host for host in allowed_hosts if host != "*"]
        ws_origins = list(settings.WS_ALLOWED_ORIGINS)
        super().__init__(application, list(dict.fromkeys([*allowed_hosts, *ws_origins])))


application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": ConfiguredOriginValidator(TokenAuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    )),
})
