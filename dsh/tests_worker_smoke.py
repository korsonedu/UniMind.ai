"""Offline checks of the worker's actual stdin/stdout error boundary."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import host


class WorkerHttpErrorSmoke(unittest.TestCase):
    def response(self, status, body):
        error = HTTPError('http://127.0.0.1/api/ai/dsh/context/', status,
                          'SYNTHETIC_SECRET', {}, io.BytesIO(body))
        payload = {'api_url': 'http://127.0.0.1', 'token': 'SYNTHETIC_TOKEN', 'state_dir': '/unused'}
        output = io.StringIO()
        with patch.object(host, 'backend_request', side_effect=error), \
                patch('sys.stdin', io.StringIO(json.dumps(payload))), \
                patch.dict('os.environ', {}, clear=True), redirect_stdout(output):
            runpy.run_path(str(Path(__file__).with_name('worker.py')), run_name='__main__')
        result = json.loads(output.getvalue())
        self.assertNotIn('SYNTHETIC_SECRET', output.getvalue())
        self.assertNotIn('SYNTHETIC_TOKEN', output.getvalue())
        return result

    def test_callback_client_status_and_controlled_text(self):
        for status, expected in ((400, 503), (403, 403), (404, 404), (409, 409), (429, 429)):
            for field in ('detail', 'error'):
                with self.subTest(status=status, field=field):
                    body = json.dumps({field: '内容访问范围尚未配置，请联系管理员。',
                                       'traceback': 'SYNTHETIC_SECRET'}).encode()
                    self.assertEqual(self.response(status, body), {
                        'status': expected, 'error': '内容访问范围尚未配置，请联系管理员。'})

    def test_unsafe_or_missing_body_uses_fixed_message(self):
        for body in (
            b'<html>SYNTHETIC_SECRET traceback</html>', b'not json', b'', b'[]',
            b'{"traceback": "SYNTHETIC_SECRET"}', b'{"detail": {"secret": "SYNTHETIC_SECRET"}}',
            b'{"error": ["SYNTHETIC_SECRET"]}', b'{"detail": "   "}',
            b'{"detail": "<html>SYNTHETIC_SECRET</html>"}',
            b'{"detail": "Traceback (most recent call last): SYNTHETIC_SECRET"}',
            b'{"detail": "line one\\nSYNTHETIC_SECRET"}',
            json.dumps({'detail': '长' * 301}).encode(),
            b'{"detail": "' + b'x' * 8192 + b'"}',
        ):
            with self.subTest(body=body[:60]):
                self.assertEqual(self.response(403, body), {
                    'status': 403, 'error': 'DSH 服务暂不可用，请稍后重试。'})

    def test_unexpected_status_does_not_forward_server_details(self):
        for status in (401, 500, 502, 503):
            with self.subTest(status=status):
                self.assertEqual(self.response(status, b'{"detail": "SYNTHETIC_SECRET"}'), {
                    'status': 503, 'error': 'DSH 服务暂不可用，请稍后重试。'})


if __name__ == '__main__':
    unittest.main()
