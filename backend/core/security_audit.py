"""Record security events without passwords, verification codes or session credentials."""
import ipaddress
import json
import logging

from core.models import SecurityAuditLog
from core.rate_limit import _get_client_ip

logger = logging.getLogger('core.security')


def record_security_event(event_type, *, request=None, user=None, detail=''):
    ip = _get_client_ip(request) if request is not None else None
    try:
        ip = str(ipaddress.ip_address(ip)) if ip else None
    except ValueError:
        ip = None
    event = SecurityAuditLog.objects.create(
        event_type=event_type, user=user, ip_address=ip, detail=detail,
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:255] if request is not None else '',
        request_id=str(getattr(request, 'request_id', ''))[:64],
    )
    logger.info('security_event %s', json.dumps({
        'id': event.pk, 'event': event_type, 'user_id': event.user_id,
        'ip': ip, 'request_id': event.request_id, 'detail': detail,
    }, ensure_ascii=False))
    return event
