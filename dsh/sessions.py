"""Account-scoped local M0 transcripts; runtime context is disposable."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from threading import RLock
from uuid import uuid4


class SessionUnavailable(Exception):
    pass


def context_version(context):
    from importlib.metadata import version
    root = Path(__file__).parent
    value = [context['student']['id'], context['memory']['version'], context['permissions_version'],
             context['model_policy'], context['system_prompt'], context.get('runtime_source'), version('deepseek-harness-sdk'),
             (root / 'plugin.ts').read_text(), (root / 'profile.patch.yml').read_text()]
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class SessionStore:
    def __init__(self, root):
        self.root = Path(root)
        self.lock = RLock()  # Single Host prototype: serialize turn/read/delete.

    def directory(self, context, session_id):
        if not isinstance(session_id, str) or not re.fullmatch('[0-9a-f]{32}', session_id):
            raise SessionUnavailable()
        identity = [os.environ.get('UNIMIND_API_URL', ''), context['student']['id']]
        owner = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
        path = self.root / owner / session_id
        if path.resolve() != self.root.resolve() / owner / session_id:
            raise SessionUnavailable()
        return path

    def save(self, context, state):
        directory = self.directory(context, state['id'])
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = directory / 'transcript.json'
        with os.fdopen(os.open(directory / 'transcript.tmp', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as stream:
            json.dump(state, stream, ensure_ascii=False)
        os.replace(directory / 'transcript.tmp', path)

    def create(self, context, session_id=None):
        state = {'id': session_id or uuid4().hex, 'context_version': context_version(context),
                 'runtime_id': uuid4().hex, 'runtime_ready': False, 'runtime_start': 0, 'dirty': False,
                 'messages': [], 'notice': '', 'updated_at': datetime.now(timezone.utc).isoformat()}
        self.save(context, state)
        return state

    def load(self, context, session_id):
        try:
            state = json.loads((self.directory(context, session_id) / 'transcript.json').read_text())
        except FileNotFoundError:
            raise SessionUnavailable() from None
        if state['id'] != session_id:
            raise SessionUnavailable()
        if state['dirty'] or 'runtime_start' not in state or state['context_version'] != context_version(context):
            self.invalidate(context, state)
        return state

    def invalidate(self, context, state):
        home = self.directory(context, state['id']) / 'runtime'
        if home.exists():
            shutil.rmtree(home)
        state.update(context_version=context_version(context), runtime_id=uuid4().hex,
                     runtime_ready=False, runtime_start=len(state['messages']), dirty=False,
                     notice='记忆、工具权限或运行状态已变化，模型上下文已重建；原聊天仅保留供查看。')
        self.save(context, state)

    def public(self, state):
        return {key: state[key] for key in ('id', 'messages', 'notice', 'updated_at')}

    def delete(self, context, session_id):
        self.load(context, session_id)
        shutil.rmtree(self.directory(context, session_id))
