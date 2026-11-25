"""Site-owned process boundary; no client-selected credentials or destinations."""
import json
import hashlib
import os
from pathlib import Path
import signal
import shutil
import subprocess
from contextlib import contextmanager
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from uuid import uuid4
from threading import Thread

from django.conf import settings
from django.db import connection, OperationalError
from rest_framework.exceptions import APIException

from ai_engine.config import get_model_for_task
from ai_engine.observability import log_ai_operation, model_token_counts
from ..dsh_authentication import make_task_token
from .ulr_config import standalone_ulr


class DshUnavailable(APIException):
    status_code = 503
    default_detail = 'DSH 服务暂不可用，请稍后重试。'


def chat_lock_directory():
    if not standalone_ulr() and settings.UNIMIND_DSH_STATE_DIR:
        return settings.UNIMIND_DSH_STATE_DIR
    return str(settings.BASE_DIR / 'logs' / 'chat-locks')


@contextmanager
def site_request_lock(user, scope=None):
    """Keep generation, quota commit and deletion ordered for this student or conversation."""
    if standalone_ulr() and connection.vendor == 'postgresql':
        # PostgreSQL reservations and conversation row locks coordinate across application hosts.
        yield
        return
    try:
        import fcntl
        state_dir = chat_lock_directory()
        if not state_dir or not Path(state_dir).is_absolute():
            raise DshUnavailable('尚未配置服务端 DSH 状态目录。')
        Path(state_dir).mkdir(mode=0o700, parents=True, exist_ok=True)
        root = Path(state_dir) / '.requests'
        root.mkdir(mode=0o700, exist_ok=True)
        if scope is None:
            key = str(user.pk)
        else:
            digest = hashlib.sha256(str(scope).strip().lower().encode()).hexdigest()
            key = f'{user.pk}-{digest}'
        with os.fdopen(os.open(root / key, os.O_CREAT | os.O_RDWR, 0o600), 'a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                error = DshUnavailable('当前会话仍有操作在处理中，请稍后重试。' if scope is not None
                                       else '当前账号仍有会话操作在处理中，请稍后重试。')
                error.status_code = 409
                raise error from None
            yield
    except (OSError, ImportError):
        raise DshUnavailable() from None


