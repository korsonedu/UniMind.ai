"""
Stub payment gateway — returns mock checkout URLs and simulates webhooks.
用于前端开发，不连接真实支付平台。后续替换为正式网关时只需换 views 里的 import。

支持：一次性支付 + 订阅（create/cancel/get_status）
"""
import uuid
import time
from datetime import timedelta

from django.utils import timezone


# ── One-time payment interface ──


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
    if event_type not in ('payment.succeeded', 'payment.captured', 'subscription_checkout_completed', 'subscription_renewed'):
        return None

    data = event.get('data', {})
    order_id = data.get('order_id')

    # Renewal events may not have order_id — use subscription_id instead
    if not order_id and event_type != 'subscription_renewed':
        return None

    result = {
        'order_id': int(order_id) if order_id else None,
        'gateway_txn_id': data.get('txn_id', f'stub_{uuid.uuid4().hex[:12]}'),
        'raw': event,
        'amount_cents': data.get('amount_cents'),
    }

    # Subscription events → tag for the webhook view
    if event_type == 'subscription_checkout_completed':
        result['type'] = 'subscription_checkout_completed'
        result['gateway_subscription_id'] = f'sub_stub_{uuid.uuid4().hex[:12]}'
        result['gateway_customer_id'] = 'cus_stub_demo'
    elif event_type == 'subscription_renewed':
        result['type'] = 'subscription_renewed'
        result['gateway_subscription_id'] = data.get('subscription_id', '')
        result['new_period_end'] = data.get('new_period_end')

    return result


# ── Subscription interface ──


def create_subscription_checkout(order) -> dict:
    """返回模拟订阅收银台 URL。"""
    return {
        'subscription_id': f'sub_stub_{order.id}',
        'checkout_url': f'/payments/result?order_id={order.id}&status=paid&txn_id=stub_sub_{uuid.uuid4().hex[:12]}',
    }


def cancel_subscription(subscription) -> dict:
    """模拟取消订阅。"""
    sub = subscription  # 避免 shadowing module name
    sub.status = 'canceled'
    sub.canceled_at = timezone.now()
    sub.save(update_fields=['status', 'canceled_at', 'updated_at'])
    return {'success': True}


def get_subscription_status(subscription) -> dict:
    """返回模拟订阅状态。"""
    sub = subscription
    return {
        'status': sub.status,
        'current_period_start': sub.current_period_start.isoformat() if sub.current_period_start else None,
        'current_period_end': sub.current_period_end.isoformat() if sub.current_period_end else None,
    }
