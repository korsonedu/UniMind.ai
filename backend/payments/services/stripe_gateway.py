"""
Stripe payment gateway integration.
"""
import logging
import os

import stripe

logger = logging.getLogger(__name__)

STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')


def _get_stripe():
    if not STRIPE_SECRET_KEY:
        raise RuntimeError('STRIPE_SECRET_KEY not configured')
    stripe.api_key = STRIPE_SECRET_KEY
    return stripe


def create_payment_intent(order):
    """Create a Stripe PaymentIntent and return the client_secret."""
    s = _get_stripe()
    intent = s.PaymentIntent.create(
        amount=order.amount_cents,
        currency='cny',
        metadata={
            'order_id': str(order.id),
            'user_id': str(order.user_id),
        },
        description=f'UniMind {order.get_plan_display()} {order.get_billing_cycle_display()}',
    )
    order.gateway_order_id = intent.id
    order.save(update_fields=['gateway_order_id'])
    return {'clientSecret': intent.client_secret}


def verify_webhook(payload: bytes, sig_header: str):
    """Verify Stripe webhook signature and return parsed event."""
    s = _get_stripe()
    return s.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)


def process_webhook_event(event) -> dict | None:
    """Process a verified Stripe webhook event. Returns order info if payment succeeded."""
    if event.type != 'payment_intent.succeeded':
        return None

    intent = event.data.object
    order_id = intent.metadata.get('order_id')
    if not order_id:
        logger.error("Stripe webhook missing order_id in metadata")
        return None

    return {
        'order_id': int(order_id),
        'gateway_txn_id': intent.id,
        'amount_cents': intent.amount_received,
        'raw': {
            'id': intent.id,
            'amount': intent.amount,
            'amount_received': intent.amount_received,
            'currency': intent.currency,
            'status': intent.status,
        },
    }
