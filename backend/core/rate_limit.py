import time
import logging
from functools import wraps
from typing import Optional

from django.core.cache import cache
from django.http import JsonResponse

logger = logging.getLogger(__name__)


def rate_limit(key_prefix: str, max_requests: int, window_seconds: int):
    """简单的滑动窗口速率限制装饰器，基于 Django cache。"""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            client_ip = _get_client_ip(request)
            cache_key = f"rl:{key_prefix}:{client_ip}"
            now = time.time()
            window_start = now - window_seconds

            entries = cache.get(cache_key)
            if not isinstance(entries, list):
                entries = []

            # 清理窗口外的旧记录
            entries = [t for t in entries if t > window_start]

            if len(entries) >= max_requests:
                retry_after = int(entries[0] + window_seconds - now) + 1
                return JsonResponse(
                    {
                        "error": "请求过于频繁，请稍后再试。",
                        "code": "rate_limited",
                        "retry_after_seconds": max(0, retry_after),
                    },
                    status=429,
                )

            entries.append(now)
            cache.set(cache_key, entries, timeout=window_seconds)
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def _get_client_ip(request) -> str:
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "127.0.0.1")
