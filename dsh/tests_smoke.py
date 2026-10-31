"""Small, offline checks for the three concrete review findings."""
import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.request import Request

import host
import smoke


class HostBoundarySmoke(unittest.TestCase):
    def test_error_response_does_not_include_token(self):
        handler = object.__new__(host.Handler)
        handler.path = '/context'
        handler.headers = {'Content-Type': 'application/json', 'Content-Length': '2'}
        handler.rfile = io.BytesIO(b'{}')
        result = []
        handler.reply = lambda status, body: result.append((status, body))
        with patch('host.backend_request', side_effect=ValueError('Token SYNTHETIC_SECRET\n')):
            handler.do_POST()
        self.assertNotIn('SYNTHETIC_SECRET', json.dumps(result))

    def test_backend_redirect_is_not_followed(self):
        request = Request('http://127.0.0.1/source', headers={'Authorization': 'Token SYNTHETIC_SECRET'})
        self.assertIsNone(host.NoRedirect().redirect_request(request, None, 302, 'Found', {}, 'http://example.invalid/collect'))

    def test_fixture_refuses_unscoped_database(self):
        with patch.dict(os.environ, {'DB_NAME': '/tmp/not-a-fixture.sqlite3'}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'isolated fixture'):
                smoke.fixture_database()


if __name__ == '__main__':
    unittest.main()
