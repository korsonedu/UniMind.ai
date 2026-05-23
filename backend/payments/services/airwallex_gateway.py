"""
Airwallex Hosted Checkout gateway.

Flow:
  1. POST /api/v1/authentication/login  →  access_token
  2. POST /api/v1/pa/checkout/sessions  →  { url }  (hosted payment page)
  3. Redirect user to url
  4. Webhook callback → confirm order
  5. User lands back on success_url

Docs: https://www.airwallex.com/docs
Sandbox: https://demo.airwallex.com
"""

import hashlib
import hmac
import json
import logging
import os
import time
from urllib.parse import urljoin

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────

AIRWALLEX_API_KEY      = os.environ.get('AIRWALLEX_API_KEY', '')
AIRWALLEX_CLIENT_ID    = os.environ.get('AIRWALLEX_CLIENT_ID', '')
AIRWALLEX_API_BASE     = os.environ.get('AIRWALLEX_API_BASE', 'https://api-demo.airwallex.com')
AIRWALLEX_WEBHOOK_KEY  = os.environ.get('AIRWALLEX_WEBHOOK_KEY', '')

AIRWALLEX_SUCCESS_URL  = os.environ.get('SITE_URL', 'http://localhost:5173') + '/payments/result'
AIRWALLEX_CANCEL_URL   = os.environ.get('SITE_URL', 'http://localhost:5173') + '/billing'


# ── Auth ─────────────────────────────────────────

def _get_token() -> str:
    """Obtain bearer token from Airwallex."""
    resp = requests.post(
        urljoin(AIRWALLEX_API_BASE, '/api/v1/authentication/login'),
        headers={
            'x-client-id': AIRWALLEX_CLIENT_ID,
            'x-api-key': AIRWALLEX_API_KEY,
            'Content-Type': 'application/json',
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()['token']


# ── Checkout Session ─────────────────────────────

def create_checkout_session(order) -> dict:
    """
    Create a hosted checkout session on Airwallex.
    Returns {"checkout_url": "https://..."} for frontend redirect.

    order: payments.models.Order instance
    """
    token = _get_token()
    amount = order.amount_cents / 100  # Airwallex uses major currency units

    payload = {
        'amount': amount,
        'currency': 'CNY',
        'merchant_order_id': str(order.id),
        'order': {
            'products': [{
                'code': order.plan,
                'name': f'UniMind {order.get_plan_display()} — {order.get_billing_cycle_display()}',
                'unit_price': amount,
                'quantity': 1,
            }],
        },
        'success_url': f'{AIRWALLEX_SUCCESS_URL}?order_id={order.id}&status=success',
        'cancel_url':  f'{AIRWALLEX_CANCEL_URL}?status=cancelled',
        'return_url':  f'{AIRWALLEX_SUCCESS_URL}?order_id={order.id}',

        # Payment methods: all available
        'payment_method_options': [
            'card',
            'wechatpay',
            'alipay',
        ],

        # Customer info (optional, pre-fills form)
        'customer': {
            'email': order.user.email if hasattr(order.user, 'email') else '',
        },

        # Expiry
        'expires_at': order.expires_at.isoformat() if order.expires_at else None,
    }

    resp = requests.post(
        urljoin(AIRWALLEX_API_BASE, '/api/v1/pa/checkout/sessions'),
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        },
        json=payload,
        timeout=15,
    )
    data = resp.json()

    if resp.status_code >= 400:
        logger.error('Airwallex create session failed: %s', data)
        raise Exception(data.get('message', 'Airwallex session creation failed'))

    # Save gateway reference
    order.gateway_order_id = data['id']
    order.save(update_fields=['gateway_order_id'])

    return {
        'checkout_url': data['url'],
        'session_id': data['id'],
    }


# ── Webhook ──────────────────────────────────────

def verify_webhook(headers: dict, body: bytes) -> dict:
    """
    Verify Airwallex webhook signature.
    Returns parsed event data if valid.
    """
    signature = headers.get('x-airwallex-signature', '')
    timestamp  = headers.get('x-airwallex-timestamp', '')

    if not signature or not timestamp:
        raise ValueError('Missing webhook signature headers')

    # HMAC-SHA256 verification
    payload = f'{timestamp}.{body.decode()}'
    expected = hmac.new(
        AIRWALLEX_WEBHOOK_KEY.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise ValueError('Webhook signature mismatch')

    return json.loads(body)


def process_webhook_event(event: dict) -> dict | None:
    """
    Process webhook event. Returns order info dict on payment success, or None.
    """
    event_type = event.get('type', event.get('name', ''))

    if event_type not in ('payment_succeeded', 'checkout.session.completed'):
        return None

    obj = event.get('data', {}).get('object', event.get('data', {}))
    merchant_order_id = obj.get('merchant_order_id', '')

    try:
        order_id = int(merchant_order_id)
    except (ValueError, TypeError):
        logger.error('Airwallex webhook: bad merchant_order_id=%s', merchant_order_id)
        return None

    return {
        'order_id': order_id,
        'gateway_txn_id': obj.get('id', ''),
        'amount_cents': int(float(obj.get('amount', 0)) * 100),
        'raw': event,
    }
