from rest_framework import exceptions
from rest_framework.authentication import TokenAuthentication, BaseAuthentication
from rest_framework.authtoken.models import Token


class CookieTokenAuthentication(TokenAuthentication):
    """从 httpOnly cookie 或 Authorization header 读取 token。"""

    def authenticate(self, request):
        token = request.COOKIES.get('auth_token')
        if token:
            try:
                token_obj = Token.objects.select_related('user').get(key=token)
                if token_obj.user.is_active:
                    return (token_obj.user, token_obj)
            except Token.DoesNotExist:
                pass
        return super().authenticate(request)


class APIKeyAuthentication(BaseAuthentication):
    """停止外部 API 凭证认证，保留凭证模型和历史记录。"""

    def authenticate(self, request):
        if request.META.get('HTTP_X_API_KEY', '').strip():
            raise exceptions.AuthenticationFailed('外部 API 访问已停用。')
        return None
