from datetime import timedelta
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token

from users.login_sessions import LoginSession
from users.models import User


@override_settings(
    ACCOUNT_ENABLED=True,
    ACCOUNT_CENTER_ORIGIN='http://testserver',
    ACCOUNT_WEBSITE_ORIGINS=['http://testserver'],
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class LoginSessionSmokeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='session-user', email='session@example.test', password='Pass12345')

    def test_two_password_logins_and_logout_are_independent(self):
        browser, desktop = Client(), Client()
        with patch('ai_assistant.tasks.precompute_user_profile.delay'):
            for client in (browser, desktop):
                response = client.post('/api/users/login/', {'username': self.user.username, 'password': 'Pass12345'})
                self.assertEqual(response.status_code, 200)
        browser_key, desktop_key = [client.cookies['auth_token'].value for client in (browser, desktop)]
        self.assertNotEqual(browser_key, desktop_key)
        self.assertEqual(browser.get('/api/users/me/').status_code, 200)
        self.assertEqual(desktop.post('/api/users/logout/').status_code, 200)
        self.assertIsNone(LoginSession.resolve(desktop_key))
        self.assertEqual(desktop.get('/api/users/me/').status_code, 401)
        self.assertEqual(browser.get('/api/users/me/').status_code, 200)

    def test_expiry_password_change_and_legacy_cookie_require_login(self):
        for token in (Token.objects.create(user=self.user), LoginSession.issue(self.user)):
            self.client.cookies['auth_token'] = token.key
            if isinstance(token, LoginSession):
                LoginSession.objects.filter(pk=token.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
            self.assertEqual(self.client.get('/api/users/me/').status_code, 401)
        token = LoginSession.issue(self.user)
        self.user.set_password('FreshPass12345')
        self.user.save(update_fields=['password'])
        self.assertIsNone(LoginSession.resolve(token.key))

    def test_website_logout_and_platform_logout_do_not_restore_each_other(self):
        token = LoginSession.issue(self.user)
        self.client.cookies['auth_token'] = token.key
        website = Client()
        website.force_login(self.user)
        session = website.session
        session.update({'account_user_id': self.user.pk, 'account_session_version': self.user.account_session_version, 'account_audience': 'website'})
        session.save()
        website.cookies['korson_account_session'] = session.session_key
        self.assertEqual(website.post('/account-api/logout/').status_code, 200)
        self.assertEqual(self.client.get('/api/users/me/').status_code, 200)
        self.assertEqual(self.client.post('/api/users/logout/').status_code, 200)
        self.assertIsNone(website.get('/account-api/session/').json()['user'])

    def test_remembered_card_requires_click_and_csrf_then_only_creates_platform_session(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.user)
        session = browser.session
        session.update({'account_user_id': self.user.pk, 'account_session_version': self.user.account_session_version, 'account_audience': 'account'})
        session.save()
        response = browser.get('/accounts/login/?next=/accounts/unimind/')
        self.assertContains(response, 'account-card')
        self.assertFalse(LoginSession.objects.exists())
        self.assertIsNone(browser.get('/account-api/session/').json()['user'])
        self.assertEqual(browser.post('/accounts/unimind/').status_code, 403)
        data = {'csrfmiddlewaretoken': browser.cookies['csrftoken'].value, 'next': '/courses', 'account_id': self.user.pk}
        self.assertEqual(browser.post('/accounts/unimind/', {**data, 'account_id': 0}).status_code, 400)
        response = browser.post('/accounts/unimind/', data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].endswith('/account-callback?next=%2Fcourses'))
        self.assertIsNotNone(LoginSession.resolve(response.cookies['auth_token'].value))
        self.assertIsNone(browser.get('/account-api/session/').json()['user'])