@contextmanager
def quota_write_lock():
    """Serialize SQLite ledger access while a bridge write is in progress."""
    try:
        if connection.vendor != 'sqlite':
            yield
            return
        import fcntl
        state_dir = chat_lock_directory()
        if not state_dir or not Path(state_dir).is_absolute():
            raise DshUnavailable('尚未配置服务端 DSH 状态目录。')
        root = Path(state_dir)
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        with os.fdopen(os.open(root / '.quota.lock', os.O_CREAT | os.O_RDWR, 0o600), 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield
    except (OSError, OperationalError, ImportError):
        raise DshUnavailable('数据服务繁忙或运行环境不可用，请稍后重试。') from None


def log_model_observation(record, reservation=None, *, gateway_id=None):
    completed = record['status'] == 'completed'
    counts = model_token_counts(record.get('usage'), anthropic=True) if record['usage_complete'] else {}
    log_ai_operation(operation=record['operation'], success=completed, duration_ms=record['elapsed_ms'],
        error_category='none' if completed else record['status'], metadata={
            'runtime': 'dsh', 'gateway_id': gateway_id,
            **({'request_id': reservation.request_id, 'attempt_id': reservation.attempt_id} if reservation else {}),
            'model': record['model'], 'offered_tools': ','.join(record['offered_tools']), 'model_request': record['request'],
            'reported_model': record.get('reported_model'), 'max_output_tokens': record['max_output_tokens'],
            'submitted_tools': ','.join(record['submitted_tools']) if 'submitted_tools' in record else None,
            **counts,
        })


def run_site_action(user, action, *, message='', session_id=None, reservation=None, on_event=None, chat_context=None):
    python = getattr(settings, 'UNIMIND_DSH_PYTHON', '')
    api_url = getattr(settings, 'UNIMIND_DSH_API_URL', '')
    state_dir = getattr(settings, 'UNIMIND_DSH_STATE_DIR', '')
    if (not python or not Path(python).is_absolute() or not Path(python).is_file()
            or not state_dir or not Path(state_dir).is_absolute()
            or urlsplit(api_url).scheme != 'http' or urlsplit(api_url).hostname not in ('127.0.0.1', 'localhost', '::1')):
        raise DshUnavailable('尚未配置服务端 DSH 运行环境。')
    model = None
    if action == 'chat':
        fixture = getattr(settings, 'UNIMIND_DSH_FIXTURE_URL', '')
        if fixture:
            if (not settings.DEBUG or urlsplit(fixture).scheme != 'http'
                    or urlsplit(fixture).hostname not in ('127.0.0.1', 'localhost', '::1')):
                raise DshUnavailable('协议模拟仅允许显式的本机开发环境。')
            model = {'url': fixture, 'key': 'local-protocol-fixture', 'mode': 'local-protocol-smoke'}
        else:
            config = get_model_for_task('assistant.chat.planner')
            if urlsplit(config['base_url']).hostname != 'api.deepseek.com' or not config['api_key']:
                raise DshUnavailable('尚未配置已授权的 DeepSeek 官方来源。')
            model = {'url': 'https://api.deepseek.com/anthropic/v1/messages',
                     'key': config['api_key'], 'mode': 'deepseek-official'}
    create_session = action == 'new' or (action == 'chat' and not session_id)
    session_id = uuid4().hex if create_session else session_id
    payload = {'action': action, 'message': message, 'session_id': session_id, 'api_url': api_url,
               'state_dir': state_dir, 'token': make_task_token(user, reservation, chat_context=chat_context), 'model': model,
               'create_session': create_session,
               'runtime_source': 'local-protocol-smoke' if getattr(settings, 'UNIMIND_DSH_FIXTURE_URL', '') else 'deepseek-official'}
    worker = Path(settings.BASE_DIR).parent / 'dsh' / 'worker.py'
    environment = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL', 'TMPDIR', 'SSL_CERT_FILE', 'SSL_CERT_DIR') if key in os.environ}
    reserved = None
    completed = False
    event_write = None
    event_reader = None
    event_thread = None
    handoff_dir = None
    try:
        if action == 'chat' and (chat_context or {}).get('history_digest'):
            # Product history owns recovery during handoff. The SDK scratch transcript is private and disposable.
            handoff_dir = TemporaryDirectory(prefix='handoff-', dir=state_dir)
            payload['state_dir'] = state_dir = handoff_dir.name
        if create_session:
            owner = hashlib.sha256(json.dumps([api_url, user.pk]).encode()).hexdigest()
            directory = Path(state_dir) / owner
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            candidate = directory / session_id
            candidate.mkdir(mode=0o700)
            reserved = candidate
        if on_event:
            event_read, event_write = os.pipe()
            environment['UNIMIND_DSH_EVENT_FD'] = str(event_write)
            event_reader = os.fdopen(event_read, 'r')
            def receive_events():
                try:
                    for line in event_reader:
                        if len(line) <= 65536:
                            event = json.loads(line)
                            if isinstance(event, dict):
                                if event.get('type') == 'model_observation' and reservation is not None:
                                    log_model_observation(event['record'], reservation)
                                elif event.get('type') in ('step', 'text_delta', 'tool_status'):
                                    on_event(event)
                except (ValueError, OSError):
                    pass
            event_thread = Thread(target=receive_events, daemon=True)
        with subprocess.Popen([python, str(worker)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, env=environment, start_new_session=True,
                              pass_fds=(event_write,) if event_write is not None else ()) as process:
            if event_write is not None:
                os.close(event_write)
                event_write = None
                event_thread.start()
            try:
                output, _ = process.communicate(json.dumps(payload).encode(), timeout=120)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
                raise DshUnavailable('DSH 本轮运行超时，请重新提问。') from None
        if process.returncode or len(output) > 2 * 1024 * 1024:
            raise ValueError()
        result = json.loads(output)
        if not isinstance(result, dict):
            raise ValueError()
        status = result.get('status', 503)
        if status != 200:
            error = DshUnavailable(result.get('error') or DshUnavailable.default_detail)
            error.status_code = status if status in (403, 404, 409, 429, 503) else 503
            raise error
        if not isinstance(result.get('result'), dict):
            raise ValueError()
        completed = True
        return result['result']
    except (OSError, ValueError, KeyError, TypeError):
        raise DshUnavailable() from None
    finally:
        if event_write is not None:
            os.close(event_write)
        if event_thread and event_thread.ident:
            event_thread.join(timeout=2)
        if event_reader:
            event_reader.close()
        if handoff_dir is not None:
            handoff_dir.cleanup()
        elif reserved is not None and not completed and reserved.exists():
            try:
                shutil.rmtree(reserved)
            except OSError:
                raise DshUnavailable('本轮未完成，临时会话清理失败，请联系管理员。') from None
