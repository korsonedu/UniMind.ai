import hashlib
import hmac
import json
import re
import time
from uuid import UUID

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed


class DirectusAdminAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return 'Signature'

    def authenticate(self, request):
        actor = request.headers.get('X-Unimind-Operator', '')
        timestamp = request.headers.get('X-Unimind-Timestamp', '')
        nonce = request.headers.get('X-Unimind-Nonce', '')
        signature = request.headers.get('X-Unimind-Signature', '')
        secret = settings.UNIMIND_ADMIN_BRIDGE_SECRET
        mapping = settings.UNIMIND_DIRECTUS_ADMIN_MAP
        try:
            mapping = json.loads(mapping) if isinstance(mapping, str) else mapping
            if len(secret) < 32 or not isinstance(mapping, dict) or len(mapping) != 2:
                raise ValueError()
            if len(set(mapping.values())) != 2 or any(not isinstance(pk, int) or isinstance(pk, bool) or pk < 1 for pk in mapping.values()):
                raise ValueError()
            for key in mapping:
                UUID(key)
            UUID(actor)
            UUID(nonce)
            if not re.fullmatch(r'[0-9a-f]{64}', signature):
                raise ValueError()
            if actor not in mapping or abs(time.time() - int(timestamp)) > 60:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise AuthenticationFailed('管理身份无效或后台接入尚未配置。')
        canonical = '\n'.join(['v1', request.method, request.get_full_path(), actor, timestamp,
                               nonce, hashlib.sha256(request.body).hexdigest()])
        expected = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise AuthenticationFailed('管理请求签名无效。')
        user = get_user_model().objects.filter(pk=mapping[actor], is_active=True, is_staff=True,
                                               is_superuser=True, institution__isnull=True).first()
        if not user:
            raise AuthenticationFailed('管理账号未映射或已停用。')
        try:
            fresh = cache.add(f'backoffice:nonce:{actor}:{nonce}', 1, 125)
        except Exception:
            raise AuthenticationFailed('身份校验服务暂不可用。')
        if not fresh:
            raise AuthenticationFailed('管理请求已处理，请重新发起。')
        return user, actor
