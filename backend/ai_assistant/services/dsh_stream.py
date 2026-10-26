"""ASGI transport for one existing bounded site task; no second ledger or agent loop."""
import asyncio
import json
from queue import Queue, Empty, Full
from threading import Event, Thread

from django.db import close_old_connections
from rest_framework.exceptions import APIException


async def stream_events(action):
    queue = Queue(maxsize=64)
    closed = Event()

    def publish(event):
        if event['type'] in ('done', 'error'):
            while not closed.is_set():
                try:
                    queue.put_nowait(event)
                    return
                except Full:
                    try:
                        queue.get_nowait()  # Final result replaces expendable provisional fragments.
                    except Empty:
                        pass
        elif not closed.is_set():
            try:
                queue.put_nowait(event)
            except Full:
                pass  # Provisional fragments may be dropped; done contains the canonical answer.

    def produce():
        close_old_connections()
        try:
            result = action(publish)
            publish({'type': 'done', 'result': result})
        except APIException as exc:
            detail = exc.detail
            publish({'type': 'error', 'status': exc.status_code,
                     'error': str(detail.get('error', '本轮未完成。')) if isinstance(detail, dict) else str(detail)})
        except Exception:
            publish({'type': 'error', 'status': 503, 'error': 'DSH 服务暂不可用，请稍后恢复同一请求。'})
        finally:
            close_old_connections()

    Thread(target=produce, daemon=True).start()
    try:
        while True:
            try:
                event = await asyncio.to_thread(queue.get, True, 5)
            except Empty:
                yield b': heartbeat\n\n'
                continue
            yield ('data: ' + json.dumps(event, ensure_ascii=False) + '\n\n').encode()
            if event['type'] in ('done', 'error'):
                break
    finally:
        closed.set()  # The dispatched task still completes/settles within its original deadline.
