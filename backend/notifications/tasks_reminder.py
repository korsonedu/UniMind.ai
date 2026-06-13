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


@shared_task
def send_due_review_reminders():
    """定期检查学生到期复习题，超过阈值时通知"""
    from users.models import InstitutionNotificationConfig
    from ai_assistant.services.memory_system import MemorySystem
    from core.email_service import send_email

    configs = InstitutionNotificationConfig.objects.filter(
        enabled=True
    ).select_related('institution')

    sent = 0
    for config in configs:
        institution = config.institution
        students = institution.students.filter(
            institution_role='student', is_active=True
        )

        for student in students:
            due = MemorySystem.query_due_reviews(student, limit=50, institution=institution)
            due_count = due.get('due_count', 0)

            if due_count < config.due_threshold:
                continue

            kp_names = list(set(
                r.get('kp_name', '') for r in due.get('reviews', [])[:5] if r.get('kp_name')
            ))
            kp_hint = '、'.join(kp_names[:3]) if kp_names else '多个知识点'

            subject = f'UniMind 复习提醒：你有 {due_count} 道题到期了'
            body = (
                f'Hi {student.get_full_name() or student.username}，\n\n'
                f'你有 {due_count} 道到期复习题，涉及 {kp_hint}。\n\n'
                f'打开 UniMind 和小宇对话，他会帮你开始复习。\n\n'
                f'UniMind.ai'
            )

            try:
                if config.channel == 'email':
                    send_email(student.email, subject, body)
                    sent += 1
            except Exception:
                pass

        # Also notify institution contact email as summary
        if sent > 0 and config.channel == 'email':
            summary_subject = f'UniMind 复习提醒汇总：{sent} 名学生有待复习题目'
            summary_body = (
                f'尊敬的 {institution.contact_name}，\n\n'
                f'您的机构「{institution.name}」共有 {sent} 名学生收到了到期复习提醒。\n\n'
                f'登录 UniMind 工作台查看详情。\n\n'
                f'UniMind.ai'
            )
            try:
                send_email(institution.contact_email, summary_subject, summary_body)
            except Exception:
                pass

    return f'Sent {sent} due review reminders'
