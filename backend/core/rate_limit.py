import time
import logging
from functools import wraps
from typing import Optional

from django.core.cache import cache
from django.http import JsonResponse

logger = logging.getLogger(__name__)


def rate_limit(key_prefix: str, max_requests: int, window_seconds: int):
    """固定窗口速率限制装饰器，基于 Django cache 原子递增。"""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            client_ip = _get_client_ip(request)
            cache_key = f"rl:{key_prefix}:{client_ip}"

            count = _incr_cache(cache_key, window_seconds)
            if count is not None and count > max_requests:
                return _rate_limit_response(cache_key, window_seconds)

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def user_rate_limit(key_prefix: str, max_requests: int, window_seconds: int):
    """用户级速率限制装饰器（基于 request.user.id + IP fallback）。"""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user_id = getattr(request.user, "id", None) or "anon"
            client_ip = _get_client_ip(request)
            cache_key = f"rl:{key_prefix}:u{user_id}:{client_ip}"

            count = _incr_cache(cache_key, window_seconds)
            if count is not None and count > max_requests:
                return _rate_limit_response(cache_key, window_seconds)

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def _incr_cache(cache_key: str, window_seconds: int) -> int | None:
    """原子递增缓存计数器，cache 不可用时返回超限值（fail-closed）。"""
    try:
        if cache.add(cache_key, 1, timeout=window_seconds):
            return 1
        return cache.incr(cache_key) or 1
    except Exception:
        logger.warning("Rate limiting: Redis unavailable, blocking request (fail-closed)")
        return 999999  # 触发限流，阻止请求


def _rate_limit_response(cache_key: str, window_seconds: int):
    try:
        ttl = cache.ttl(cache_key) or window_seconds
    except AttributeError:
        ttl = window_seconds
    return JsonResponse(
        {
            "error": "上传过于频繁，请稍后再试。",
            "code": "rate_limited",
            "retry_after_seconds": max(0, ttl),
        },
        status=429,
    )


def _get_client_ip(request) -> str:
    # 优先信任 nginx 注入的 X-Real-IP（由 proxy_set_header 设置，客户端不可伪造）
    x_real_ip = request.META.get("HTTP_X_REAL_IP")
    if x_real_ip:
        return x_real_ip.strip()
    # 无 X-Real-IP 时 fallback 到 REMOTE_ADDR
    return request.META.get("REMOTE_ADDR", "127.0.0.1")
