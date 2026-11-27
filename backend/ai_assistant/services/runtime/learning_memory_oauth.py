"""Authorization-code PKCE for registered learning memory clients."""

import hashlib
import ipaddress
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from oauth2_provider.models import Application
from oauth2_provider.oauth2_validators import OAuth2Validator
from oauthlib.oauth2 import WebApplicationServer
from rest_framework.exceptions import PermissionDenied

from ai_assistant.models import (
    LearningMemoryAuthorizationCode,
    LearningMemoryDynamicClient,
    LearningMemoryGrant,
    LearningMemoryRefreshToken,
)
from users.workspaces.access import membership_for
from users.workspaces.identity import account_user

SCOPES = {
    'learning.memory.read': '读取所选空间的学习记录',
    'learning.memory.notes': '读取所选空间的笔记',
    'learning.memory.write': '保存外部学习检查点',
}
READ_SCOPE = 'learning.memory.read'
TOKEN_LIFETIME = 3600
DCR_MAX_REDIRECT_URIS = 8
ALLOWED_DCR_GRANT_TYPES = frozenset({'authorization_code', 'refresh_token'})


class DynamicClientRegistrationError(ValueError):
    def __init__(self, code, description):
        super().__init__(description)
        self.code = code
        self.description = description


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def memory_token():
    return 'umlm_' + secrets.token_urlsafe(32)


def oauth_enabled(request):
    origin = settings.UNIMIND_LEARNING_MEMORY_OAUTH_ORIGIN
    has_clients = (
        bool(settings.UNIMIND_LEARNING_MEMORY_OAUTH_CLIENT_IDS)
        or bool(getattr(settings, 'UNIMIND_LEARNING_MEMORY_OAUTH_DCR', False))
    )
    return (settings.UNIMIND_LEARNING_MEMORY_CONNECTORS and bool(origin)
            and has_clients
            and origin == f'{request.scheme}://{request.get_host()}')


def dcr_enabled(request):
    return oauth_enabled(request) and bool(getattr(settings, 'UNIMIND_LEARNING_MEMORY_OAUTH_DCR', False))


def resource_uri():
    return settings.UNIMIND_LEARNING_MEMORY_OAUTH_ORIGIN + reverse('learning-memory-mcp')


def registered_client(client_id):
    if not client_id or client_id == settings.ACCOUNT_WEBSITE_CLIENT_ID:
        return None
    allowed_static = client_id in settings.UNIMIND_LEARNING_MEMORY_OAUTH_CLIENT_IDS
    allowed_dynamic = (
        bool(getattr(settings, 'UNIMIND_LEARNING_MEMORY_OAUTH_DCR', False))
        and LearningMemoryDynamicClient.objects.filter(client_id=client_id).exists()
    )
    if not (allowed_static or allowed_dynamic):
        return None
    return Application.objects.filter(
        client_id=client_id, authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
    ).first()


def _is_loopback_redirect(uri):
    return (
        uri.scheme == 'http'
        and uri.hostname in ('127.0.0.1', '::1', 'localhost')
        and uri.port is not None
    )


def validate_dcr_redirect_uri(value):
    if not isinstance(value, str) or not value or len(value) > 2000 or any(ch.isspace() for ch in value):
        raise DynamicClientRegistrationError('invalid_redirect_uri', 'redirect_uri 格式无效。')
    try:
        uri = urlsplit(value)
    except ValueError as exc:
        raise DynamicClientRegistrationError('invalid_redirect_uri', 'redirect_uri 无法解析。') from exc
    if not uri.hostname or uri.username or uri.password or uri.fragment:
        raise DynamicClientRegistrationError('invalid_redirect_uri', 'redirect_uri 不能包含凭据或片段。')
    if _is_loopback_redirect(uri):
        return value
    if uri.scheme != 'https':
        raise DynamicClientRegistrationError(
            'invalid_redirect_uri', 'redirect_uri 必须使用 HTTPS 或本地回环地址（带端口）。',
        )
    try:
        ip = ipaddress.ip_address(uri.hostname)
    except ValueError:
        if uri.hostname in ('localhost', 'localhost.localdomain') or uri.hostname.endswith('.local'):
            raise DynamicClientRegistrationError('invalid_redirect_uri', 'HTTPS redirect_uri 不允许本地域名。')
        return value
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
        raise DynamicClientRegistrationError('invalid_redirect_uri', 'HTTPS redirect_uri 不允许内网或保留 IP。')
    return value


