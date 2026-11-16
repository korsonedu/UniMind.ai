"""Capacitor development origins and production configuration gates."""
import os
import runpy
from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.parse import urlparse

from channels.testing import WebsocketCommunicator
from corsheaders.middleware import CorsMiddleware
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from school_system.asgi import ConfiguredOriginValidator


class MobileOriginTests(SimpleTestCase):
    @override_settings(
        DEBUG=True, IS_PROD=False, ALLOWED_HOSTS=['localhost', '192.168.1.23'],
        WS_ALLOWED_ORIGINS=['http://localhost', 'https://localhost', 'capacitor://localhost'],
    )
    @patch('channels.consumer.aclose_old_connections', new_callable=AsyncMock)
    @patch('channels.generic.websocket.aclose_old_connections', new_callable=AsyncMock)
    async def test_websocket_handshake_enforces_origin(self, _disconnect_cleanup, _close_connections):
        async def accept(scope, receive, send):
            await receive()
            await send({'type': 'websocket.accept'})
            await receive()

        for origin, expected in (
            ('http://localhost', True), ('https://localhost', True),
            ('capacitor://localhost', True), ('http://192.168.1.23:8000', True),
            ('https://attacker.invalid', False), ('http://localhost.attacker.invalid', False),
            (None, False),
        ):
            with self.subTest(origin=origin):
                headers = [(b'origin', origin.encode())] if origin else []
                communicator = WebsocketCommunicator(ConfiguredOriginValidator(accept), '/', headers=headers)
                connected, _ = await communicator.connect(timeout=10)
                self.assertEqual(connected, expected)
                await communicator.disconnect(timeout=10)

    @override_settings(DEBUG=True, IS_PROD=False, ALLOWED_HOSTS=['*'],
                       WS_ALLOWED_ORIGINS=['capacitor://localhost'])
    def test_http_development_wildcard_does_not_open_websocket_origins(self):
        validator = ConfiguredOriginValidator(None)
        self.assertTrue(validator.valid_origin(urlparse('capacitor://localhost')))
        self.assertFalse(validator.valid_origin(urlparse('https://attacker.invalid')))
        self.assertFalse(validator.valid_origin(None))

    @override_settings(DEBUG=False, IS_PROD=True, ALLOWED_HOSTS=['unimind.example'],
                       WS_ALLOWED_ORIGINS=[])
    def test_production_does_not_implicitly_allow_capacitor(self):
        validator = ConfiguredOriginValidator(None)
        self.assertTrue(validator.valid_origin(urlparse('https://unimind.example')))
        for origin in ('http://localhost', 'https://localhost', 'capacitor://localhost'):
            self.assertFalse(validator.valid_origin(urlparse(origin)))

    @override_settings(
        CORS_ALLOW_ALL_ORIGINS=False, CORS_ALLOWED_ORIGINS=['capacitor://localhost'],
        CORS_ALLOWED_ORIGIN_REGEXES=[], CORS_ALLOW_PRIVATE_NETWORK=True,
    )
    def test_installed_cors_middleware_allows_private_network_only_for_allowed_origin(self):
        middleware = CorsMiddleware(lambda request: HttpResponse())
        for origin, allowed in (('capacitor://localhost', True), ('https://attacker.invalid', False)):
            with self.subTest(origin=origin):
                request = RequestFactory().options(
                    '/api/ws-ticket/', HTTP_ORIGIN=origin,
                    HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST',
                    HTTP_ACCESS_CONTROL_REQUEST_PRIVATE_NETWORK='true',
                )
                response = middleware(request)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get('Access-Control-Allow-Private-Network'), 'true' if allowed else None)
                self.assertEqual(response.get('Access-Control-Allow-Origin'), origin if allowed else None)


class MobileSettingsTests(SimpleTestCase):
    def load_settings(self, **environment):
        path = Path(__file__).resolve().parents[1] / 'school_system' / 'settings.py'
        with patch.dict(os.environ, environment, clear=True), patch('dotenv.load_dotenv'):
            return runpy.run_path(str(path))

    def production(self, **environment):
        return self.load_settings(DJANGO_ENV='production', SECRET_KEY='test-production-secret',
                                  **{'ALLOWED_HOSTS': 'unimind.example', **environment})

    def test_production_defaults_are_closed_and_development_host_switch_is_ignored(self):
        config = self.production(DEV_ALLOW_ALL_HOSTS='true')
        self.assertEqual(config['ALLOWED_HOSTS'], ['unimind.example'])
        self.assertFalse(config['CORS_ALLOW_ALL_ORIGINS'])
        self.assertFalse(config['CORS_ALLOW_PRIVATE_NETWORK'])
        self.assertFalse(config['CORS_ALLOW_CAPACITOR_ORIGINS'])
        self.assertEqual(config['CORS_ALLOWED_ORIGINS'], [])
        self.assertEqual(config['CSRF_TRUSTED_ORIGINS'], [])
        self.assertEqual(config['WS_ALLOWED_ORIGINS'], [])

    def test_production_rejects_debug_empty_hosts_and_open_cors(self):
        for environment, message in (
            ({'DEBUG': 'true'}, 'DEBUG must be False'),
            ({'ALLOWED_HOSTS': ''}, 'ALLOWED_HOSTS must be configured'),
            ({'CORS_ALLOW_ALL_ORIGINS': 'true'}, 'CORS_ALLOW_ALL_ORIGINS must be False'),
        ):
            with self.subTest(environment=environment), self.assertRaisesMessage(ImproperlyConfigured, message):
                self.production(**environment)

    def test_production_capacitor_requires_explicit_opt_in(self):
        config = self.production(CORS_ALLOW_CAPACITOR_ORIGINS='true')
        self.assertEqual(config['CORS_ALLOWED_ORIGINS'], config['CAPACITOR_ALLOWED_ORIGINS'])
        self.assertEqual(config['WS_ALLOWED_ORIGINS'], config['CAPACITOR_ALLOWED_ORIGINS'])
        self.assertEqual(config['CSRF_TRUSTED_ORIGINS'], [])
        self.assertFalse(config['CORS_ALLOW_ALL_ORIGINS'])

    def test_development_capacitor_and_lan_configuration(self):
        config = self.load_settings(DEBUG='true', ALLOWED_HOSTS='localhost,192.168.1.23',
                                    CORS_ALLOW_ALL_ORIGINS='false')
        self.assertEqual(config['ALLOWED_HOSTS'], ['localhost', '192.168.1.23'])
        self.assertTrue(config['CORS_ALLOW_PRIVATE_NETWORK'])
        for origin in config['CAPACITOR_ALLOWED_ORIGINS']:
            self.assertIn(origin, config['CORS_ALLOWED_ORIGINS'])
            self.assertIn(origin, config['WS_ALLOWED_ORIGINS'])
        config = self.load_settings(DEBUG='true', DEV_ALLOW_ALL_HOSTS='true')
        self.assertEqual(config['ALLOWED_HOSTS'], ['*'])
