import hashlib
import hmac

from django.utils import timezone
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
    """API Key 认证 — 从 X-API-Key header 解析并验证 API 凭证。

    格式: X-API-Key: <raw_secret>
    验证: SHA256(raw_secret) == key_secret_hash
    验证成功后设置 request.api_credential 和 request.api_scopes。
    无 API Key header 时返回 None（让其他认证类处理）。
    """

    def authenticate(self, request):
        raw_secret = request.META.get('HTTP_X_API_KEY', '').strip()
        if not raw_secret:
            return None

        from users.models import APICredential

        # 查找匹配的凭证：遍历活跃 key，比对 SHA256(secret)
        secret_hash = hashlib.sha256(raw_secret.encode('utf-8')).hexdigest()
        try:
            cred = APICredential.objects.select_related('institution').get(
                key_secret_hash=secret_hash, is_active=True,
            )
        except APICredential.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid API key')

        if not cred.institution.is_active:
            raise exceptions.AuthenticationFailed('Institution is not active')

        # 速率限制检查（原子 incr）
        from django.core.cache import cache
        cache_key = f'api_rate:{cred.key_id}'
        try:
            count = cache.incr(cache_key)
        except ValueError:
            # key 不存在，创建并设过期
            cache.set(cache_key, 1, 60)
            count = 1

        if count > cred.rate_limit:
            raise exceptions.AuthenticationFailed('Rate limit exceeded')

        cred.last_used_at = timezone.now()
        cred.save(update_fields=['last_used_at'])

        request.api_credential = cred
        request.api_scopes = cred.scopes

        return (None, None)
