import time

from django.conf import settings
from django.contrib.auth import logout
from django.contrib.sessions.backends.base import UpdateError
from django.contrib.sessions.exceptions import SessionInterrupted
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import JsonResponse
from django.utils.cache import patch_vary_headers
from django.utils.http import http_date
from django.utils.deprecation import MiddlewareMixin


class AccountSessionMiddleware(SessionMiddleware):
    """Only the website API uses its own host-only, path-scoped session cookie."""

    def process_request(self, request):
        request.is_website_account = request.path.startswith('/account-api/')
        if request.is_website_account:
            request.session = self.SessionStore(request.COOKIES.get('korson_account_session'))
        else:
            super().process_request(request)

    def process_response(self, request, response):
        if not getattr(request, 'is_website_account', False):
            return super().process_response(request, response)
        session = request.session
        name, path = 'korson_account_session', '/account-api/'
        if session.accessed:
            patch_vary_headers(response, ('Cookie',))
        if session.is_empty():
            if name in request.COOKIES:
                response.delete_cookie(name, path=path, samesite='Lax')
            return response
        if (session.modified or settings.SESSION_SAVE_EVERY_REQUEST) and response.status_code < 500:
            max_age = None if session.get_expire_at_browser_close() else session.get_expiry_age()
            try:
                session.save()
            except UpdateError as exc:
                raise SessionInterrupted('账号会话已退出，请重新登录。') from exc
            response.set_cookie(
                name, session.session_key, path=path,
                max_age=max_age, expires=http_date(time.time() + max_age) if max_age else None,
                secure=settings.SESSION_COOKIE_SECURE, httponly=True, samesite='Lax',
            )
        return response


class AccountBoundaryMiddleware(MiddlewareMixin):
    def process_request(self, request):
        website = request.path.startswith('/account-api/')
        center = request.path.startswith('/accounts/')
        if not website and not center:
            return None
        if not settings.ACCOUNT_ENABLED:
            return JsonResponse({'error': '账号服务暂未启用'}, status=503)
        origin = f'{request.scheme}://{request.get_host()}'
        allowed = settings.ACCOUNT_WEBSITE_ORIGINS if website else [settings.ACCOUNT_CENTER_ORIGIN]
        if origin not in allowed:
            return JsonResponse({'error': '账号请求来源不正确'}, status=403)
        audience = 'website' if website else 'account'
        if request.user.is_authenticated:
            from .services import account_is_current
            if not account_is_current(request, audience=audience):
                logout(request)
        if center and not request.user.is_authenticated and request.path in {
                '/accounts/o/authorize/', '/accounts/profile/', '/accounts/unimind/', '/accounts/login/', '/accounts/desktop/'}:
            from .services import legacy_cookie_user, begin_account_session
            user = legacy_cookie_user(request)
            if user:
                begin_account_session(request, user, audience='account')

    def process_response(self, request, response):
        if request.path.startswith(('/account-api/', '/accounts/', '/api/users/desktop-auth/')):
            response['Cache-Control'] = 'no-store'
            response['Referrer-Policy'] = 'no-referrer'
        return response