def register_dynamic_client(payload):
    if not isinstance(payload, dict):
        raise DynamicClientRegistrationError('invalid_client_metadata', '请求体必须为 JSON 对象。')
    raw_redirects = payload.get('redirect_uris')
    if not isinstance(raw_redirects, list) or not (1 <= len(raw_redirects) <= DCR_MAX_REDIRECT_URIS):
        raise DynamicClientRegistrationError(
            'invalid_redirect_uri', f'redirect_uris 必须提供 1 至 {DCR_MAX_REDIRECT_URIS} 个回调地址。',
        )
    redirect_uris = list(dict.fromkeys(validate_dcr_redirect_uri(item) for item in raw_redirects))

    raw_name = payload.get('client_name', 'MCP Client')
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise DynamicClientRegistrationError('invalid_client_metadata', 'client_name 必须为非空字符串。')
    client_name = raw_name.strip()[:80]

    auth_method = payload.get('token_endpoint_auth_method', 'none')
    if auth_method != 'none':
        raise DynamicClientRegistrationError(
            'invalid_client_metadata', '动态客户端注册仅支持公开 PKCE 客户端（token_endpoint_auth_method="none"）。',
        )

    grant_types = payload.get('grant_types', ['authorization_code', 'refresh_token'])
    if (not isinstance(grant_types, list) or not grant_types
            or any(not isinstance(item, str) for item in grant_types)
            or not set(grant_types) <= ALLOWED_DCR_GRANT_TYPES
            or 'authorization_code' not in grant_types):
        raise DynamicClientRegistrationError('invalid_client_metadata', 'grant_types 仅支持 authorization_code 和 refresh_token。')
    grant_types = list(dict.fromkeys(grant_types))

    response_types = payload.get('response_types', ['code'])
    if response_types != ['code']:
        raise DynamicClientRegistrationError('invalid_client_metadata', 'response_types 仅支持 ["code"]。')

    raw_scope = payload.get('scope')
    validated_scope = None
    if raw_scope is not None:
        if not isinstance(raw_scope, str) or not raw_scope.strip():
            raise DynamicClientRegistrationError('invalid_client_metadata', 'scope 格式无效。')
        scopes = raw_scope.split()
        if not set(scopes) <= SCOPES.keys():
            raise DynamicClientRegistrationError('invalid_client_metadata', '请求的 scope 不被支持。')
        validated_scope = ' '.join(dict.fromkeys(scopes))

    raw_client_uri = payload.get('client_uri', '')
    client_uri = ''
    if raw_client_uri:
        if not isinstance(raw_client_uri, str) or len(raw_client_uri) > 500:
            raise DynamicClientRegistrationError('invalid_client_metadata', 'client_uri 无效。')
        parsed_uri = urlsplit(raw_client_uri)
        if parsed_uri.scheme != 'https' or not parsed_uri.hostname or parsed_uri.username or parsed_uri.password:
            raise DynamicClientRegistrationError('invalid_client_metadata', 'client_uri 必须为有效的 HTTPS 地址。')
        client_uri = raw_client_uri

    client_id = 'umdcr_' + secrets.token_urlsafe(24)
    issued_at = int(timezone.now().timestamp())
    with transaction.atomic():
        Application.objects.create(
            client_id=client_id,
            client_secret='',
            name=client_name,
            client_type=Application.CLIENT_PUBLIC,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris=' '.join(redirect_uris),
        )
        LearningMemoryDynamicClient.objects.create(
            client_id=client_id,
            client_name=client_name,
            client_uri=client_uri,
            redirect_uris=redirect_uris,
        )

    response = {
        'client_id': client_id,
        'client_id_issued_at': issued_at,
        'client_name': client_name,
        'redirect_uris': redirect_uris,
        'grant_types': grant_types,
        'response_types': ['code'],
        'token_endpoint_auth_method': 'none',
    }
    if client_uri:
        response['client_uri'] = client_uri
    if validated_scope:
        response['scope'] = validated_scope
    return response


def learner_account_active(learner, account):
    if not account.is_active or not learner.is_active or account_user(learner).pk != account.pk:
        return False
    try:
        membership_for(learner)
    except PermissionDenied:
        return False
    return True


