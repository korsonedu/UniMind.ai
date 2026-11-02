import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


def session_key():
    return secrets.token_hex(32)


def session_expiry():
    return timezone.now() + timedelta(days=30)


class LoginSession(models.Model):
    key = models.CharField(max_length=64, primary_key=True, default=session_key, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='login_sessions')
    expires_at = models.DateTimeField(default=session_expiry)
    account_session_version = models.PositiveIntegerField()

    @classmethod
    def issue(cls, user):
        return cls.objects.create(user=user, account_session_version=user.account_session_version)

    @classmethod
    def resolve(cls, key):
        session = cls.objects.select_related('user').filter(key=key, expires_at__gt=timezone.now()).first() if key else None
        if (session and session.user.is_active
                and session.account_session_version == session.user.account_session_version):
            return session
        return None
