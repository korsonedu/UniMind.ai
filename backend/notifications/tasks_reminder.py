from datetime import timedelta
from celery import shared_task
from django.utils import timezone


@shared_task
def send_expiry_reminders():
    """每天检查机构到期情况，到期前 7/3/1 天发送邮件提醒"""
    from users.models import Institution
    from core.email_service import send_email

    now = timezone.now()
    institutions = Institution.objects.filter(is_active=True, plan_expires_at__isnull=False)

    sent = 0
    for inst in institutions:
        days_left = (inst.plan_expires_at - now).days
        if days_left not in (7, 3, 1):
            continue

        subject = f'UniMind {inst.get_plan_display()} 版即将到期（{days_left}天后）'
        body = (
            f'尊敬的 {inst.contact_name}，\n\n'
            f'您的机构「{inst.name}」当前 {inst.get_plan_display()} 版将于 '
            f'{inst.plan_expires_at.strftime("%Y年%m月%d日")} 到期，剩余 {days_left} 天。\n\n'
            f'到期后学员将无法使用部分功能。请及时续费以保持服务不中断。\n\n'
            f'如需续费或升级版本，请登录 UniMind 管理后台操作。\n\n'
            f'UniMind.ai 团队'
        )

        try:
            send_email(inst.contact_email, subject, body)
            sent += 1
        except Exception:
            pass

    return f'Sent {sent} expiry reminders'
