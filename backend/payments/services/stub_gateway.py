"""
Stub payment gateway — returns mock checkout URLs and simulates webhooks.
用于前端开发，不连接真实支付平台。后续替换为正式网关时只需换 views 里的 import。
"""
import uuid
import time


def create_checkout_session(order) -> dict:
    """返回模拟收银台 URL。前端跳转到此 URL 即表示"支付成功"。"""
    return {
        'checkout_url': f'/payments/result?order_id={order.id}&status=paid&txn_id=stub_{uuid.uuid4().hex[:12]}',
    }


def verify_webhook(headers: dict, body: bytes) -> dict:
    """Stub webhook 验签：永远通过，返回模拟事件。"""
    import json
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        payload = {}
    return {
        'type': payload.get('type', 'payment.succeeded'),
        'data': payload.get('data', {}),
    }


def process_webhook_event(event: dict) -> dict | None:
    """
    处理模拟 webhook 事件。
    忽略不关心的事件类型，返回支付成功的结果。
    """
    event_type = event.get('type', '')
    if event_type not in ('payment.succeeded', 'payment.captured'):
        return None

    data = event.get('data', {})
    order_id = data.get('order_id')
    if not order_id:
        return None

    return {
        'order_id': int(order_id),
        'gateway_txn_id': data.get('txn_id', f'stub_{uuid.uuid4().hex[:12]}'),
        'raw': event,
        'amount_cents': data.get('amount_cents'),
    }
