from rest_framework.authentication import TokenAuthentication
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
