"""
Stripe payment gateway integration.
"""
import logging
import os

import stripe
from django.utils import timezone

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


def create_subscription_checkout(institution, plan: str, billing_cycle: str, user_email: str = '') -> dict:
    """Create a Stripe Checkout Session for subscription mode. Returns checkout_url and subscription record."""
    s = _get_stripe()

    # Build price data based on plan
    plan_prices = {
        ('starter', 'monthly'): 9900,    # ¥99/mo
        ('starter', 'annual'): 99000,    # ¥990/yr
        ('growth', 'monthly'): 29900,    # ¥299/mo
        ('growth', 'annual'): 299000,    # ¥2990/yr
        ('enterprise', 'monthly'): 99900,  # ¥999/mo
        ('enterprise', 'annual'): 999000,  # ¥9990/yr
    }
    unit_amount = plan_prices.get((plan, billing_cycle), 9900)

    # Create local subscription record first
    from payments.models import Subscription
    sub = Subscription.objects.create(
        institution=institution,
        plan=plan,
        billing_cycle=billing_cycle,
        status='incomplete',
    )

    session = s.checkout.Session.create(
        mode='subscription',
        line_items=[{
            'price_data': {
                'currency': 'cny',
                'product_data': {
                    'name': f'UniMind {dict(Subscription.PLAN_CHOICES).get(plan, plan)}',
                    'description': dict(Subscription.BILLING_CHOICES).get(billing_cycle, billing_cycle),
                },
                'unit_amount': unit_amount,
                'recurring': {
                    'interval': 'month' if billing_cycle == 'monthly' else 'year',
                },
            },
            'quantity': 1,
        }],
        metadata={
            'subscription_id': str(sub.id),
            'institution_id': str(institution.id),
        },
        customer_email=user_email or None,
        success_url=f'{SITE_URL}/billing?subscription=success',
        cancel_url=f'{SITE_URL}/billing?subscription=cancelled',
    )

    sub.stripe_subscription_id = session.id
    sub.save(update_fields=['stripe_subscription_id'])

    return {'checkout_url': session.url, 'subscription_id': sub.id}


def cancel_subscription(subscription) -> dict:
    """Cancel a Stripe subscription at period end."""
    s = _get_stripe()
    if not subscription.stripe_subscription_id:
        raise ValueError('Subscription has no Stripe ID')

    s.Subscription.modify(
        subscription.stripe_subscription_id,
        cancel_at_period_end=True,
    )
    subscription.canceled_at = timezone.now()
    subscription.save(update_fields=['canceled_at'])
    return {'message': '订阅将在当前周期结束时取消', 'canceled_at': subscription.canceled_at.isoformat()}


def process_webhook_event(event) -> dict | None:
    """Process a verified Stripe webhook event. Returns order info or subscription event."""
    # Subscription events
    if event.type in ('customer.subscription.updated', 'customer.subscription.deleted', 'invoice.paid'):
        return _process_subscription_webhook(event)

    # One-time payment events
    if event.type == 'checkout.session.completed':
        session = event.data.object
        # Check if this is a subscription checkout
        if session.metadata.get('subscription_id'):
            return _process_subscription_checkout_completed(session)

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


def _process_subscription_checkout_completed(session) -> dict | None:
    """Handle checkout.session.completed for subscription mode."""
    subscription_id = session.metadata.get('subscription_id')
    if not subscription_id:
        return None

    try:
        from payments.models import Subscription
        sub = Subscription.objects.get(id=int(subscription_id))
        sub.status = 'active'
        if session.subscription:
            sub.stripe_subscription_id = session.subscription
        sub.current_period_start = timezone.now()
        sub.save(update_fields=['status', 'stripe_subscription_id', 'current_period_start'])
    except Exception as e:
        logger.error(f"Failed to activate subscription {subscription_id}: {e}")

    return {
        'type': 'subscription_checkout_completed',
        'subscription_id': int(subscription_id),
        'gateway_txn_id': session.id,
        'amount_cents': session.amount_total,
        'raw': {
            'id': session.id,
            'subscription': session.subscription,
            'amount_total': session.amount_total,
            'currency': session.currency,
        },
    }


def _process_subscription_webhook(event) -> dict | None:
    """Handle subscription lifecycle events."""
    from payments.models import Subscription

    stripe_sub = event.data.object
    sub_id = stripe_sub.id if hasattr(stripe_sub, 'id') else None
    if not sub_id:
        return None

    try:
        sub = Subscription.objects.get(stripe_subscription_id=sub_id)
    except Subscription.DoesNotExist:
        logger.warning(f"Subscription not found for Stripe sub {sub_id}")
        return None

    if event.type == 'customer.subscription.updated':
        sub.status = stripe_sub.status
        if stripe_sub.current_period_start:
            from datetime import datetime
            sub.current_period_start = datetime.fromtimestamp(stripe_sub.current_period_start)
        if stripe_sub.current_period_end:
            from datetime import datetime
            sub.current_period_end = datetime.fromtimestamp(stripe_sub.current_period_end)
        sub.save(update_fields=['status', 'current_period_start', 'current_period_end'])

    elif event.type == 'customer.subscription.deleted':
        sub.status = 'canceled'
        sub.save(update_fields=['status'])

    elif event.type == 'invoice.paid':
        # Auto-renewal successful — extend period and update institution expiry
        if stripe_sub.get('current_period_end'):
            from datetime import datetime
            sub.current_period_end = datetime.fromtimestamp(stripe_sub.current_period_end)
            sub.status = 'active'
            sub.save(update_fields=['status', 'current_period_end'])
            # Extend institution plan expiry
            inst = sub.institution
            inst.plan_expires_at = sub.current_period_end
            inst.save(update_fields=['plan_expires_at'])

    return {
        'type': event.type,
        'subscription_id': sub.id,
        'status': sub.status,
        'stripe_subscription_id': sub_id,
    }

