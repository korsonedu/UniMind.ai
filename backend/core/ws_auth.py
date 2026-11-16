"""
Channels WebSocket 认证中间件 — 从 auth_token cookie 解析独立登录会话，注入 scope["user"]。
替代 channels.auth.AuthMiddlewareStack（后者读 Django session，但登录流程未写入 session）。
"""
import asyncio
import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from channels.sessions import CookieMiddleware

logger = logging.getLogger(__name__)


@database_sync_to_async
def get_user_from_token(token_key: str, space='personal'):
    """根据 auth_token 查找有效登录会话对应的用户。失败返回 None。"""
    from users.login_sessions import LoginSession

    if not token_key:
        return None

    token = LoginSession.resolve(token_key, touch=False)
    if not token:
        return None
    from users.workspaces.identity import select_learner
    from rest_framework.exceptions import PermissionDenied
    try:
        return select_learner(token.user, space)
    except PermissionDenied:
        return None


class TokenAuthMiddleware(BaseMiddleware):
    """WebSocket 认证：从 auth_token cookie 读取登录会话，注入 scope["user"]。

    需外层包 channels.sessions.CookieMiddleware 以提供 scope["cookies"]。
    """

    async def __call__(self, scope, receive, send):
        from django.contrib.auth.models import AnonymousUser

        cookies = scope.get("cookies", {})
        token_key = cookies.get("auth_token", "")
        scope = dict(scope)
        space = parse_qs(scope.get('query_string', b'').decode()).get('space', ['personal'])[0]
        scope["user"] = await get_user_from_token(token_key, space) or AnonymousUser()
        if not scope['user'].is_authenticated:
            return await super().__call__(scope, receive, send)

        async def authenticated_receive():
            while True:
                try:
                    message = await asyncio.wait_for(receive(), timeout=60)
                except asyncio.TimeoutError:
                    message = None
                if message and message['type'] in {'websocket.connect', 'websocket.disconnect'}:
                    return message
                if not await get_user_from_token(token_key, space):
                    await send({'type': 'websocket.close', 'code': 4001})
                    return {'type': 'websocket.disconnect', 'code': 4001}
                if message is not None:
                    return message

        return await super().__call__(scope, authenticated_receive, send)


def TokenAuthMiddlewareStack(inner):
    """替代 channels.auth.AuthMiddlewareStack 的 WS 认证栈。"""
    return CookieMiddleware(TokenAuthMiddleware(inner))
