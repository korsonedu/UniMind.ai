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
    def test_old_transcript_stays_out_after_rebuilt_turn(self):
        context = {'student': {'id': 1}, 'memory': {'version': 'old'}, 'permissions_version': 'allowed',
                   'model_policy': {'model': 'test', 'operation': 'assistant.chat.planner', 'max_tokens': 128},
                   'system_prompt': 'test', 'routing': {}, 'runtime_source': 'local-protocol-smoke'}
        @contextmanager
        def gateway(*_args):
            yield {'url': 'http://127.0.0.1:1/v1', 'credential': 'SYNTHETIC_TASK', 'mode': 'local-protocol-smoke',
                   'task_id': 'test-task', 'requests': [{'status': 'completed'}]}
        with TemporaryDirectory() as temp:
            store = SessionStore(temp)
            state = store.create(context)
            state.update(messages=[{'role': 'user', 'content': 'OLD_PRIVATE_MEMORY 请批改'},
                                   {'role': 'assistant', 'content': '确认继续批改吗？'}], runtime_ready=True)
            store.save(context, state)
            context['memory']['version'] = 'corrected'
            calls = []
            def backend(_path, body):
                calls.append(body)
                return deepcopy(context)
            harness = MagicMock()
            for method in ('start_session', 'resume_session'):
                getattr(harness.__enter__.return_value, method).return_value.run.return_value = SimpleNamespace(final_response='fresh answer', finish_reason='stop')
            config = {'url': 'http://127.0.0.1:1/v1/messages', 'key': 'SYNTHETIC_KEY', 'mode': 'local-protocol-smoke'}
            with patch.object(host, 'SESSIONS', store), patch.object(host, 'backend_request', backend), \
                    patch.object(host, 'task_gateway', gateway), patch.object(host, 'DeepSeekHarness', return_value=harness):
                host.run_turn('fresh question', config, state['id'])
                calls.clear()
                result = host.run_turn('继续', config, state['id'])
            routed = [m for call in calls for m in call.get('recent_messages', [])]
            self.assertEqual([m['content'] for m in routed], ['fresh question', 'fresh answer'])
            self.assertNotIn('OLD_PRIVATE_MEMORY', json.dumps(routed))
            self.assertIn('OLD_PRIVATE_MEMORY', json.dumps(result['session']['messages']))

    def test_official_turn_keeps_session_state(self):
        context = {'student': {'id': 1}, 'memory': {'version': 'initial'}, 'permissions_version': 'allowed',
                   'model_policy': {'model': 'test', 'operation': 'assistant.chat.planner', 'max_tokens': 128}, 'system_prompt': 'test', 'routing': {}}
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
