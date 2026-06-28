"""
Channels WebSocket 认证中间件 — 从 auth_token cookie 解析 DRF Token，注入 scope["user"]。
替代 channels.auth.AuthMiddlewareStack（后者读 Django session，但登录流程未写入 session）。
"""
import logging

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from channels.sessions import CookieMiddleware

logger = logging.getLogger(__name__)


@database_sync_to_async
def get_user_from_token(token_key: str):
    """根据 auth_token 查找 DRF Token 对应的用户。失败返回 None。"""
    from rest_framework.authtoken.models import Token

    if not token_key:
        return None

    try:
        token = Token.objects.select_related("user").get(key=token_key)
    except Token.DoesNotExist:
        return None

    if token.user.is_active:
        return token.user
    return None


class TokenAuthMiddleware(BaseMiddleware):
    """WebSocket 认证：从 auth_token cookie 读取 DRF Token，注入 scope["user"]。

    需外层包 channels.sessions.CookieMiddleware 以提供 scope["cookies"]。
    """

    async def __call__(self, scope, receive, send):
        from django.contrib.auth.models import AnonymousUser

        cookies = scope.get("cookies", {})
        token_key = cookies.get("auth_token", "")
        scope = dict(scope)
        scope["user"] = await get_user_from_token(token_key) or AnonymousUser()
        return await super().__call__(scope, receive, send)


def TokenAuthMiddlewareStack(inner):
    """替代 channels.auth.AuthMiddlewareStack 的 WS 认证栈。"""
    return CookieMiddleware(TokenAuthMiddleware(inner))
