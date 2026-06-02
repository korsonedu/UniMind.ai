"""
Stripe payment gateway integration.
"""
import logging
import os

import stripe

logger = logging.getLogger(__name__)

STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')

SITE_URL = os.environ.get('SITE_URL', 'http://localhost:5173')


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


def create_checkout_session(order) -> dict:
    """Create a Stripe Checkout Session and return the hosted checkout URL."""
    s = _get_stripe()
    session = s.checkout.Session.create(
        mode='payment',
        line_items=[{
            'price_data': {
                'currency': 'cny',
                'product_data': {
                    'name': f'UniMind {order.get_plan_display()} {order.get_billing_cycle_display()}',
                },
                'unit_amount': order.amount_cents,
            },
            'quantity': 1,
        }],
        metadata={
            'order_id': str(order.id),
            'user_id': str(order.user_id),
        },
        success_url=f'{SITE_URL}/payments/result?order_id={order.id}&status=success',
        cancel_url=f'{SITE_URL}/billing?status=cancelled',
    )
    order.gateway_order_id = session.id
    order.save(update_fields=['gateway_order_id'])
    return {'checkout_url': session.url}


def verify_webhook(headers, body: bytes):
    """Verify Stripe webhook signature and return parsed event.
    Compatible with gateway router interface: verify_webhook(headers, body)."""
    s = _get_stripe()
    sig_header = headers.get('stripe-signature', headers.get('Stripe-Signature', ''))
    return s.Webhook.construct_event(body, sig_header, STRIPE_WEBHOOK_SECRET)


def process_webhook_event(event) -> dict | None:
    """Process a verified Stripe webhook event. Returns order info if payment succeeded."""
    if event.type == 'checkout.session.completed':
        session = event.data.object
        order_id = session.metadata.get('order_id')
        if not order_id:
            logger.error("Stripe checkout session missing order_id in metadata")
            return None
        return {
            'order_id': int(order_id),
            'gateway_txn_id': session.id,
            'amount_cents': session.amount_total,
            'raw': {
                'id': session.id,
                'payment_status': session.payment_status,
                'amount_total': session.amount_total,
                'currency': session.currency,
            },
        }

    if event.type == 'payment_intent.succeeded':
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

    return None
