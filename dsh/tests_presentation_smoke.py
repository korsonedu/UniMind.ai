"""New presentation cards retain provenance; tool failures retain stable call IDs."""
import json
import os
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cards import tool_cards
from streaming import tool_status
from worker import execute


class PresentationSmoke(unittest.TestCase):
    def test_validated_card_history_and_provenance(self):
        visual = {'type': 'action_cards', 'payload': {'cards': [{'action': {'type': 'reply', 'url': '继续讲解'}}]}}
        context = {'tools': [], 'available_tools': [{'function': {'name': 'present_learning_visual'}}]}
        events = [{'type': 'tool/call', 'data': {'name': 'present_learning_visual', 'callId': 'a'}},
            {'type': 'tool/result', 'data': {'meta': {'unimindCard': visual}, 'message': {
                'role': 'tool', 'toolCallId': 'a', 'content': [{'type': 'text', 'text': '{"presented":true}'}]}}}]
        self.assertEqual(tool_cards(events, context), [{'tool': 'present_learning_visual', **visual}])
        visual['payload']['cards'][0]['action'] = {'type': 'navigate', 'url': '//external.invalid'}
        self.assertEqual(tool_cards(events, context), [])
        visual['payload']['cards'][0]['action']['url'] = '/course/1'
        self.assertEqual(len(tool_cards(events, context)), 1)
        context['available_tools'] = [{'function': {'name': 'search_courses'}}]
        events[0]['data']['name'] = 'search_courses'
        self.assertEqual(tool_cards(events, context), [])

    def test_worker_locks_session_without_blocking_other_conversations(self):
        with TemporaryDirectory() as state_dir, patch.dict(os.environ):
            payload = {'api_url': 'http://127.0.0.1:1', 'token': 'synthetic', 'state_dir': state_dir,
                'runtime_source': 'local-protocol-smoke', 'action': 'chat', 'create_session': False,
                'session_id': 'a' * 32, 'message': '合成提问', 'model': {}}
            def runtime(_message, _model, session_id, _emit):
                if session_id == 'a' * 32:
                    other = execute({**payload, 'session_id': 'b' * 32})
                    same = execute(payload)
                    self.assertEqual(other['status'], 200)
                    self.assertEqual(same['status'], 409)
                return {'content': '合成回答'}
            with patch('host.backend_request', return_value={'student': {'id': 1}}), \
                    patch('host.run_turn', side_effect=runtime):
                self.assertEqual(execute(payload)['status'], 200)

    def test_terminal_status_and_interruption(self):
        for error, content in [(False, '{}'), (True, '{}'), (False, '{"error":"denied"}')]:
            calls = {}
            start = tool_status({'type': 'tool/call', 'data': {'name': 'search_courses', 'callId': 'stable'}}, {'search_courses'}, calls)
            end = tool_status({'type': 'tool/result', 'data': {'message': {'toolCallId': 'stable', 'isError': error,
                'content': [{'type': 'text', 'text': content}]}}}, {'search_courses'}, calls)
            self.assertEqual(start['call_id'], end['call_id'])
            self.assertEqual(end['status'], 'failed' if error or 'error' in content else 'succeeded')
            self.assertEqual(calls, {})
        events = []
        def interrupted(_payload, emit):
            emit({'type': 'tool_status', 'name': 'search_courses', 'call_id': 'pending', 'status': 'running'})
            raise RuntimeError('synthetic private error')
        with patch('worker._execute', interrupted):
            with self.assertRaises(RuntimeError):
                execute({}, events.append)
        self.assertEqual([e['status'] for e in events], ['running', 'failed'])
        self.assertNotIn('synthetic private', json.dumps(events))


if __name__ == '__main__':
    unittest.main()
