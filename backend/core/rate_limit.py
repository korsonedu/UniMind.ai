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

            try:
                # add() 是原子的：key 不存在时返回 True 并设置
                if cache.add(cache_key, 1, timeout=window_seconds):
                    count = 1
                else:
                    # incr() 是原子的：不存在时返回 None，需 fallback
                    count = cache.incr(cache_key) or 1
            except Exception:
                # cache 不可用时放行，避免误拦
                return view_func(request, *args, **kwargs)

            if count > max_requests:
                ttl = cache.ttl(cache_key) or window_seconds
                return JsonResponse(
                    {
                        "error": "请求过于频繁，请稍后再试。",
                        "code": "rate_limited",
                        "retry_after_seconds": max(0, ttl),
                    },
                    status=429,
                )

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def _get_client_ip(request) -> str:
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "127.0.0.1")
