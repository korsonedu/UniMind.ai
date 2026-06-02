"""
Alipay page pay integration.
"""
import json
import logging
import os

from alipay import Alipay

logger = logging.getLogger(__name__)

ALIPAY_APP_ID = os.environ.get('ALIPAY_APP_ID', '')
ALIPAY_PRIVATE_KEY = os.environ.get('ALIPAY_PRIVATE_KEY', '')
ALIPAY_PUBLIC_KEY = os.environ.get('ALIPAY_PUBLIC_KEY', '')
ALIPAY_NOTIFY_URL = os.environ.get('ALIPAY_NOTIFY_URL', '')
ALIPAY_RETURN_URL = os.environ.get('ALIPAY_RETURN_URL', '')
ALIPAY_DEBUG = os.environ.get('DJANGO_ENV', 'production') == 'development'


def _get_client(app_id='', private_key='', alipay_public_key=''):
    """Build Alipay client with configurable credentials."""
    return Alipay(
        appid=app_id or ALIPAY_APP_ID,
        app_notify_url=ALIPAY_NOTIFY_URL,
        app_private_key_string=private_key or ALIPAY_PRIVATE_KEY,
        alipay_public_key_string=alipay_public_key or ALIPAY_PUBLIC_KEY,
        sign_type='RSA2',
        debug=ALIPAY_DEBUG,
    )


def create_page_pay(order, app_id='', private_key='', alipay_public_key=''):
    """Create Alipay page pay → returns full payment URL."""
    alipay = _get_client(app_id, private_key, alipay_public_key)

    subject = f'UniMind {order.get_plan_display()} {order.get_billing_cycle_display()}'
    out_trade_no = f'unimind-{order.id}-{order.created_at.strftime("%Y%m%d%H%M%S")}'

    order_str = alipay.api_alipay_trade_page_pay(
        subject=subject,
        out_trade_no=out_trade_no,
        total_amount=order.amount_cents / 100.0,  # Alipay uses yuan
        return_url=ALIPAY_RETURN_URL,
    )

    order.gateway_order_id = out_trade_no
    order.save(update_fields=['gateway_order_id'])

    pay_url = f'https://openapi.alipay.com/gateway.do?{order_str}'
    if ALIPAY_DEBUG:
        pay_url = f'https://openapi-sandbox.dl.alipaydev.com/gateway.do?{order_str}'

    return {'pay_url': pay_url, 'out_trade_no': out_trade_no}


def create_checkout_session(order) -> dict:
    """Unified interface: create Alipay page pay → return checkout_url."""
    result = create_page_pay(order)
    return {'checkout_url': result['pay_url']}


# Gateway router interface aliases
def verify_webhook(headers, body: bytes):
    """Verify Alipay webhook notification. Compatible with gateway router interface."""
    data = {}
    for key, val in (headers.items() if hasattr(headers, 'items') else []):
        if key.lower().startswith('x-') or key.lower() == 'sign':
            data[key] = val
    # Alipay sends form-encoded data in body, parse it
    from urllib.parse import parse_qs
    parsed = {k: v[0] if len(v) == 1 else v for k, v in parse_qs(body.decode('utf-8')).items()}
    signature = parsed.pop('sign', '') or headers.get('sign', '')
    if not verify_notify(parsed, signature):
        raise ValueError('Alipay webhook signature verification failed')
    return parsed


def process_webhook_event(event: dict) -> dict | None:
    """Process Alipay webhook event. Compatible with gateway router interface."""
    return process_notify(event)


def verify_notify(data: dict, signature: str):
    """Verify Alipay notify signature. Returns True if valid."""
    alipay = _get_client()
    return alipay.verify(data, signature)


def process_notify(data: dict) -> dict | None:
    """Process Alipay notify. Returns order info if payment succeeded."""
    trade_status = data.get('trade_status', '')
    if trade_status not in ('TRADE_SUCCESS', 'TRADE_FINISHED'):
        return None

    out_trade_no = data.get('out_trade_no', '')
    if not out_trade_no.startswith('unimind-'):
        logger.error("Alipay notify: unrecognized out_trade_no=%s", out_trade_no)
        return None

    try:
        order_id = int(out_trade_no.split('-')[1])
    except (IndexError, ValueError):
        logger.error("Alipay notify: cannot parse order_id from %s", out_trade_no)
        return None

    return {
        'order_id': order_id,
        'gateway_txn_id': data.get('trade_no', out_trade_no),
        'amount_cents': int(float(data.get('total_amount', 0)) * 100),
        'raw': data,
    }
