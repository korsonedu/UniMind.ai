from django.conf import settings
from oauth2_provider.oauth2_validators import OAuth2Validator
from authlib.integrations.django_client import OAuth
from authlib.integrations.base_client import OAuthError
from oauth2_provider.views import AuthorizationView, TokenView
from django.db import transaction
from django.shortcuts import redirect
from urllib.parse import urlencode
from oauthlib.oauth2 import InvalidGrantError
from users.models import User


class KorsonOAuth2Validator(OAuth2Validator):
    oidc_claim_scope = {**OAuth2Validator.oidc_claim_scope, 'account_session_version': 'openid'}

    def validate_client_id(self, client_id, request, *args, **kwargs):
        return client_id == settings.ACCOUNT_WEBSITE_CLIENT_ID and super().validate_client_id(client_id, request, *args, **kwargs)

    def validate_grant_type(self, client_id, grant_type, client, request, *args, **kwargs):
        return (client_id == settings.ACCOUNT_WEBSITE_CLIENT_ID and grant_type == 'authorization_code'
                and super().validate_grant_type(client_id, grant_type, client, request, *args, **kwargs))

    def get_additional_claims(self):
        return {
            'name': lambda request: request.user.nickname,
            'email': lambda request: request.user.email,
            'email_verified': lambda request: request.user.email_verified,
            'account_session_version': lambda request: request.user.account_session_version,
        }

    def save_authorization_code(self, client_id, code, request, *args, **kwargs):
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            if not user.is_active or user.account_session_version != request.user.account_session_version:
                raise InvalidGrantError()
            request.user = user
            request.claims = {**(request.claims or {}), 'korson_session_version': user.account_session_version}
            return super().save_authorization_code(client_id, code, request, *args, **kwargs)

    def validate_code(self, client_id, code, client, request, *args, **kwargs):
        if not super().validate_code(client_id, code, client, request, *args, **kwargs):
            return False
        user = User.objects.select_for_update().get(pk=request.user.pk)
        if not user.is_active or request.claims.get('korson_session_version') != user.account_session_version:
            return False
        request.user = user
        return True


class AccountAuthorizationView(AuthorizationView):
    login_url = '/accounts/login/'

    def dispatch(self, request, *args, **kwargs):
        from .services import account_conflict, account_website_origin
        account_website_origin(request)
        if account_conflict(request):
            return redirect('/accounts/select/?' + urlencode({'next': request.get_full_path()}))
        return super().dispatch(request, *args, **kwargs)


class AccountTokenView(TokenView):
    def post(self, request, *args, **kwargs):
        with transaction.atomic():
            return super().post(request, *args, **kwargs)


def website_oauth():
    oauth = OAuth()
    client = oauth.register(
        'korson', client_id=settings.ACCOUNT_WEBSITE_CLIENT_ID,
        client_secret=settings.ACCOUNT_WEBSITE_CLIENT_SECRET,
        server_metadata_url=settings.ACCOUNT_DISCOVERY_URL,
        client_kwargs={'scope': 'openid profile email', 'code_challenge_method': 'S256', 'default_timeout': 10},
    )
    metadata = client.load_server_metadata()
    if metadata.get('issuer') != settings.ACCOUNT_ISSUER_URL:
        raise OAuthError(description='账号服务签发者不匹配。')
    # Our provider uses RSA exclusively; never broaden algorithms from discovery.
    client.server_metadata['id_token_signing_alg_values_supported'] = ['RS256']
    return client
