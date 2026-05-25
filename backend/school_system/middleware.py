import uuid
import logging
import time

from django.http import JsonResponse


logger = logging.getLogger(__name__)


class RequestIDMiddleware:
    """
    为每个请求生成/透传 request id，并回写到响应头 X-Request-ID。
    """

    header_name = "HTTP_X_REQUEST_ID"
    response_header = "X-Request-ID"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming_request_id = request.META.get(self.header_name)
        request_id = str(incoming_request_id).strip() if incoming_request_id else ""
        if not request_id:
            request_id = uuid.uuid4().hex

        request.request_id = request_id
        response = self.get_response(request)
        response[self.response_header] = request_id
        return response


class APIExceptionMiddleware:
    """
    统一兜底 API 未捕获异常，确保返回 request_id 便于排查。
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except Exception as exc:  # noqa: BLE001
            is_api_path = str(getattr(request, "path", "")).startswith("/api/")
            if not is_api_path:
                raise

            request_id = getattr(request, "request_id", None)
            logger.exception("Unhandled API exception path=%s request_id=%s", request.path, request_id)

            from django.conf import settings
            resp_data = {
                "error": "服务器内部错误",
                "code": "internal_server_error",
                "request_id": request_id,
            }
            if not getattr(settings, "IS_PROD", False):
                resp_data["details"] = {"exception": exc.__class__.__name__}

            resp = JsonResponse(resp_data, status=500)
            if request_id:
                resp["X-Request-ID"] = request_id
            return resp


class SecurityHeadersMiddleware:
    """添加安全响应头（等保二级）。"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self' https: wss:; "
            "frame-ancestors 'none'"
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response


class APIAccessLogMiddleware:
    """
    记录 API 访问日志（状态码、耗时、request_id）。
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.perf_counter()
        response = self.get_response(request)

        is_api_path = str(getattr(request, "path", "")).startswith("/api/")
        if is_api_path:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            request_id = getattr(request, "request_id", "-")
            user = getattr(request, "user", None)
            username = "-"
            try:
                if user and getattr(user, "is_authenticated", False):
                    username = getattr(user, "username", "-") or "-"
            except Exception:  # noqa: BLE001
                username = "-"

            logger.info(
                "api_access method=%s path=%s status=%s duration_ms=%s request_id=%s user=%s content_length=%s",
                request.method,
                request.path,
                getattr(response, "status_code", "-"),
                duration_ms,
                request_id,
                username,
                request.META.get("CONTENT_LENGTH", "0"),
            )

        return response
