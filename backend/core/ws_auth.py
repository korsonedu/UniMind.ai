"""
Channels WebSocket 认证中间件 — 从 auth_token cookie 或一次性短时 ticket 解析独立登录会话，注入 scope["user"]。
替代 channels.auth.AuthMiddlewareStack（后者读 Django session，但登录流程未写入 session）。
"""
import asyncio
import logging
import re
import secrets
import time
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from channels.sessions import CookieMiddleware
from django.core.cache import cache

logger = logging.getLogger(__name__)

WS_TICKET_TTL = 30
WS_TICKET_CACHE_PREFIX = "ws_ticket:"
_WS_TICKET_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")


def issue_ws_ticket(user, auth) -> str:
    """签发一次性短时 WebSocket 凭证并存入缓存。"""
    from users.login_sessions import LoginSession
    from rest_framework.exceptions import AuthenticationFailed

    session = LoginSession.resolve(auth.key, touch=False) if isinstance(auth, LoginSession) else None
    if session is None or session.user_id != user.id:
        raise AuthenticationFailed('登录已失效，请重新登录。')
    ticket = secrets.token_urlsafe(32)
    session_key = session.key
    payload = {
        "user_id": user.id,
        "session_key": session_key,
        "expires_at": time.time() + WS_TICKET_TTL,
    }
    if not cache.add(f"{WS_TICKET_CACHE_PREFIX}{ticket}", payload, timeout=WS_TICKET_TTL):
        raise RuntimeError("Failed to store WebSocket ticket")
    return ticket


def _extract_ticket_from_scope(scope) -> str:
    raw_query = scope.get("query_string") or b""
    query_str = raw_query.decode("latin1") if isinstance(raw_query, (bytes, bytearray)) else str(raw_query)
    if not query_str:
        return ""
    values = parse_qs(query_str, keep_blank_values=True).get("ticket") or []
    if len(values) != 1:
        return ""
    return values[0].strip()


@database_sync_to_async
def consume_ws_ticket(ticket: str):
    """原子消费单次 WS ticket 并校验用户与有效 LoginSession。失败返回 (None, '')。"""
    from users.login_sessions import LoginSession

    if not ticket or not _WS_TICKET_RE.fullmatch(ticket):
        return None, ""

    cache_key = f"{WS_TICKET_CACHE_PREFIX}{ticket}"
    try:
        payload = cache.get(cache_key)
        # Both LocMemCache (under its lock) and RedisCache (DEL) return whether
        # this caller removed the key. Only that caller may use the payload.
        if not payload or not cache.delete(cache_key):
            return None, ""
    except Exception:
        logger.warning("WS ticket cache lookup failed", exc_info=True)
        return None, ""

    if not isinstance(payload, dict):
        return None, ""
    expires_at = payload.get("expires_at")
    if expires_at is not None and time.time() >= expires_at:
        return None, ""

    user_id = payload.get("user_id")
    session_key = payload.get("session_key")
    if not user_id or not session_key:
        return None, ""

    token = LoginSession.resolve(session_key, touch=False)
    if not token or token.user_id != user_id:
        return None, ""
    return token.user, session_key


@database_sync_to_async
def get_user_from_token(token_key: str):
    """根据 auth_token 查找有效登录会话对应的用户。失败返回 None。"""
    from users.login_sessions import LoginSession

    if not token_key:
        return None

    token = LoginSession.resolve(token_key, touch=False)
    return token.user if token else None


class TokenAuthMiddleware(BaseMiddleware):
    """WebSocket 认证：优先从 auth_token cookie 读取登录会话，仅无 cookie 时校验单次 ticket。

    需外层包 channels.sessions.CookieMiddleware 以提供 scope["cookies"]。
    """

    async def __call__(self, scope, receive, send):
        from django.contrib.auth.models import AnonymousUser

        cookies = scope.get("cookies", {})
        token_key = cookies.get("auth_token", "")
        scope = dict(scope)
        if token_key:
            user = await get_user_from_token(token_key)
        else:
            ticket = _extract_ticket_from_scope(scope)
            user, token_key = await consume_ws_ticket(ticket) if ticket else (None, "")
        scope["user"] = user or AnonymousUser()
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
                if not await get_user_from_token(token_key):
                    await send({'type': 'websocket.close', 'code': 4001})
                    return {'type': 'websocket.disconnect', 'code': 4001}
                if message is not None:
                    return message

        return await super().__call__(scope, authenticated_receive, send)


def TokenAuthMiddlewareStack(inner):
    """替代 channels.auth.AuthMiddlewareStack 的 WS 认证栈。"""
    return CookieMiddleware(TokenAuthMiddleware(inner))
