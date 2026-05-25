from datetime import timedelta

from django.utils import timezone

from users.models import Institution, InstitutionAuditLog

DEFAULT_TRIAL_DAYS = 14


def activate_membership(user, plan, duration_days, source='payment'):
    """Single entry point for membership activation.

    Args:
        user: User instance
        plan: 'starter' | 'growth' | 'enterprise'
        duration_days: 0 = permanent, >0 = expires after N days
        source: 'payment' | 'invite_code' | 'admin'
    """
    now = timezone.now()
    expires_at = None if duration_days <= 0 else now + timedelta(days=duration_days)

    user.is_member = True
    user.membership_tier = plan
    user.membership_expires_at = expires_at
    user.trial_ends_at = None  # paid activation overrides trial
    user.save(update_fields=['is_member', 'membership_tier', 'membership_expires_at', 'trial_ends_at'])

    # Upgrade affiliated institution if applicable
    inst = user.institution
    if inst and inst.plan != plan:
        old_plan = inst.plan
        inst.plan = plan
        inst.plan_expires_at = expires_at
        inst.save(update_fields=['plan', 'plan_expires_at', 'updated_at'])
        InstitutionAuditLog.objects.create(
            institution=inst,
            operator=user,
            action='purchase_plan',
            detail=f'{old_plan} → {plan} (expires: {expires_at}) via {source}',
        )


def extend_membership(user, extra_days):
    """Extend existing membership by N days from today."""
    if user.membership_expires_at is None:
        return
    now = timezone.now()
    base = max(user.membership_expires_at, now)
    user.membership_expires_at = base + timedelta(days=extra_days)
    user.save(update_fields=['membership_expires_at'])


def downgrade_to_free(user):
    user.is_member = False
    user.membership_tier = 'free'
    user.membership_expires_at = None
    user.trial_ends_at = None
    user.save(update_fields=['is_member', 'membership_tier', 'membership_expires_at', 'trial_ends_at'])
