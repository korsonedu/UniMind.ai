"""Short-lived callbacks for one server-owned DSH task, never a site login."""
from django.contrib.auth import get_user_model
from django.core import signing
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from users.models import AIUsageReservation


SALT = 'unimind.dsh.readonly-task.v1'
MAX_AGE = 120


def make_task_token(user, reservation=None, *, chat_context=None):
    return signing.dumps({'user': user.pk, 'purpose': SALT,
                          'reservation': reservation.pk if reservation else None,
                          'attempt': str(reservation.attempt_id) if reservation else '',
                          'chat_context': chat_context}, salt=SALT)


class DshTaskAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return 'DSH'

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts or parts[0].lower() != b'dsh':
            return None
        try:
            if len(parts) != 2:
                raise ValueError()
            claims = signing.loads(parts[1].decode(), salt=SALT, max_age=MAX_AGE)
            if not isinstance(claims, dict) or claims.get('purpose') != SALT:
                raise ValueError()
            user = get_user_model().objects.get(pk=claims['user'], is_active=True)
            if claims.get('reservation'):
                if not AIUsageReservation.objects.filter(pk=claims['reservation'], user=user, status='pending',
                                                       attempt_id=claims['attempt']).exists():
                    raise ValueError()
            elif getattr(request.resolver_match, 'url_name', '') != 'dsh-context':
                raise ValueError()
        except (signing.BadSignature, ValueError, TypeError, KeyError, UnicodeError, get_user_model().DoesNotExist):
            raise AuthenticationFailed('DSH 任务凭据无效或已失效。') from None
        return user, claims
