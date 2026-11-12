"""Local socket-pair smoke: sustained bytes must not renew the HTTP deadline."""
import http.client
import socket
from contextlib import contextmanager
from threading import Event, Thread
from time import monotonic
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError
from ai_assistant.services.learning_resources import find_resources, public_text


class LearningResourceDeadlineSmoke(SimpleTestCase):
    @contextmanager
    def transport(self, handlers, budget=.25):
        stopped = Event()
        pairs = []
        handlers = iter(handlers)

        def create_connection(address, timeout, source_address=None):
            self.assertEqual(address, ('1.1.1.1', 443))
            client, peer = socket.socketpair()
            client.settimeout(timeout)
            pairs.append((client, peer))
            handler = next(handlers)

            def serve():
                try:
                    request = b''
                    while b'\r\n\r\n' not in request:
                        chunk = peer.recv(4096)
                        if not chunk:
                            return
                        request += chunk
                    handler(peer, stopped)
                except OSError:
                    pass  # Deadline shutdown intentionally interrupts the sender.
                finally:
                    peer.close()

            Thread(target=serve, daemon=True).start()
            return client

        class LocalConnection(http.client.HTTPConnection):
            def connect(self):
                # socketpair has no TCP_NODELAY; retain the real HTTP parser.
                self.sock = self._create_connection((self.host, self.port), self.timeout, self.source_address)

        def connection(host, timeout, context):
            self.assertEqual(host, 'example.org')
            return LocalConnection(host, timeout=timeout)

        addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('1.1.1.1', 443))]
        with patch('ai_assistant.services.learning_resources.PUBLIC_TEXT_TIMEOUT', budget), \
                patch('socket.getaddrinfo', return_value=addresses), \
                patch('socket.create_connection', side_effect=create_connection), \
                patch('http.client.HTTPSConnection', side_effect=connection):
            try:
                yield
            finally:
                stopped.set()
                for client, peer in pairs:
                    client.close()
                    peer.close()

    def assert_deadline(self, handlers, budget=.25, margin=.15):
        with self.transport(handlers, budget):
            started = monotonic()
            with self.assertRaises(ValidationError):
                find_resources(None, {'url': 'https://example.org/lesson'})
            elapsed = monotonic() - started
            self.assertGreater(elapsed, budget * .8)
            self.assertLess(elapsed, budget + margin)

    def test_normal_text_is_read(self):
        def normal(peer, stopped):
            peer.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 5\r\nConnection: close\r\n\r\nhello')

        with self.transport([normal]):
            self.assertEqual(public_text('https://example.org/lesson'), ('https://example.org/lesson', 'hello'))

    def test_continuous_body_bytes_do_not_extend_budget(self):
        def slow_body(peer, stopped):
            peer.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 1000\r\nConnection: close\r\n\r\n')
            for _ in range(40):
                if stopped.wait(.025):
                    break
                peer.sendall(b'x')

        self.assert_deadline([slow_body])

    def test_continuous_header_or_chunk_line_bytes_do_not_extend_budget(self):
        for prefix in (
            b'HTTP/1.1 200 OK\r\nX-Slow: ',
            b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n1;',
        ):
            def slow_line(peer, stopped):
                peer.sendall(prefix)
                for _ in range(40):
                    if stopped.wait(.025):
                        break
                    peer.sendall(b'a')

            with self.subTest(prefix=prefix):
                self.assert_deadline([slow_line])

    def test_redirect_uses_remaining_total_budget(self):
        def redirect(peer, stopped):
            if not stopped.wait(.16):
                peer.sendall(b'HTTP/1.1 302 Found\r\nLocation: /next\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')

        def second(peer, stopped):
            peer.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 1000\r\nConnection: close\r\n\r\n')
            for _ in range(40):
                if stopped.wait(.025):
                    break
                peer.sendall(b'x')

        self.assert_deadline([redirect, second], margin=.08)
