from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from payments.models import ReferralCode, ReferralRecord
from users.models import User


@transaction.atomic
def record_referral_signup(referee, code):
    referral = ReferralCode.objects.filter(code=code, user__is_active=True).exclude(user=referee).first()
    if not referral:
        return
    _, created = ReferralRecord.objects.get_or_create(
        referrer_id=referral.user_id, referee=referee, defaults={'reward_granted': True},
    )
    if not created:
        return

    now = timezone.now()
    recipients = User.objects.select_for_update().filter(pk__in=[referral.user_id, referee.pk]).order_by('pk')
    for user in recipients:
        previous = user.referral_membership_expires_at
        paid_until = user.membership_expires_at if user.is_member else None
        user.referral_membership_expires_at = max(now, previous or now, paid_until or now) + timedelta(days=3)
        user.save(update_fields=['referral_membership_expires_at'])
    ReferralCode.objects.filter(pk=referral.pk).update(signups=F('signups') + 1)
