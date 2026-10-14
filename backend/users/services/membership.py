from datetime import timedelta

from django.utils import timezone

DEFAULT_TRIAL_DAYS = 7


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
    user.personal_plan = plan
    user.membership_expires_at = expires_at
    user.membership_source = source
    user.save(update_fields=['is_member', 'personal_plan', 'membership_tier', 'membership_expires_at', 'membership_source'])

    from django.core.cache import cache
    cache.delete(f'effective_plan:{user.pk}')
    cache.delete(f'inst:features:u{user.pk}:i{user.institution_id or 0}')


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
    user.personal_plan = 'free'
    user.membership_expires_at = None
    user.membership_source = None
    user.save(update_fields=['is_member', 'personal_plan', 'membership_tier', 'membership_expires_at', 'membership_source'])
