import base64
import hashlib
import secrets
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from rest_framework.authtoken.models import Token

from users.models import User


@override_settings(
    ACCOUNT_ENABLED=True,
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
        client.force_login(self.user)
        session = client.session
        session.update({'account_user_id': self.user.pk, 'account_session_version': self.user.account_session_version,
                        'account_audience': 'account'})
        session.save()
        return client

    def authorize(self):
        request_id = self.start().json()['request_id']
        self.login()
        response = self.client.post('/accounts/desktop/', {'request': request_id})
        self.assertEqual(response.status_code, 200)
        query = parse_qs(urlsplit(response.context['callback']).query)
        self.assertEqual(query['state'], [self.state])
        return request_id, query['code'][0]

    def exchange(self, code, verifier=None, client=None, **headers):
        return (client or self.client).post('/api/users/desktop-auth/exchange/', {
            'code': code, 'code_verifier': verifier or self.verifier,
        }, content_type='application/json', **headers)

    def test_success_cookie_token_preservation_duplicate_confirmation_and_replay(self):
        token = Token.objects.create(user=self.user)
        request_id, code = self.authorize()
        native = Client(enforce_csrf_checks=True)
        response = self.exchange(code, client=native)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'ok': True})
        self.assertEqual(response.cookies['auth_token'].value, token.key)
        self.assertTrue(response.cookies['auth_token']['httponly'])
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertEqual(Token.objects.get(user=self.user).key, token.key)
        repeated = self.client.post('/accounts/desktop/', {'request': request_id})
        self.assertEqual(repeated.status_code, 400)
        self.assertNotIn('auth_token', repeated.cookies)
        replay = self.exchange(code, client=native)
        self.assertEqual(replay.status_code, 400)
        self.assertNotIn('auth_token', replay.cookies)

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
        self.assertEqual(self.client.get('/accounts/desktop/', {'request': request_id}).status_code, 400)
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

    def test_login_round_trip_preserves_ticket_and_get_does_not_authorize(self):
        request_id = self.start().json()['request_id']
        response = self.client.get('/accounts/desktop/', {'request': request_id})
        target = parse_qs(urlsplit(response['Location']).query)['next'][0]
        self.assertEqual(target, '/accounts/desktop/?request=' + request_id)
        login = self.client.get(response['Location'])
        self.assertEqual(login.context['next_path'], target)
        self.login()
        response = self.client.get(target)
        self.assertContains(response, self.user.email)
        self.assertFalse(cache.get('desktop_confirmed:' + request_id))
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    def test_confirmation_requires_csrf(self):
        client = self.login(Client(enforce_csrf_checks=True))
        request_id = self.start(client).json()['request_id']
        url = '/accounts/desktop/?request=' + request_id
        self.assertEqual(client.get(url)['Referrer-Policy'], 'same-origin')
        self.assertEqual(client.post(url, {'request': request_id}).status_code, 403)
        data = {'request': request_id, 'csrfmiddlewaretoken': client.cookies['csrftoken'].value}
        self.assertEqual(client.post(url, data, HTTP_ORIGIN='null').status_code, 403)
        self.assertEqual(client.post(url, data, HTTP_ORIGIN='https://evil.example').status_code, 403)
        response = client.post(url, data, HTTP_ORIGIN='http://testserver')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    def test_platform_cookie_restores_confirmation_without_authorizing(self):
        token = Token.objects.create(user=self.user)
        self.client.cookies['auth_token'] = token.key
        request_id = self.start().json()['request_id']
        response = self.client.get('/accounts/desktop/', {'request': request_id})
        self.assertContains(response, self.user.email)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)
        self.assertFalse(cache.get('desktop_confirmed:' + request_id))
        self.assertNotIn('callback', response.context)
        self.assertEqual(Token.objects.get(user=self.user).key, token.key)
        self.assertNotIn('auth_token', response.cookies)

    def test_disabled_origin_host_json_and_size_boundaries(self):
        with self.settings(ACCOUNT_ENABLED=False):
            self.assertEqual(self.start().status_code, 503)
            self.assertEqual(self.exchange(secrets.token_urlsafe(32)).status_code, 503)
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
