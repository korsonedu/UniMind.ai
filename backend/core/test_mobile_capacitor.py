"""Native header authentication, single-use WS tickets and password rotation."""
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from django.core.cache import cache
from django.core.cache.backends.locmem import LocMemCache
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient

from core.ws_auth import (
    WS_TICKET_CACHE_PREFIX, consume_ws_ticket, issue_ws_ticket,
    TokenAuthMiddleware, _extract_ticket_from_scope,
)
from users.login_sessions import LoginSession
from users.models import User


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class NativeTicketTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='native', password='OldPass12345')
        self.session = LoginSession.issue(self.user)
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.session.key}')

    def test_header_issue_and_one_time_consume(self):
        response = self.client.post('/api/ws-ticket/', {}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {'ticket', 'expires_in'})
        self.assertEqual(response.json()['expires_in'], 30)
        self.assertEqual(response['Cache-Control'], 'no-store')
        ticket = response.json()['ticket']
        user, key = consume_ws_ticket.func(ticket)
        self.assertEqual((user.pk, key), (self.user.pk, self.session.key))
        self.assertEqual(consume_ws_ticket.func(ticket), (None, ''))

    def test_anonymous_legacy_token_and_cookie_without_csrf_rejected(self):
        from rest_framework.authtoken.models import Token
        self.client.credentials()
        self.assertEqual(self.client.post('/api/ws-ticket/').status_code, 401)
        legacy = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {legacy.key}')
        self.assertEqual(self.client.post('/api/ws-ticket/').status_code, 401)
        self.client.credentials()
        self.client.cookies['auth_token'] = self.session.key
        self.assertEqual(self.client.post('/api/ws-ticket/').status_code, 403)

    def test_expired_and_malformed_tickets(self):
        for ticket in ('', 'bad', 'x' * 129, 'a/b' * 10):
            self.assertEqual(consume_ws_ticket.func(ticket), (None, ''))
        ticket = issue_ws_ticket(self.user, self.session)
        key = WS_TICKET_CACHE_PREFIX + ticket
        payload = cache.get(key)
        payload['expires_at'] = time.time() - 1
        cache.set(key, payload, 30)
        self.assertEqual(consume_ws_ticket.func(ticket), (None, ''))
        ticket = issue_ws_ticket(self.user, self.session)
        cache.delete(WS_TICKET_CACHE_PREFIX + ticket)
        self.assertEqual(consume_ws_ticket.func(ticket), (None, ''))

    def test_session_expiry_idle_revocation_and_inactive_user(self):
        for change in ('expired', 'idle', 'deleted', 'inactive', 'version'):
            with self.subTest(change=change):
                self.user.refresh_from_db()
                self.user.is_active = True
                self.user.save(update_fields=['is_active'])
                session = LoginSession.issue(self.user)
                ticket = issue_ws_ticket(self.user, session)
                if change == 'expired':
                    LoginSession.objects.filter(pk=session.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
                elif change == 'idle':
                    LoginSession.objects.filter(pk=session.pk).update(last_seen_at=timezone.now() - timedelta(days=2))
                elif change == 'deleted':
                    session.delete()
                elif change == 'inactive':
                    User.objects.filter(pk=self.user.pk).update(is_active=False)
                else:
                    User.objects.filter(pk=self.user.pk).update(account_session_version=self.user.account_session_version + 1)
                self.assertEqual(consume_ws_ticket.func(ticket), (None, ''))
                with self.assertRaises(AuthenticationFailed):
                    issue_ws_ticket(self.user, session)

    def test_cannot_issue_for_another_user_or_without_session(self):
        other = User.objects.create_user(username='other-native')
        for auth in (None, LoginSession.issue(other)):
            with self.assertRaises(AuthenticationFailed):
                issue_ws_ticket(self.user, auth)

    def test_password_rotates_all_sessions_and_outstanding_tickets(self):
        other_session = LoginSession.issue(self.user)
        ticket = issue_ws_ticket(self.user, self.session)
        response = self.client.patch('/api/users/me/password/', {
            'old_password': 'OldPass12345', 'new_password': 'NewPass12345',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {'status', 'token'})
        self.assertEqual(response.json()['status'], 'ok')
        self.assertEqual(response['Cache-Control'], 'no-store')
        new_key = response.json()['token']
        self.assertEqual(response.cookies['auth_token'].value, new_key)
        self.assertIsNone(LoginSession.resolve(self.session.key))
        self.assertIsNone(LoginSession.resolve(other_session.key))
        self.assertEqual(consume_ws_ticket.func(ticket), (None, ''))
        self.assertEqual(LoginSession.resolve(new_key).user_id, self.user.pk)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewPass12345'))
        self.client.cookies.clear()
        self.assertEqual(self.client.get('/api/users/me/').status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {new_key}')
        self.assertEqual(self.client.get('/api/users/me/').status_code, 200)


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class TicketConcurrencyTests(SimpleTestCase):
    def test_simultaneous_reads_only_one_delete_wins(self):
        ticket = 'a' * 43
        key = WS_TICKET_CACHE_PREFIX + ticket
        cache.set(key, {'user_id': 1, 'session_key': 'session', 'expires_at': time.time() + 30}, 30)
        barrier = Barrier(16)
        original_get = LocMemCache.get

        def simultaneous_get(backend, *args, **kwargs):
            payload = original_get(backend, *args, **kwargs)
            barrier.wait(timeout=10)
            return payload

        session = SimpleNamespace(user_id=1, user=object())
        with patch.object(LocMemCache, 'get', new=simultaneous_get), \
                patch.object(LoginSession, 'resolve', return_value=session):
            with ThreadPoolExecutor(max_workers=16) as executor:
                results = list(executor.map(consume_ws_ticket.func, [ticket] * 16))
        self.assertEqual(sum(user is not None for user, _ in results), 1)

    def test_cache_failure_denies_consumption(self):
        with patch('core.ws_auth.cache.get', side_effect=ConnectionError):
            self.assertEqual(consume_ws_ticket.func('a' * 43), (None, ''))


class NativeMiddlewareTests(SimpleTestCase):
    async def test_ticket_authenticates_and_revocation_closes_connection(self):
        delivered = []
        user = SimpleNamespace(is_authenticated=True)

        async def consumer(scope, receive, send):
            self.assertIs(scope['user'], user)
            delivered.append(await receive())
            delivered.append(await receive())

        receive = AsyncMock(side_effect=[{'type': 'websocket.connect'}, {'type': 'websocket.receive', 'text': 'private'}])
        send = AsyncMock()
        with patch('core.ws_auth.consume_ws_ticket', new=AsyncMock(return_value=(user, 'session'))) as consume, \
                patch('core.ws_auth.get_user_from_token', new=AsyncMock(return_value=None)):
            await TokenAuthMiddleware(consumer)({'query_string': b'ticket=example'}, receive, send)
        consume.assert_awaited_once_with('example')
        self.assertEqual(delivered[-1], {'type': 'websocket.disconnect', 'code': 4001})
        send.assert_awaited_once_with({'type': 'websocket.close', 'code': 4001})

    async def test_invalid_ticket_is_anonymous_and_cookie_takes_precedence(self):
        seen = []

        async def consumer(scope, receive, send):
            seen.append(scope['user'].is_authenticated)

        with patch('core.ws_auth.consume_ws_ticket', new=AsyncMock(return_value=(None, ''))) as consume:
            await TokenAuthMiddleware(consumer)({'query_string': b'ticket=invalid'}, AsyncMock(), AsyncMock())
            self.assertEqual(seen, [False])
            consume.assert_awaited_once()
        with patch('core.ws_auth.consume_ws_ticket', new=AsyncMock()) as consume, \
                patch('core.ws_auth.get_user_from_token', new=AsyncMock(return_value=SimpleNamespace(is_authenticated=True))):
            await TokenAuthMiddleware(consumer)({'cookies': {'auth_token': 'cookie'}, 'query_string': b'ticket=ignored'}, AsyncMock(), AsyncMock())
            consume.assert_not_awaited()
        self.assertEqual(seen, [False, True])

    def test_duplicate_query_ticket_rejected(self):
        self.assertEqual(_extract_ticket_from_scope({'query_string': b'ticket=a&ticket=b'}), '')
        self.assertEqual(_extract_ticket_from_scope({'query_string': b'ticket=a&ticket='}), '')
