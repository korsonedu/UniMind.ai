"""PWA Web Push 发送工具。"""
import json
import logging
import os
from django.conf import settings

logger = logging.getLogger(__name__)

VAPID_PRIVATE_KEY = getattr(settings, 'VAPID_PRIVATE_KEY', os.getenv('VAPID_PRIVATE_KEY', ''))
VAPID_CLAIMS_EMAIL = getattr(settings, 'VAPID_CLAIMS_EMAIL', os.getenv('VAPID_CLAIMS_EMAIL', 'noreply@unimind.ai'))


def send_push_notification(user, title: str, body: str, link: str = '') -> int:
    """向用户的所有浏览器推送通知。返回成功发送数。"""
    if not VAPID_PRIVATE_KEY:
        logger.warning('VAPID_PRIVATE_KEY not configured, skip push')
        return 0

    from users.models import PushSubscription
    from pywebpush import webpush, WebPushException

    subs = PushSubscription.objects.filter(user=user)
    if not subs:
        return 0

    payload = json.dumps({'title': title, 'body': body, 'link': link or '/'})

    sent = 0
    for sub in subs:
        try:
            webpush(
                subscription_info={
                    'endpoint': sub.endpoint,
                    'keys': {'p256dh': sub.p256dh, 'auth': sub.auth},
                },
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={'sub': f'mailto:{VAPID_CLAIMS_EMAIL}'},
                timeout=10,
            )
            sent += 1
        except WebPushException as e:
            logger.warning(f'Push failed for {user.id} endpoint {sub.endpoint[:50]}: {e}')
            if e.response and e.response.status_code in (404, 410):
                sub.delete()  # 过期订阅
        except Exception as e:
            logger.warning(f'Push error for {user.id}: {e}')

    return sent
