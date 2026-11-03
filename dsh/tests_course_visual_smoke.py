"""Actual SDK + provider gateway with local course-image protocol fixtures only."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch

import host
from sessions import SessionStore
from smoke import model_fixture


class CourseVisualSmoke(unittest.TestCase):
    def test_actual_harness_receives_authorized_images_after_tool_round(self):
        question = '解释当前课程画面'
        # A small real JPEG; provider responses remain fully simulated.
        image = ('/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/'
                 '2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAACAAIDASIAAhEBAxEB/'
                 '8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/'
                 '8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD3+iiigD//2Q==')
        context = {'student': {'id': 1}, 'memory': {'version': 'fixture'},
                   'permissions_version': 'fixture', 'routing': {},
                   'system_prompt': '课程资料：当前冻结截图与讲稿。',
                   'tools': [], 'tool_groups': {},
                   'model_policy': {'operation': 'assistant.chat.planner', 'tier': 'fast',
                       'model': 'deepseek-v4-flash', 'max_requests': 2,
                       'max_tokens': 128, 'max_request_bytes': 65536},
                   'course_visual_message': question,
                   'course_visual_content': [
                       {'type': 'text', 'text': 'current：12 秒'},
                       {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + image}}]}

        class Backend(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                if self.path != '/api/ai/dsh/context/':
                    self.send_error(404)
                    return
                body = json.dumps(context).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        backend = ThreadingHTTPServer(('127.0.0.1', 0), Backend)
        Thread(target=backend.serve_forever, daemon=True).start()
        model, calls = model_fixture()
        # First provider request asks for a native discovery tool; the second
        # must still see the same image, as real models may use tools first.
        definition = {'function': {'name': 'find_learning_tools', 'description': 'fixture',
                      'parameters': {'type': 'object', 'properties': {'group': {'type': 'string'}},
                                     'required': ['group']}}}
        context['tools'] = [definition]
        context['tool_groups'] = {'resources': {'title': 'fixture', 'description': 'fixture', 'tools': []}}
        model.tool_response = lambda body: [('find_learning_tools', {'group': 'resources'})] if len(calls) == 1 else None
        try:
            with TemporaryDirectory(prefix='unimind-course-visual-sdk-') as temp, patch.dict(os.environ, {
                    'UNIMIND_API_URL': f'http://127.0.0.1:{backend.server_port}',
                    'UNIMIND_AUTH_TOKEN': 'LOCAL_SYNTHETIC_IDENTITY'}), \
                    patch.object(host, 'SESSIONS', SessionStore(Path(temp) / 'sessions')):
                result = host.run_turn(question, {'url': f'http://127.0.0.1:{model.server_port}/v1/messages',
                    'key': 'LOCAL_SYNTHETIC_MODEL', 'mode': 'local-protocol-smoke'})
            self.assertEqual(result['finish_reason'], 'completed')
            self.assertEqual(len(calls), 2)
            for call in calls:
                self.assertNotIn(image, json.dumps(call.get('system')))
                images = [block for row in call['messages'] if isinstance(row['content'], list)
                          for block in row['content'] if block['type'] == 'image']
                self.assertEqual(len(images), 1)
                self.assertEqual(images[0]['source']['data'], image)
                self.assertEqual(images[0]['source']['media_type'], 'image/jpeg')
            self.assertNotIn(image, json.dumps(result['gateway']))
        finally:
            model.shutdown()
            model.server_close()
            backend.shutdown()
            backend.server_close()


if __name__ == '__main__':
    unittest.main()
