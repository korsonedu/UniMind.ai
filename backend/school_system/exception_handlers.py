from typing import Any

from rest_framework.views import exception_handler as drf_exception_handler


def _extract_message(detail: Any) -> str:
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list) and detail:
        return _extract_message(detail[0])
    if isinstance(detail, dict):
        # 优先 detail / error 字段，其次取第一个 value
        for key in ("detail", "error", "message"):
            if key in detail:
                return _extract_message(detail[key])
        if detail:
            first_value = next(iter(detail.values()))
            return _extract_message(first_value)
    return "请求处理失败"


def unified_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    request = context.get("request")
    request_id = getattr(request, "request_id", None) if request else None
    if not request_id and request is not None:
        request_id = request.META.get("HTTP_X_REQUEST_ID")

    raw_detail = response.data
    message = _extract_message(raw_detail)
    code = getattr(exc, "default_code", None) or "api_error"

    from django.conf import settings
    response.data = {
        "error": message,
        "code": str(code),
        "request_id": request_id,
    }
    if not getattr(settings, "IS_PROD", False):
        response.data["details"] = raw_detail
    if request_id:
        response["X-Request-ID"] = request_id
    return response
