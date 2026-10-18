from django.core.cache import cache
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from django.test import Client
from unittest.mock import patch
from django.db import IntegrityError
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token

from users.models import User


@override_settings(
    ACCOUNT_ENABLED=True,
    ACCOUNT_WEBSITE_ORIGINS=["http://testserver"],
    ACCOUNT_CENTER_ORIGIN="http://testserver",
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class AccountTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_website_cookie_is_not_account_cookie(self):
        user = User.objects.create_user(username="existing", password="Pass12345")
        self.client.force_login(user)
        original = self.client.cookies["sessionid"].value
        response = self.client.get("/account-api/session/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        self.assertIsNone(response.json()["user"])
        self.assertEqual(self.client.cookies["sessionid"].value, original)

    @override_settings(ACCOUNT_ENABLED=False)
    def test_disabled_account_does_not_mutate_platform_cookie(self):
        user = User.objects.create_user(username="existing", password="Pass12345")
        token = Token.objects.create(user=user)
        self.client.cookies["auth_token"] = token.key
        response = self.client.get("/account-api/session/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(Token.objects.get(user=user).key, token.key)
        self.assertNotIn("auth_token", response.cookies)

    def test_unknown_website_host_is_rejected(self):
        response = self.client.get("/account-api/session/", HTTP_HOST="localhost:9999")
        self.assertEqual(response.status_code, 403)

    def put_code(self, email, purpose='register', code='123456'):
        cache.set(f'account_code:{purpose}:{email}', {
            'purpose': purpose, 'id': 'one-use-code', 'code_hash': make_password(code),
            'sent_at': timezone.now().isoformat(),
        }, timeout=600)

    def test_registration_does_not_grant_learning(self):
        self.put_code('student@example.com')
        response = self.client.post('/accounts/register/', {
            'email': 'student@example.com', 'code': '123456', 'password': 'Pass12345',
            'nickname': '同学', 'agreed_to_terms': 'on',
        })
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email='student@example.com')
        self.assertIsNone(user.institution_id)
        self.assertFalse(user.is_member)
        self.assertEqual(user.personal_plan, 'free')
        self.assertEqual(user.role, 'student')
        self.assertTrue(user.agreed_to_terms)
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_wrong_code_purpose_does_not_register(self):
        self.put_code('student@example.com', 'reset_password')
        response = self.client.post('/accounts/register/', {
            'email': 'student@example.com', 'code': '123456', 'password': 'Pass12345',
            'agreed_to_terms': 'on',
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(email='student@example.com').exists())

    def test_registration_requires_terms(self):
        self.put_code('student@example.com')
        response = self.client.post('/accounts/register/', {
            'email': 'student@example.com', 'code': '123456', 'password': 'Pass12345',
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(email='student@example.com').exists())

    def test_code_consumed_only_once(self):
        from users.accounts import services
        self.put_code('student@example.com')
        services.consume_account_code('student@example.com', '123456', purpose='register')
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            services.consume_account_code('student@example.com', '123456', purpose='register')

    def test_account_login_keeps_existing_platform_token(self):
        user = User.objects.create_user(username='paid', password='Pass12345')
        original = Token.objects.create(user=user).key
        response = self.client.post('/accounts/login/', {'identifier': 'paid', 'password': 'Pass12345'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)
        self.assertEqual(Token.objects.get(user=user).key, original)

    def test_failed_password_locks_account(self):
        user = User.objects.create_user(username='existing', password='Pass12345')
        for _ in range(5):
            self.client.post('/accounts/login/', {'identifier': 'existing', 'password': 'wrong'})
        user.refresh_from_db()
        self.assertIsNotNone(user.locked_until)
        response = self.client.post('/accounts/login/', {'identifier': 'existing', 'password': 'Pass12345'})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_registration_and_login_reject_missing_csrf(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post('/accounts/login/', {'identifier': 'existing', 'password': 'Pass12345'})
        self.assertEqual(response.status_code, 403)

    @patch('core.email_service.send_verification_email', return_value=True)
    def test_code_send_has_email_cooldown(self, send):
        data = {'email': 'student@example.com', 'purpose': 'register'}
        first = self.client.post('/accounts/send-code/', data)
        second = self.client.post('/accounts/send-code/', data)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)

    def test_reset_changes_existing_password_without_new_account(self):
        user = User.objects.create_user(username='existing', email='student@example.com',
                                        email_verified=True, password='Pass12345')
        self.put_code(user.email, 'reset_password')
        response = self.client.post('/accounts/reset-password/', {
            'email': user.email, 'code': '123456', 'password': 'FreshPass12345',
        })
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.check_password('FreshPass12345'))
        self.assertEqual(User.objects.count(), 1)

    def test_code_expires_and_five_wrong_attempts_invalidate_it(self):
        from users.accounts import services
        from django.core.exceptions import ValidationError
        self.put_code('student@example.com')
        for _ in range(5):
            with self.assertRaises(ValidationError):
                services.consume_account_code('student@example.com', '654321', purpose='register')
        with self.assertRaises(ValidationError):
            services.consume_account_code('student@example.com', '123456', purpose='register')

    def test_inactive_user_cannot_login(self):
        User.objects.create_user(username='disabled', password='Pass12345', is_active=False)
        response = self.client.post('/accounts/login/', {'identifier': 'disabled', 'password': 'Pass12345'})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('_auth_user_id', self.client.session)

    @patch('users.models.User.objects.create_user', side_effect=IntegrityError("users_verified_email_ci_unique"))
    def test_legacy_register_email_conflict_is_not_500(self, create):
        cache.set('verification_code:student@example.com', {'code_hash': make_password('123456'), 'sent_at': timezone.now().isoformat()})
        response = self.client.post('/api/users/register/', {
            'email': 'student@example.com', 'code': '123456', 'password': 'Pass12345', 'agreed_to_terms': True,
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.exists())

    @patch('users.models.User.objects.create_user', side_effect=IntegrityError("users_verified_email_ci_unique"))
    def test_legacy_code_creation_email_conflict_is_not_500(self, create):
        cache.set('verification_code:student@example.com', {'code_hash': make_password('123456'), 'sent_at': timezone.now().isoformat()})
        response = self.client.post('/api/users/login-by-code/', {'email': 'student@example.com', 'code': '123456'})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.exists())

    def website_client(self, user):
        from django.contrib.sessions.backends.db import SessionStore
        session = SessionStore()
        session.update({
            '_auth_user_id': str(user.pk), '_auth_user_backend': 'django.contrib.auth.backends.ModelBackend',
            '_auth_user_hash': user.get_session_auth_hash(), 'account_user_id': user.pk,
            'account_session_version': user.account_session_version, 'account_audience': 'website',
        })
        session.save()
        client = Client()
        client.cookies['korson_account_session'] = session.session_key
        return client

    def test_legacy_cookie_creates_center_session_without_rotating_token(self):
        user = User.objects.create_user(username='existing', password='Pass12345')
        token = Token.objects.create(user=user)
        self.client.cookies['auth_token'] = token.key
        response = self.client.get('/accounts/profile/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)
        self.assertEqual(Token.objects.get(user=user).key, token.key)

    def test_original_username_takes_priority_over_another_accounts_email(self):
        original = User.objects.create_user(username='shared@example.test', password='Pass12345')
        User.objects.create_user(username='other', email='shared@example.test', password='OtherPass12345', email_verified=True)
        response = self.client.post('/accounts/login/', {'identifier': original.username, 'password': 'Pass12345'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session['_auth_user_id']), original.pk)

    def test_paid_platform_entry_preserves_token_and_institution(self):
        user = User.objects.create_user(username='paid', password='Pass12345', is_member=True)
        token = Token.objects.create(user=user)
        self.client.post('/accounts/login/', {'identifier': user.username, 'password': 'Pass12345'})
        response = self.client.get('/accounts/unimind/')
        self.assertEqual(response['Location'], 'http://localhost:5173/account-callback')
        self.assertEqual(response.cookies['auth_token'].value, token.key)
        user.refresh_from_db()
        self.assertIsNone(user.institution_id)

    def test_free_platform_entry_creates_platform_token(self):
        user = User.objects.create_user(username='free', password='Pass12345')
        self.client.post('/accounts/login/', {'identifier': user.username, 'password': 'Pass12345'})
        response = self.client.get('/accounts/unimind/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], 'http://localhost:5173/account-callback')
        self.assertTrue(Token.objects.filter(user=user).exists())
        self.assertIn('auth_token', response.cookies)

    def test_conflicting_accounts_require_explicit_selection(self):
        account = User.objects.create_user(username='account', password='Pass12345', is_member=True)
        platform = User.objects.create_user(username='platform', password='Pass12345', is_member=True)
        token = Token.objects.create(user=platform)
        self.client.post('/accounts/login/', {'identifier': account.username, 'password': 'Pass12345'})
        self.client.cookies['auth_token'] = token.key
        response = self.client.get('/accounts/unimind/')
        self.assertTrue(response['Location'].startswith('/accounts/select/?'))
        self.assertEqual(int(self.client.session['_auth_user_id']), account.pk)
        self.assertEqual(self.client.cookies['auth_token'].value, token.key)
        response = self.client.post('/accounts/select/', {'selection': 'platform', 'next': '/accounts/unimind/'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session['_auth_user_id']), platform.pk)

    def test_website_logout_leaves_other_service_session_active(self):
        user = User.objects.create_user(username='existing', password='Pass12345')
        token = Token.objects.create(user=user)
        self.client.post('/accounts/login/', {'identifier': user.username, 'password': 'Pass12345'})
        website = self.website_client(user)
        self.assertEqual(website.get('/account-api/session/').json()['user']['id'], user.pk)
        self.assertEqual(website.post('/account-api/logout/').status_code, 200)
        self.assertIsNone(website.get('/account-api/session/').json()['user'])
        self.assertEqual(self.client.get('/accounts/profile/').status_code, 200)
        self.assertEqual(Token.objects.get(user=user).key, token.key)

    def test_revoke_invalidates_sessions_and_legacy_token(self):
        from users.accounts import services
        user = User.objects.create_user(username='existing', password='Pass12345')
        Token.objects.create(user=user)
        website = self.website_client(user)
        self.client.post('/accounts/login/', {'identifier': user.username, 'password': 'Pass12345'})
        services.revoke_account_sessions(user.pk)
        self.assertIsNone(website.get('/account-api/session/').json()['user'])
        self.assertEqual(self.client.get('/accounts/profile/').status_code, 302)
        user.refresh_from_db()
        self.assertEqual(user.account_session_version, 1)
        self.assertFalse(Token.objects.filter(user=user).exists())

    def test_password_change_and_disable_revoke_tokens(self):
        user = User.objects.create_user(username='existing', password='Pass12345')
        for action in ['password', 'disable']:
            with self.subTest(action=action):
                Token.objects.create(user=user)
                version = user.account_session_version
                if action == 'password':
                    user.set_password('FreshPass12345')
                    user.save(update_fields=['password'])
                else:
                    user.is_active = False
                    user.save(update_fields=['is_active'])
                user.refresh_from_db()
                self.assertEqual(user.account_session_version, version + 1)
                self.assertFalse(Token.objects.filter(user=user).exists())

    def test_logout_all_is_post_only_and_revokes_other_sessions(self):
        user = User.objects.create_user(username='existing', password='Pass12345')
        website = self.website_client(user)
        self.client.post('/accounts/login/', {'identifier': user.username, 'password': 'Pass12345'})
        self.assertEqual(self.client.get('/accounts/logout-all/').status_code, 405)
        self.assertEqual(self.client.post('/accounts/logout-all/').status_code, 302)
        self.assertIsNone(website.get('/account-api/session/').json()['user'])


@override_settings(
    ACCOUNT_ENABLED=True,
    ACCOUNT_WEBSITE_ORIGINS=['http://testserver'],
    ACCOUNT_CENTER_ORIGIN='http://testserver',
    ACCOUNT_ISSUER_URL='http://testserver/accounts/o',
    ACCOUNT_DISCOVERY_URL='http://testserver/accounts/o/.well-known/openid-configuration',
    ACCOUNT_WEBSITE_CLIENT_ID='test-website',
    ACCOUNT_WEBSITE_CLIENT_SECRET='test-only-secret-that-is-never-deployed-12345',
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class AccountOAuthTests(TestCase):
    def setUp(self):
        from jwcrypto import jwk
        from oauth2_provider.models import Application
        cache.clear()
        self.key = jwk.JWK.generate(kty='RSA', size=2048)
        provider = override_settings(OAUTH2_PROVIDER={
            'OIDC_ENABLED': True, 'OIDC_RSA_PRIVATE_KEY': self.key.export_to_pem(private_key=True, password=None).decode(),
            'OIDC_ISS_ENDPOINT': 'http://testserver/accounts/o',
            'OAUTH2_VALIDATOR_CLASS': 'users.accounts.oidc.KorsonOAuth2Validator',
            'SCOPES': {'openid': 'identity', 'profile': 'profile', 'email': 'email'},
            'PKCE_REQUIRED': True, 'COMPLIANT_BCP_RFC9700_PKCE_METHOD': True,
            'ALLOWED_REDIRECT_URI_SCHEMES': ['http'], 'OAUTHLIB_CORE_ALWAYS_RELOAD': True,
        })
        provider.enable()
        self.addCleanup(provider.disable)
        Application.objects.create(
            name='test website', client_id='test-website',
            client_secret='test-only-secret-that-is-never-deployed-12345',
            client_type='confidential', authorization_grant_type='authorization-code',
            algorithm='RS256', skip_authorization=True, redirect_uris='http://testserver/account-api/callback/',
        )
        self.user = User.objects.create_user(username='existing', password='Pass12345', email='student@example.com', email_verified=True)
        self.center = Client()
        self.center.post('/accounts/login/', {'identifier': 'existing', 'password': 'Pass12345'})
        self.attack = ''

    def provider_request(self, prepared, **kwargs):
        import json
        import requests
        from urllib.parse import urlsplit, parse_qs, urlencode
        from jwcrypto import jwt
        parsed = urlsplit(prepared.url)
        self.assertEqual(parsed.netloc, 'testserver')
        body = prepared.body or b''
        if self.attack == 'pkce' and parsed.path.endswith('/token/'):
            data = parse_qs(body.decode() if isinstance(body, bytes) else body)
            data['code_verifier'] = ['incorrect-verifier']
            body = urlencode({key: values[0] for key, values in data.items()})
        response = Client().generic(
            prepared.method, parsed.path + ('?' + parsed.query if parsed.query else ''),
            data=body, content_type=prepared.headers.get('Content-Type', 'application/octet-stream'),
            HTTP_HOST='testserver', HTTP_AUTHORIZATION=prepared.headers.get('Authorization', ''),
        )
        content = response.content
        if self.attack in {'nonce', 'issuer', 'audience', 'nonce-disabled'} and parsed.path.endswith('/token/') and response.status_code == 200:
            data = json.loads(content)
            claims = json.loads(jwt.JWT(key=self.key, jwt=data['id_token']).claims)
            claims[{'nonce': 'nonce', 'issuer': 'iss', 'audience': 'aud', 'nonce-disabled': 'nonce'}[self.attack]] = 'wrong'
            if self.attack == 'nonce-disabled':
                claims['nonce_supported'] = False
            signed = jwt.JWT(header={'alg': 'RS256', 'kid': self.key.thumbprint()}, claims=claims)
            signed.make_signed_token(self.key)
            data['id_token'] = signed.serialize()
            content = json.dumps(data).encode()
        result = requests.Response()
        result.status_code, result._content, result.url = response.status_code, content, prepared.url
        result.headers.update(dict(response.headers))
        result.request = prepared
        return result

    def flow(self, return_to='/schools/de'):
        from urllib.parse import urlsplit
        started = self.client.get('/account-api/login/', {'return_to': return_to})
        self.assertEqual(started.status_code, 302)
        authorized = self.center.get(started['Location'])
        self.assertEqual(authorized.status_code, 302)
        callback = urlsplit(authorized['Location'])
        return callback.path + '?' + callback.query

    @patch('requests.sessions.Session.send')
    def test_real_code_exchange_preserves_identity_and_token(self, network):
        network.side_effect = self.provider_request
        token = Token.objects.create(user=self.user)
        callback = self.flow('/schools/de?province=北京')
        response = self.client.get(callback)
        self.assertEqual(response['Location'], '/schools/de?province=%E5%8C%97%E4%BA%AC')
        session = self.client.get('/account-api/session/').json()
        self.assertEqual(session['user']['id'], self.user.pk)
        self.assertEqual(Token.objects.get(user=self.user).key, token.key)
        self.assertEqual(self.client.get(callback)['Location'], '/account?error=login')

    @patch('requests.sessions.Session.send')
    def test_invalid_state_does_not_create_session(self, network):
        network.side_effect = self.provider_request
        response = self.client.get('/account-api/callback/?state=wrong&code=wrong')
        self.assertEqual(response['Location'], '/account?error=login')
        self.assertIsNone(self.client.get('/account-api/session/').json()['user'])

    @patch('requests.sessions.Session.send')
    def test_wrong_nonce_issuer_audience_and_pkce_are_rejected(self, network):
        network.side_effect = self.provider_request
        for attack in ['nonce', 'issuer', 'audience', 'nonce-disabled', 'pkce']:
            with self.subTest(attack=attack):
                self.client = Client()
                self.attack = attack
                response = self.client.get(self.flow())
                self.assertEqual(response['Location'], '/account?error=login')
                self.assertIsNone(self.client.get('/account-api/session/').json()['user'])

    def test_open_redirects_are_rejected(self):
        from users.accounts import services
        for value in ['https://evil.example/', '//evil.example/', '/\\evil.example/', '/%2f%2fevil.example/', '/%0d%0aLocation:evil']:
            self.assertEqual(services.safe_site_return_path(value), '/account')
        self.assertEqual(services.safe_site_return_path('/schools/de?x=1'), '/schools/de?x=1')

    def test_oauth_client_management_is_not_exposed(self):
        response = self.center.get('/accounts/o/applications/register/')
        self.assertEqual(response.status_code, 404)

    @patch('requests.sessions.Session.send')
    def test_authorization_code_is_invalid_after_logout_all(self, network):
        network.side_effect = self.provider_request
        callback = self.flow()
        self.center.post('/accounts/logout-all/')
        self.assertEqual(self.client.get(callback)['Location'], '/account?error=login')
        self.assertIsNone(self.client.get('/account-api/session/').json()['user'])

    def test_stale_authorization_request_cannot_issue_new_code(self):
        from types import SimpleNamespace
        from oauthlib.oauth2 import InvalidGrantError
        from users.accounts.oidc import KorsonOAuth2Validator
        User.objects.filter(pk=self.user.pk).update(account_session_version=1)
        request = SimpleNamespace(user=self.user, claims={})
        with self.assertRaises(InvalidGrantError):
            KorsonOAuth2Validator().save_authorization_code('test-website', {'code': 'stale'}, request)

    @patch('requests.sessions.Session.send')
    def test_multiple_pending_logins_keep_their_return_paths(self, network):
        network.side_effect = self.provider_request
        first = self.flow('/schools/de?one=1')
        second = self.flow('/research')
        self.assertEqual(self.client.get(first)['Location'], '/schools/de?one=1')
        self.assertEqual(self.client.get(second)['Location'], '/research')
