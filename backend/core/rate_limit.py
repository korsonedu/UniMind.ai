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
    """原子递增缓存计数器，cache 不可用时返回 None。"""
    try:
        if cache.add(cache_key, 1, timeout=window_seconds):
            return 1
        return cache.incr(cache_key) or 1
    except Exception:
        logger.warning("Rate limiting disabled: Redis unavailable")
        return None


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
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "127.0.0.1")
