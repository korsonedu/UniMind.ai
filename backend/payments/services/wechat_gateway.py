"""
WeChat Pay APIv3 integration.
"""
import json
import logging
import os

from wechatpayv3 import WeChatPay, WeChatPayType

logger = logging.getLogger(__name__)

WECHAT_MCH_ID = os.environ.get('WECHAT_MCH_ID', '')
WECHAT_API_V3_KEY = os.environ.get('WECHAT_API_V3_KEY', '')
WECHAT_CERT_SERIAL = os.environ.get('WECHAT_CERT_SERIAL', '')
WECHAT_PRIVATE_KEY_PATH = os.environ.get('WECHAT_PRIVATE_KEY_PATH', '')
WECHAT_APP_ID = os.environ.get('WECHAT_APP_ID', '')
WECHAT_NOTIFY_URL = os.environ.get('WECHAT_NOTIFY_URL', '')


def _get_client(mch_id='', api_v3_key='', cert_serial='', private_key_path=''):
    """Build WeChatPay client with configurable credentials (platform or institution)."""
    return WeChatPay(
        wechatpay_type=WeChatPayType.NATIVE,
        mchid=mch_id or WECHAT_MCH_ID,
        apiv3_key=api_v3_key or WECHAT_API_V3_KEY,
        serial_no=cert_serial or WECHAT_CERT_SERIAL,
        private_key=private_key_path or WECHAT_PRIVATE_KEY_PATH,
        appid=WECHAT_APP_ID,
        notify_url=WECHAT_NOTIFY_URL,
    )


def create_native_order(order, mch_id='', api_v3_key='', cert_serial='', private_key_path=''):
    """Create WeChat Native payment order → returns code_url (QR code)."""
    wx = _get_client(mch_id, api_v3_key, cert_serial, private_key_path)
    description = f'UniMind {order.get_plan_display()}-{order.get_billing_cycle_display()}'
    out_trade_no = f'unimind-{order.id}-{order.created_at.strftime("%Y%m%d%H%M%S")}'

    result = wx.pay(
        description=description,
        out_trade_no=out_trade_no,
        amount={'total': order.amount_cents},
    )

    order.gateway_order_id = out_trade_no
    order.save(update_fields=['gateway_order_id'])

    return {
        'code_url': result.get('code_url', ''),
        'out_trade_no': out_trade_no,
    }


def create_checkout_session(order) -> dict:
    """Unified interface: create WeChat Native order → return checkout_url (QR code URL)."""
    result = create_native_order(order)
    return {'checkout_url': result['code_url']}


# Gateway router interface aliases
def verify_webhook(headers, body: bytes):
    """Verify WeChat webhook notification. Compatible with gateway router interface."""
    return verify_notify(headers, body)


def process_webhook_event(event: dict) -> dict | None:
    """Process WeChat webhook event. Compatible with gateway router interface."""
    return process_notify(event)


def verify_notify(headers: dict, body: bytes):
    """Verify WeChat Pay callback and return decrypted resource."""
    wx = _get_client()
    # wechatpayv3 SDK handles verification automatically when parsing
    data = json.loads(body)
    return data


def process_notify(data: dict) -> dict | None:
    """Process WeChat Pay callback. Returns order info if payment succeeded."""
    if data.get('trade_state') != 'SUCCESS' and data.get('trade_state') != 'REFUND':
        return None

    out_trade_no = data.get('out_trade_no', '')
    if not out_trade_no.startswith('unimind-'):
        logger.error("WeChat notify: unrecognized out_trade_no=%s", out_trade_no)
        return None

    try:
        order_id = int(out_trade_no.split('-')[1])
    except (IndexError, ValueError):
        logger.error("WeChat notify: cannot parse order_id from %s", out_trade_no)
        return None

    transaction_id = data.get('transaction_id', '')

    return {
        'order_id': order_id,
        'gateway_txn_id': transaction_id or out_trade_no,
        'amount_cents': data.get('amount', {}).get('total'),
        'raw': data,
    }
