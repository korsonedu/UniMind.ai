import base64
import hashlib
import secrets
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from rest_framework.authtoken.models import Token

from users.models import User
from users.login_sessions import LoginSession


@override_settings(
    ACCOUNT_ENABLED=False,
    ACCOUNT_UNIMIND_ORIGIN='http://testserver',
    ACCOUNT_CENTER_ORIGIN='http://testserver',
    ACCOUNT_WEBSITE_ORIGINS=['http://testserver'],
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class DesktopAuthSmokeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='desktop', email='desktop@example.test')
        self.verifier = secrets.token_urlsafe(32)
        self.state = secrets.token_urlsafe(32)
        self.challenge = base64.urlsafe_b64encode(hashlib.sha256(self.verifier.encode()).digest()).rstrip(b'=').decode()

    def start(self, client=None, **headers):
        return (client or self.client).post('/api/users/desktop-auth/start/', {
            'state': self.state, 'code_challenge': self.challenge,
        }, content_type='application/json', **headers)

    def login(self, client=None):
        client = client or self.client
        client.cookies['auth_token'] = LoginSession.issue(self.user).key
        return client

    def authorize(self):
        request_id = self.start().json()['request_id']
        self.login()
        response = self.client.post('/api/users/desktop-auth/confirm/', {'request': request_id, 'account_id': self.user.pk}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        query = parse_qs(urlsplit(response.json()['callback']).query)
        self.assertEqual(query['state'], [self.state])
        return request_id, query['code'][0]

    def exchange(self, code, verifier=None, client=None, **headers):
        return (client or self.client).post('/api/users/desktop-auth/exchange/', {
            'code': code, 'code_verifier': verifier or self.verifier,
        }, content_type='application/json', **headers)

    def test_success_cookie_token_preservation_duplicate_confirmation_and_replay(self):
        token = LoginSession.issue(self.user)
        self.client.cookies['auth_token'] = token.key
        request_id, code = self.authorize()
        native = Client(enforce_csrf_checks=True)
        response = self.exchange(code, client=native)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'ok': True})
        self.assertNotEqual(response.cookies['auth_token'].value, token.key)
        self.assertIsNotNone(LoginSession.resolve(response.cookies['auth_token'].value))
        self.assertTrue(response.cookies['auth_token']['httponly'])
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertIsNotNone(LoginSession.resolve(token.key))
        repeated = self.client.post('/api/users/desktop-auth/confirm/', {'request': request_id, 'account_id': self.user.pk}, content_type='application/json')
        self.assertEqual(repeated.status_code, 400)
        self.assertNotIn('auth_token', repeated.cookies)
        replay = self.exchange(code, client=native)
        self.assertEqual(replay.status_code, 400)
        self.assertNotIn('auth_token', replay.cookies)
        self.assertEqual(native.get('/api/users/me/').status_code, 200)
        self.assertEqual(native.post('/api/users/logout/').status_code, 403)
        self.assertEqual(native.post('/api/users/logout/',
            HTTP_X_CSRFTOKEN=native.cookies['csrftoken'].value,
            HTTP_ORIGIN='http://testserver').status_code, 200)
        self.assertEqual(self.client.get('/api/users/me/').status_code, 200)

    def test_wrong_verifier_does_not_consume_code(self):
        _, code = self.authorize()
        self.assertEqual(self.exchange(code, secrets.token_urlsafe(32)).status_code, 400)
        self.assertFalse(Token.objects.filter(user=self.user).exists())
        self.assertEqual(self.exchange(code).status_code, 200)

    def test_expired_request_and_code_are_rejected(self):
        request_id, code = self.authorize()
        record = cache.get('desktop_code:' + code)
        record['expires_at'] = 0
        cache.set('desktop_code:' + code, record)
        self.assertEqual(self.exchange(code).status_code, 400)
        ticket = cache.get('desktop_request:' + request_id)
        ticket['expires_at'] = 0
        cache.set('desktop_request:' + request_id, ticket)
        self.assertEqual(self.client.get('/api/users/desktop-auth/confirm/', {'request': request_id}).status_code, 400)
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    def test_revocation_inactive_and_current_permission_checked_at_exchange(self):
        for field, value in [('account_session_version', self.user.account_session_version + 1), ('is_active', False)]:
            with self.subTest(field=field):
                cache.clear()
                _, code = self.authorize()
                User.objects.filter(pk=self.user.pk).update(**{field: value})
                response = self.exchange(code)
                self.assertEqual(response.status_code, 400)
                self.assertNotIn('auth_token', response.cookies)
                User.objects.filter(pk=self.user.pk).update(**{field: getattr(self.user, field)})
        cache.clear()
        _, code = self.authorize()
        with patch('users.accounts.desktop.is_member_or_admin', return_value=False):
            self.assertEqual(self.exchange(code).status_code, 400)
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    def test_login_required_and_legacy_link_preserves_ticket_without_account_center(self):
        request_id = self.start().json()['request_id']
        response = self.client.get('/accounts/desktop/', {'request': request_id})
        self.assertEqual(response['Location'], 'http://testserver/desktop-auth?request=' + request_id)
        self.assertEqual(self.client.get('/api/users/desktop-auth/confirm/', {'request': request_id}).status_code, 401)
        # A Korson Django session alone cannot authorize UniMind App login.
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/api/users/desktop-auth/confirm/', {'request': request_id}).status_code, 401)

    @patch('ai_assistant.tasks.precompute_user_profile.delay')
    def test_web_password_login_continues_app_authorization(self, _precompute):
        self.user.set_password('Pass12345')
        self.user.save(update_fields=['password'])
        request_id = self.start().json()['request_id']
        response = self.client.post('/api/users/login/', {
            'username': self.user.email, 'password': 'Pass12345',
        }, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)
        response = self.client.post('/api/users/desktop-auth/confirm/', {
            'request': request_id, 'account_id': self.user.pk,
        }, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        code = parse_qs(urlsplit(response.json()['callback']).query)['code'][0]
        self.assertEqual(self.exchange(code, client=Client()).status_code, 200)

    def test_confirmation_requires_csrf(self):
        client = self.login(Client(enforce_csrf_checks=True))
        request_id = self.start(client).json()['request_id']
        url = '/api/users/desktop-auth/confirm/?request=' + request_id
        self.assertEqual(client.get(url)['Cache-Control'], 'no-store')
        self.assertEqual(client.post(url, {'request': request_id}).status_code, 403)
        data = {'request': request_id, 'account_id': self.user.pk, 'csrfmiddlewaretoken': client.cookies['csrftoken'].value}
        self.assertEqual(client.post(url, data, HTTP_ORIGIN='null').status_code, 403)
        self.assertEqual(client.post(url, data, HTTP_ORIGIN='https://evil.example').status_code, 403)
        response = client.post(url, data, HTTP_ORIGIN='http://testserver')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    def test_platform_cookie_restores_confirmation_without_authorizing(self):
        token = LoginSession.issue(self.user)
        self.client.cookies['auth_token'] = token.key
        request_id = self.start().json()['request_id']
        response = self.client.get('/api/users/desktop-auth/confirm/', {'request': request_id})
        self.assertContains(response, self.user.email)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertFalse(cache.get('desktop_confirmed:' + request_id))
        self.assertNotIn('callback', response.json())
        self.assertIsNotNone(LoginSession.resolve(token.key))
        self.assertNotIn('auth_token', response.cookies)

    def test_origin_host_json_and_size_boundaries(self):
        for headers in ({'HTTP_ORIGIN': 'https://evil.example'}, {'HTTP_ORIGIN': 'null'},
                        {'HTTP_HOST': 'localhost:9999'}, {'HTTP_SEC_FETCH_SITE': 'cross-site'}):
            with self.subTest(headers=headers):
                self.assertEqual(self.start(**headers).status_code, 403)
                self.assertEqual(self.exchange(secrets.token_urlsafe(32), **headers).status_code, 403)
        self.assertEqual(self.start(HTTP_ORIGIN='http://testserver').status_code, 200)
        self.assertEqual(self.client.post('/api/users/desktop-auth/start/', {'state': self.state}).status_code, 415)
        self.assertEqual(self.client.post('/api/users/desktop-auth/start/', 'x' * 1025, content_type='application/json').status_code, 413)
        self.assertEqual(self.client.post('/api/users/desktop-auth/start/', '[]', content_type='application/json').status_code, 400)

    def test_cache_failure_and_failed_atomic_consumption_never_set_cookie(self):
        _, code = self.authorize()
        with patch('users.accounts.desktop.cache.get', side_effect=ConnectionError):
            response = self.exchange(code)
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('auth_token', response.cookies)
        cache.add('desktop_used:' + code, True)
        response = self.exchange(code)
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('auth_token', response.cookies)
        self.assertFalse(Token.objects.filter(user=self.user).exists())
