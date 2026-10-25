"""Offline local-session smoke: ownership, invalidation, failure and deletion."""
from copy import deepcopy
from contextlib import contextmanager
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import host
from sessions import SessionStore, SessionUnavailable


class SessionSmoke(unittest.TestCase):
    def test_official_turn_keeps_session_state(self):
        context = {'student': {'id': 1}, 'memory': {'version': 'initial'}, 'permissions_version': 'allowed',
                   'model_policy': {'model': 'test', 'operation': 'assistant.chat.planner', 'max_tokens': 128}, 'system_prompt': 'test'}
        @contextmanager
        def gateway(*_args):
            yield {'url': 'http://127.0.0.1:1/v1', 'credential': 'SYNTHETIC_TASK', 'mode': 'deepseek-official',
                   'task_id': 'test-task', 'requests': [{'status': 'completed'}]}
        with TemporaryDirectory() as temp:
            root = Path(temp) / 'dsh'
            root.mkdir()
            harness = MagicMock()
            harness.__enter__.return_value.start_session.return_value.run.return_value = SimpleNamespace(final_response='test answer', finish_reason='stop')
            with patch.object(host, 'ROOT', root), patch.object(host, 'SESSIONS', SessionStore(Path(temp) / 'sessions')), \
                    patch.object(host, 'backend_request', side_effect=lambda *_args: deepcopy(context)), \
                    patch.object(host, 'task_gateway', gateway), patch.object(host, 'DeepSeekHarness', return_value=harness):
                result = host.run_turn('test question', {'url': 'https://api.deepseek.com/anthropic/v1/messages', 'key': 'SYNTHETIC_KEY', 'mode': 'deepseek-official'})
                self.assertEqual(len(result['session']['messages']), 2)
                self.assertEqual(result['content'], 'test answer')

    def test_local_lifecycle(self):
        context = {'student': {'id': 1}, 'memory': {'version': 'initial'}, 'permissions_version': 'allowed',
                   'model_policy': {'model': 'test'}, 'system_prompt': 'SYNTHETIC_INTERNAL_PROMPT'}
        with TemporaryDirectory() as temp:
            store = SessionStore(temp)
            with store.lock:
                state = store.create(context)
                state['messages'] = [{'role': 'user', 'content': 'original visible message'}]
                state['runtime_ready'] = True
                store.save(context, state)
                home = store.directory(context, state['id']) / 'runtime'
                home.mkdir()
                (home / 'private-context').write_text('SYNTHETIC_OLD_MEMORY')
                store = SessionStore(temp)
                self.assertEqual(store.load(context, state['id'])['messages'], state['messages'])
                other = deepcopy(context)
                other['student']['id'] = 2
                with self.assertRaises(SessionUnavailable):
                    store.load(other, state['id'])
                with self.assertRaises(SessionUnavailable):
                    store.load(context, '../outside')
                changed = deepcopy(context)
                changed['permissions_version'] = 'revoked'
                rebuilt = store.load(changed, state['id'])
                self.assertFalse(home.exists())
                self.assertFalse(rebuilt['runtime_ready'])
                self.assertNotEqual(rebuilt['runtime_id'], state['runtime_id'])
                self.assertEqual(rebuilt['messages'], state['messages'])
                rebuilt['dirty'] = True
                rebuilt['runtime_ready'] = True
                store.save(changed, rebuilt)
                restored = SessionStore(temp).load(changed, state['id'])
                self.assertFalse(restored['dirty'])
                self.assertFalse(restored['runtime_ready'])
                exported = json.dumps(store.public(restored))
                self.assertNotIn('SYNTHETIC_INTERNAL_PROMPT', exported)
                self.assertNotIn('runtime_id', exported)
                audit = Path(temp) / 'separate-usage.jsonl'
                audit.write_text('retained usage')
                store.delete(changed, state['id'])
                with self.assertRaises(SessionUnavailable):
                    store.load(changed, state['id'])
                self.assertTrue(audit.exists())


if __name__ == '__main__':
    unittest.main()
