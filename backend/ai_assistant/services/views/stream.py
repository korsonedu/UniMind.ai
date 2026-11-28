"""ASGI transport for one existing bounded site task; no second ledger or agent loop."""
import asyncio
import json
from contextlib import aclosing
from queue import Queue, Empty
from threading import Event, Thread

from django.db import close_old_connections, connections
from rest_framework.exceptions import APIException


async def action_events(action):
    queue = Queue()
    closed = Event()

    def publish(event):
        # Text is expendable; control/status events must survive a slow consumer.
        # Their count is bounded by the original task's model/tool budget.
        if not closed.is_set() and (event['type'] != 'text_delta' or queue.qsize() < 63):
            queue.put_nowait(event)

    def produce():
        close_old_connections()
        try:
            result = action(publish)
            event = {'type': 'done', 'result': result}
        except APIException as exc:
            detail = exc.detail
            event = {'type': 'error', 'status': exc.status_code,
                     'error': str(detail.get('error', '本轮未完成。')) if isinstance(detail, dict) else str(detail)}
        except Exception:
            event = {'type': 'error', 'status': 503, 'error': '小宇本轮未完成，请稍后恢复同一请求。'}
        finally:
            connections.close_all()
        publish(event)

    Thread(target=produce, daemon=True).start()
    try:
        while True:
            try:
                event = await asyncio.to_thread(queue.get, True, 5)
            except Empty:
                yield None
                continue
            yield event
            if event['type'] in ('done', 'error'):
                break
    finally:
        closed.set()  # The dispatched task still completes/settles within its original deadline.


async def stream_events(action):
    async with aclosing(action_events(action)) as events:
        async for event in events:
            yield (b': heartbeat\n\n' if event is None else
                   ('data: ' + json.dumps(event, ensure_ascii=False) + '\n\n').encode())
