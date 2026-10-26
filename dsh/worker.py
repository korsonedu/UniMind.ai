"""One site request per isolated SDK process; stdin is a private parent pipe."""
import fcntl
from contextlib import ExitStack
import json
import os
import shutil
from pathlib import Path
import sys
from uuid import uuid4

import host
from sessions import SessionStore, SessionUnavailable


def execute(payload):
    os.environ.update({'UNIMIND_API_URL': payload['api_url'], 'UNIMIND_AUTH_TOKEN': payload['token'],
                       'UNIMIND_DSH_AUTH_SCHEME': 'DSH',
                       'UNIMIND_DSH_AUDIT_DIR': str(Path(payload['state_dir']).parent / 'usage')})
    host.SESSIONS = SessionStore(payload['state_dir'])
    context = host.backend_request('/api/ai/dsh/context/', {})
    context['runtime_source'] = payload['runtime_source']
    owner = host.SESSIONS.directory(context, uuid4().hex).parent
    owner.mkdir(mode=0o700, parents=True, exist_ok=True)
    with ExitStack() as stack:
        lock = stack.enter_context(os.fdopen(os.open(owner / '.runtime.lock', os.O_CREAT | os.O_RDWR, 0o600), 'a'))
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'status': 409, 'error': '当前学习会话仍在处理中，请稍后重试。'}
        action = payload['action']
        if action == 'chat':
            slots = Path(payload['state_dir']) / '.slots'
            slots.mkdir(mode=0o700, parents=True, exist_ok=True)
            for index in range(4):
                slot = os.fdopen(os.open(slots / str(index), os.O_CREAT | os.O_RDWR, 0o600), 'a')
                try:
                    fcntl.flock(slot, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    slot.close()
                    continue
                stack.enter_context(slot)
                break
            else:
                return {'status': 503, 'error': 'AI 服务繁忙，请稍后重试。'}
            new_session = payload['create_session']
            session_id = host.SESSIONS.create(context, payload['session_id'])['id'] if new_session else payload['session_id']
            try:
                result = host.run_turn(payload['message'], payload['model'], session_id)
            except Exception:
                if new_session:
                    shutil.rmtree(host.SESSIONS.directory(context, session_id))
                raise
        elif action == 'new':
            result = host.SESSIONS.public(host.SESSIONS.create(context, payload['session_id']))
        elif action == 'read':
            result = host.SESSIONS.public(host.SESSIONS.load(context, payload['session_id']))
        elif action == 'delete':
            host.SESSIONS.delete(context, payload['session_id'])
            result = {'deleted': True}
        else:
            return {'status': 503, 'error': '未知的 DSH 服务操作。'}
        return {'status': 200, 'result': result}


if __name__ == '__main__':
    try:
        response = execute(json.load(sys.stdin))
    except SessionUnavailable:
        response = {'status': 404, 'error': '会话不存在或不属于当前账号。'}
    except host.HostConfigurationError as exc:
        response = {'status': 503, 'error': str(exc)}
    except Exception:
        response = {'status': 503, 'error': 'DSH 服务暂不可用，请稍后重试。'}
    print(json.dumps(response, ensure_ascii=False))
