from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token

from core.models import SecurityAuditLog
from users.accounts.services import authenticate_account, reset_account_password
from users.login_sessions import LoginSession
from users.models import User


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class Level2SmokeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='level2', email='level2@example.test',
                                             password='Pass12345', email_verified=True)

    def test_legacy_header_rejected_and_idle_session_cannot_revive(self):
        legacy = Token.objects.create(user=self.user)
        self.assertEqual(self.client.get('/api/users/me/', HTTP_AUTHORIZATION=f'Token {legacy.key}').status_code, 401)
        session = LoginSession.issue(self.user)
        self.client.cookies['auth_token'] = session.key
        self.assertEqual(self.client.get('/api/users/me/').status_code, 200)
        LoginSession.objects.filter(pk=session.pk).update(last_seen_at=timezone.now() - timedelta(minutes=31))
        self.assertEqual(self.client.get('/api/users/me/').status_code, 401)
        self.assertIsNone(LoginSession.resolve(session.key))

    def test_account_lockout_and_password_reset_are_audited(self):
        from django.test import RequestFactory
        request = RequestFactory().post('/accounts/login/', REMOTE_ADDR='127.0.0.1')
        request.request_id = 'level2-smoke'
        for _ in range(5):
            with self.assertRaises(ValidationError):
                authenticate_account(request, self.user.username, 'WrongPass123')
        self.assertEqual(SecurityAuditLog.objects.filter(event_type='login_failure').count(), 4)
        locked = SecurityAuditLog.objects.get(event_type='login_locked')
        self.assertEqual(locked.request_id, request.request_id)
        self.assertEqual(locked.ip_address, '127.0.0.1')
        with patch('users.accounts.services.consume_account_code'):
            reset_account_password(email=self.user.email, code='123456', password='NewPass12345', request=request)
        self.assertTrue(SecurityAuditLog.objects.filter(event_type='password_change', user=self.user).exists())
        self.assertFalse(SecurityAuditLog.objects.filter(detail__contains='123456').exists())
        self.assertEqual(authenticate_account(request, self.user.username, 'NewPass12345').pk, self.user.pk)
        self.assertTrue(SecurityAuditLog.objects.filter(event_type='login_success', user=self.user).exists())

    def test_django_admin_uses_the_same_lockout(self):
        self.user.is_staff = True
        self.user.save(update_fields=['is_staff'])
        for _ in range(5):
            self.client.post('/admin/login/', {'username': self.user.username, 'password': 'WrongPass123', 'next': '/admin/'})
        self.user.refresh_from_db()
        self.assertGreater(self.user.locked_until, timezone.now())
        self.assertEqual(self.client.post('/admin/login/', {'username': self.user.username, 'password': 'Pass12345', 'next': '/admin/'}).status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)


from django.test import SimpleTestCase


class WebsocketSessionSmokeTests(SimpleTestCase):
    async def test_revoked_session_closes_before_delivering_next_message(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        from core.ws_auth import TokenAuthMiddleware

        delivered = []
        async def consumer(scope, receive, send):
            delivered.append(await receive())
            await send({'type': 'websocket.accept'})
            delivered.append(await receive())
        receive = AsyncMock(side_effect=[{'type': 'websocket.connect'}, {'type': 'websocket.receive', 'text': 'private'}])
        send = AsyncMock()
        with patch('core.ws_auth.get_user_from_token', new=AsyncMock(side_effect=[SimpleNamespace(is_authenticated=True), None])):
            await TokenAuthMiddleware(consumer)({'cookies': {'auth_token': 'smoke'}}, receive, send)
        self.assertEqual(delivered[-1], {'type': 'websocket.disconnect', 'code': 4001})
        send.assert_any_await({'type': 'websocket.close', 'code': 4001})
