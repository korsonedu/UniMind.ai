from rest_framework import exceptions
from rest_framework.authentication import TokenAuthentication, BaseAuthentication
from users.login_sessions import LoginSession


class CookieTokenAuthentication(TokenAuthentication):
    """从 httpOnly cookie 或 Authorization header 读取 token。"""

    def authenticate(self, request):
        token = request.COOKIES.get('auth_token')
        token_obj = LoginSession.resolve(token)
        if token_obj:
            return (token_obj.user, token_obj)
        return super().authenticate(request)

    def authenticate_credentials(self, key):
        token = LoginSession.resolve(key)
        if token:
            return (token.user, token)
        return super().authenticate_credentials(key)


class APIKeyAuthentication(BaseAuthentication):
    """停止外部 API 凭证认证，保留凭证模型和历史记录。"""

    def authenticate(self, request):
        if request.META.get('HTTP_X_API_KEY', '').strip():
            raise exceptions.AuthenticationFailed('外部 API 访问已停用。')
        return None
