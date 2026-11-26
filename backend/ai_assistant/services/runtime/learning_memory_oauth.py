"""Authorization-code PKCE for registered learning memory clients."""

import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from oauth2_provider.models import Application
from oauth2_provider.oauth2_validators import OAuth2Validator
from oauthlib.oauth2 import WebApplicationServer
from rest_framework.exceptions import PermissionDenied

from ai_assistant.models import LearningMemoryAuthorizationCode, LearningMemoryGrant, LearningMemoryRefreshToken
from users.workspaces.access import membership_for
from users.workspaces.identity import account_user

SCOPES = {
    'learning.memory.read': '读取所选空间的学习记录',
    'learning.memory.notes': '读取所选空间的笔记',
    'learning.memory.write': '保存外部学习检查点',
}
READ_SCOPE = 'learning.memory.read'
TOKEN_LIFETIME = 3600


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def memory_token():
    return 'umlm_' + secrets.token_urlsafe(32)


def oauth_enabled(request):
    origin = settings.UNIMIND_LEARNING_MEMORY_OAUTH_ORIGIN
    return (settings.UNIMIND_LEARNING_MEMORY_CONNECTORS and bool(origin)
            and bool(settings.UNIMIND_LEARNING_MEMORY_OAUTH_CLIENT_IDS)
            and origin == f'{request.scheme}://{request.get_host()}')


def resource_uri():
    return settings.UNIMIND_LEARNING_MEMORY_OAUTH_ORIGIN + reverse('learning-memory-mcp')


def registered_client(client_id):
    if client_id == settings.ACCOUNT_WEBSITE_CLIENT_ID or client_id not in settings.UNIMIND_LEARNING_MEMORY_OAUTH_CLIENT_IDS:
        return None
    return Application.objects.filter(client_id=client_id, authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE).first()


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
            loopback = uri.scheme == 'http' and uri.hostname in ('127.0.0.1', '::1') and uri.port
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