class LearningMemoryOAuthValidator(OAuth2Validator):
    # Preserve toolkit client secret verification, while limiting app lookup to this resource.
    def _load_application(self, client_id, request):
        request.client = registered_client(client_id)
        return request.client

    def validate_redirect_uri(self, client_id, redirect_uri, request, *args, **kwargs):
        try:
            uri = urlsplit(redirect_uri)
            loopback = uri.scheme == 'http' and uri.hostname in ('127.0.0.1', '::1', 'localhost') and uri.port
            if redirect_uri not in request.client.redirect_uris.split() and not loopback:
                return False
            return request.client.redirect_uri_allowed(redirect_uri)
        except ValueError:
            return False

    def get_default_redirect_uri(self, client_id, request, *args, **kwargs):
        return None

    def is_pkce_required(self, client_id, request):
        return True

    def get_default_scopes(self, client_id, request, *args, **kwargs):
        return [READ_SCOPE]

    def validate_scopes(self, client_id, scopes, client, request, *args, **kwargs):
        return READ_SCOPE in scopes and set(scopes) <= SCOPES.keys()

    def save_authorization_code(self, client_id, code, request, *args, **kwargs):
        now = timezone.now()
        LearningMemoryAuthorizationCode.objects.filter(expires_at__lte=now).delete()
        LearningMemoryAuthorizationCode.objects.create(
            learner=request.learning_learner, account=request.user, account_session_version=request.user.account_session_version,
            digest=digest(code['code']), client_id=client_id, redirect_uri=request.redirect_uri,
            resource=resource_uri(), challenge=request.code_challenge,
            scope=' '.join(request.scopes), expires_at=now + timedelta(seconds=90),
        )

    def validate_code(self, client_id, code, client, request, *args, **kwargs):
        # Lock the code until token creation and consumption finish in the same transaction.
        row = LearningMemoryAuthorizationCode.objects.select_for_update().filter(
            digest=digest(code), client_id=client_id, resource=resource_uri(), expires_at__gt=timezone.now(),
        ).first()
        if (row is None or request.resource != row.resource
                or row.account.account_session_version != row.account_session_version
                or not learner_account_active(row.learner if row.learner_id else row.project.user, row.account)):
            return False
        request.learning_code = row
        request.user = row.account
        request.scopes = row.scope.split()
        return True

    def get_code_challenge(self, code, request):
        return request.learning_code.challenge

    def get_code_challenge_method(self, code, request):
        return 'S256'

    def confirm_redirect_uri(self, client_id, code, redirect_uri, client, request, *args, **kwargs):
        return (request.learning_code.redirect_uri == redirect_uri
                and self.validate_redirect_uri(client_id, redirect_uri, request))

    def invalidate_authorization_code(self, client_id, code, request, *args, **kwargs):
        request.learning_code.delete()

    def validate_refresh_token(self, refresh_token, client, request, *args, **kwargs):
        row = LearningMemoryRefreshToken.objects.filter(digest=digest(refresh_token)).first()
        if row is None:
            return False
        grant = LearningMemoryGrant.objects.select_for_update().filter(
            pk=row.grant_id, oauth_client_id=client.client_id, oauth_resource=resource_uri(),
            oauth_authorized_until__gt=timezone.now(),
        ).first()
        if grant is None:
            return False
        learner = grant.owner
        account = account_user(learner)
        if (account.account_session_version != grant.oauth_account_session_version
                or not learner_account_active(learner, account)):
            return False
        if LearningMemoryRefreshToken.objects.filter(pk=row.pk, used=True).exists():
            # A replay invalidates the integration and every token issued for it.
            grant.delete()
            return False
        request.learning_grant = grant
        request.learning_refresh = row
        request.user = account
        return True

    def get_original_scopes(self, refresh_token, request, *args, **kwargs):
        return request.learning_refresh.scope

    def rotate_refresh_token(self, request):
        return True

    def save_bearer_token(self, token, request, *args, **kwargs):
        now = timezone.now()
        if request.grant_type == 'refresh_token':
            grant = request.learning_grant
            original_scope = request.learning_refresh.scope
            request.learning_refresh.used = True
            request.learning_refresh.save(update_fields=['used'])
        else:
            row = request.learning_code
            original_scope = row.scope
            grant = LearningMemoryGrant(project=row.project, learner=row.learner, name=request.client.name[:80], oauth_resource=row.resource,
                oauth_client_id=row.client_id, oauth_account_session_version=row.account_session_version,
                oauth_authorized_until=now + timedelta(days=30))
        grant.digest = digest(token['access_token'])
        grant.expires_at = min(grant.oauth_authorized_until, now + timedelta(seconds=TOKEN_LIFETIME))
        grant.can_write = 'learning.memory.write' in request.scopes
        grant.share_notes = 'learning.memory.notes' in request.scopes
        grant.save()
        token['expires_in'] = max(0, int((grant.expires_at - now).total_seconds()))
        LearningMemoryRefreshToken.objects.create(
            grant=grant, digest=digest(token['refresh_token']), scope=original_scope,
        )


def server():
    return WebApplicationServer(LearningMemoryOAuthValidator(), token_generator=lambda _: memory_token(),
                                refresh_token_generator=lambda _: secrets.token_urlsafe(32), token_expires_in=TOKEN_LIFETIME)
