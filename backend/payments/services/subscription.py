"""
Subscription business layer — gateway-agnostic lifecycle management.

All functions operate on the Subscription model directly; gateway
communication happens in the view layer via gateway_router.
"""
import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from payments.models import Subscription
from users.services.membership import activate_membership, downgrade_to_free

logger = logging.getLogger(__name__)

DURATION_DAYS = {'monthly': 30, 'annual': 365}


def _get_institution_owner(inst):
    """Return the institution owner user, or None."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.filter(institution=inst, institution_role='owner').first()


def create_subscription(*, institution, plan: str, billing_cycle: str, gateway: str) -> Subscription:
    """Create a pending subscription record. Activated later via webhook callback."""
    now = timezone.now()
    duration = DURATION_DAYS.get(billing_cycle, 30)
    return Subscription.objects.create(
        institution=institution,
        plan=plan,
        billing_cycle=billing_cycle,
        gateway=gateway,
        status='pending',
        current_period_start=now,
        current_period_end=now + timedelta(days=duration),
    )


def activate_subscription(sub: Subscription, gateway_subscription_id: str, gateway_customer_id: str = '') -> Subscription:
    """Mark subscription active and activate membership. Called on successful checkout webhook."""
    with transaction.atomic():
        sub.status = 'active'
        sub.gateway_subscription_id = gateway_subscription_id
        if gateway_customer_id:
            sub.gateway_customer_id = gateway_customer_id
        sub.save(update_fields=['status', 'gateway_subscription_id', 'gateway_customer_id', 'updated_at'])

        # Activate membership for the institution owner
        owner = _get_institution_owner(sub.institution)
        if owner:
            duration = DURATION_DAYS.get(sub.billing_cycle, 30)
            activate_membership(owner, sub.plan, duration, source=f'subscription:{sub.gateway}')

    logger.info("Subscription %s activated for institution %s", sub.id, sub.institution_id)
    return sub


def cancel_subscription(sub: Subscription) -> Subscription:
    """Mark subscription as canceled."""
    now = timezone.now()
    sub.status = 'canceled'
    sub.canceled_at = now
    sub.save(update_fields=['status', 'canceled_at', 'updated_at'])
    logger.info("Subscription %s canceled", sub.id)
    return sub


def renew_subscription(sub: Subscription, new_period_end) -> Subscription:
    """Extend the current period. Called on renewal webhook."""
    sub.current_period_end = new_period_end
    sub.status = 'active'
    sub.save(update_fields=['current_period_end', 'status', 'updated_at'])
    logger.info("Subscription %s renewed until %s", sub.id, new_period_end)
    return sub


def expire_subscription(sub: Subscription) -> Subscription:
    """Mark subscription expired, downgrade institution plan and owner membership."""
    with transaction.atomic():
        sub.status = 'expired'
        sub.save(update_fields=['status', 'updated_at'])

        inst = sub.institution
        inst.plan = 'free'
        inst.plan_expires_at = None
        inst.save(update_fields=['plan', 'plan_expires_at', 'updated_at'])

        # Also downgrade the institution owner's personal membership
        owner = _get_institution_owner(inst)
        if owner and owner.is_member:
            downgrade_to_free(owner)

    logger.info("Subscription %s expired, institution %s downgraded to free", sub.id, inst.id)
    return sub


def get_active_subscription(institution):
    """Return the active subscription for an institution, or None."""
    return Subscription.objects.filter(
        institution=institution,
        status='active',
    ).order_by('-created_at').first()
