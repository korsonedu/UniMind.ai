from urllib.parse import parse_qs, urlencode, urlsplit
import secrets

from django.contrib.sessions.backends.db import SessionStore
from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from users.login_sessions import LoginSession
from users.models import User


@override_settings(
    ACCOUNT_ENABLED=True,
    ACCOUNT_CENTER_ORIGIN='http://testserver',
    ACCOUNT_UNIMIND_ORIGIN='http://testserver',
    ACCOUNT_WEBSITE_ORIGINS=['http://testserver'],
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class WebsiteEntrySmokeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='website-entry', password='Pass12345')
        session = SessionStore()
        session.update({
            '_auth_user_id': str(self.user.pk), '_auth_user_backend': 'django.contrib.auth.backends.ModelBackend',
            '_auth_user_hash': self.user.get_session_auth_hash(), 'account_user_id': self.user.pk,
            'account_session_version': self.user.account_session_version, 'account_audience': 'website',
        })
        session.save()
        self.client.cookies['korson_account_session'] = session.session_key

    def handoff(self):
        response = self.client.get('/account-api/center/unimind/')
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('/accounts/login/', response['Location'])
        started = self.client.get(response['Location'])
        self.assertEqual(started.status_code, 302)
        authorized = self.client.get(started['Location'])
        self.assertEqual(authorized.status_code, 302)
        return authorized['Location']

    def test_website_session_alone_enters_unimind_without_login_or_card(self):
        response = self.client.get(self.handoff())
        self.assertEqual(response['Location'], 'http://testserver/account-callback')
        self.assertEqual(LoginSession.resolve(response.cookies['auth_token'].value).user_id, self.user.pk)
        self.assertEqual(self.client.get('/account-api/session/').json()['user']['id'], self.user.pk)

    def test_same_account_reuses_target_session_and_single_use_code(self):
        token = LoginSession.issue(self.user)
        self.client.cookies['auth_token'] = token.key
        callback = self.handoff()
        response = self.client.get(callback)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('auth_token', response.cookies)
        self.assertEqual(LoginSession.objects.count(), 1)
        self.assertEqual(self.client.get(callback).status_code, 400)

    def test_handoff_cannot_be_replayed_in_another_browser_or_after_revocation(self):
        callback = self.handoff()
        self.assertEqual(Client().get(callback).status_code, 400)
        self.user.set_password('FreshPass12345')
        self.user.save(update_fields=['password'])
        self.assertEqual(self.client.get(callback).status_code, 400)
        self.assertFalse(LoginSession.objects.exists())

    def test_conflict_requires_explicit_choice_and_does_not_loop(self):
        other = User.objects.create_user(username='other-entry')
        token = LoginSession.issue(other)
        self.client.cookies['auth_token'] = token.key
        callback = self.handoff()
        response = self.client.get(callback)
        self.assertContains(response, '请选择')
        self.assertNotIn('auth_token', response.cookies)
        data = {key: value[0] for key, value in parse_qs(urlsplit(callback).query).items()}
        response = self.client.post(callback, {**data, 'selection': 'website', 'account_id': self.user.pk, 'platform_id': other.pk})
        self.assertEqual(response['Location'], 'http://testserver/account-callback')
        self.assertEqual(LoginSession.resolve(response.cookies['auth_token'].value).user_id, self.user.pk)
        self.assertIsNotNone(LoginSession.resolve(token.key))

    def test_keep_target_account_requires_csrf_and_preserves_website_account(self):
        secure = Client(enforce_csrf_checks=True)
        secure.cookies = self.client.cookies
        self.client = secure
        other = User.objects.create_user(username='keep-entry')
        token = LoginSession.issue(other)
        self.client.cookies['auth_token'] = token.key
        callback = self.handoff()
        self.assertEqual(self.client.get(callback).status_code, 200)
        data = {key: value[0] for key, value in parse_qs(urlsplit(callback).query).items()}
        data.update({'selection': 'platform', 'account_id': self.user.pk, 'platform_id': other.pk})
        self.assertEqual(self.client.post(callback, data).status_code, 403)
        data['csrfmiddlewaretoken'] = self.client.cookies['csrftoken'].value
        response = self.client.post(callback, data)
        self.assertEqual(response['Location'], 'http://testserver/account-callback')
        self.assertNotIn('auth_token', response.cookies)
        self.assertEqual(self.client.get('/account-api/session/').json()['user']['id'], self.user.pk)
        self.assertIsNotNone(LoginSession.resolve(token.key))

    def test_source_logout_tampering_and_expired_code_cannot_authorize(self):
        callback = self.handoff()
        query = {key: value[0] for key, value in parse_qs(urlsplit(callback).query).items()}
        bad = '/accounts/unimind/?' + urlencode({**query, 'entry_state': secrets.token_urlsafe(32)})
        self.assertEqual(self.client.get(bad).status_code, 400)
        grant = cache.get('unimind_entry:' + query['code'])
        grant['expires_at'] = 0
        cache.set('unimind_entry:' + query['code'], grant)
        self.assertEqual(self.client.get(callback).status_code, 400)
        callback = self.handoff()
        self.client.post('/account-api/logout/')
        self.assertEqual(self.client.get(callback).status_code, 400)
        self.assertFalse(LoginSession.objects.exists())

    def test_website_identity_does_not_depend_on_the_center_cookie(self):
        other = User.objects.create_user(username='center-entry', password='OtherPass12345')
        self.client.post('/accounts/login/', {'identifier': other.username, 'password': 'OtherPass12345'})
        response = self.client.get(self.handoff())
        self.assertEqual(LoginSession.resolve(response.cookies['auth_token'].value).user_id, self.user.pk)
        self.assertEqual(int(self.client.session['_auth_user_id']), other.pk)

    def test_guest_website_uses_target_login_and_website_logout_stays_signed_out(self):
        token = LoginSession.issue(self.user)
        self.client.cookies['auth_token'] = token.key
        self.client.post('/account-api/logout/')
        response = self.client.get('/account-api/center/unimind/')
        self.assertEqual(response['Location'], 'http://testserver/xiaoyu')
        self.assertIsNone(self.client.get('/account-api/session/').json()['user'])
        self.assertIsNotNone(LoginSession.resolve(token.key))

    @override_settings(
        ACCOUNT_CENTER_ORIGIN='https://unimind.example', ACCOUNT_UNIMIND_ORIGIN='https://unimind.example',
        ACCOUNT_WEBSITE_ORIGINS=['https://korson.example'], ALLOWED_HOSTS=['unimind.example', 'korson.example'],
    )
    def test_cross_domain_handoff_preserves_source_session(self):
        url = 'https://korson.example/account-api/center/unimind/'
        for _ in range(4):
            response = self.client.get(url, secure=True, HTTP_HOST=urlsplit(url).netloc)
            self.assertEqual(response.status_code, 302)
            url = response['Location']
            self.assertNotIn('/accounts/login/', url)
        self.assertEqual(url, 'https://unimind.example/account-callback')
        self.assertIsNotNone(LoginSession.resolve(response.cookies['auth_token'].value))
        source = self.client.get('/account-api/session/', secure=True, HTTP_HOST='korson.example')
        self.assertEqual(source.json()['user']['id'], self.user.pk)
