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
                # PWA push as parallel channel
                from notifications.push import send_push_notification
                push_sent = send_push_notification(
                    student, title=subject, body=body, link='/xiaoyu',
                )
                if push_sent > 0:
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


@shared_task
def send_student_health_alerts():
    """每周计算所有学生健康分、保存快照、通知管理员高风险学生。"""
    from users.models import Institution
    from quizzes.services.student_health import compute_student_health, compute_institution_student_health
    from quizzes.models import StudentHealthSnapshot
    from notifications.models import Notification
    from core.email_service import send_email

    now = timezone.now()
    today = now.date()
    alert_count = 0

    for inst in Institution.objects.filter(is_active=True):
        results = compute_institution_student_health(inst)

        critical_students = []
        for r in results:
            # 保存每日快照
            StudentHealthSnapshot.objects.update_or_create(
                user_id=r['student_id'],
                snapshot_date=today,
                defaults={
                    'institution': inst,
                    'score': r['score'],
                    'level': r['level'],
                    'components': r['components'],
                    'details': r['details'],
                },
            )

            if r['level'] == 'critical':
                critical_students.append(r)

        # 通知机构管理员
        if critical_students and inst.contact_email:
            names = '、'.join(s['name'] for s in critical_students[:5])
            more = f' 等{len(critical_students)}人' if len(critical_students) > 5 else ''
            subject = f'UniMind 学情预警：{len(critical_students)} 名学生处于危险状态'
            body = (
                f'尊敬的 {inst.contact_name}，\n\n'
                f'以下学生学习健康度较低，建议关注：{names}{more}\n\n'
                f'登录 UniMind 工作台 → 机构仪表盘查看详情。\n\n'
                f'UniMind.ai'
            )
            try:
                send_email(inst.contact_email, subject, body)
                alert_count += 1
            except Exception:
                pass

            # 为每个危险学生创建站内通知
            for s in critical_students[:10]:
                try:
                    Notification.objects.create(
                        recipient_id=s['student_id'],
                        ntype='system',
                        title='学习健康度提醒',
                        content=f'你已连续多日未活跃学习，建议尽快开始复习。当前健康分：{s["score"]}',
                        link='/xiaoyu',
                    )
                    alert_count += 1
                except Exception:
                    pass

    return f'Saved {today} health snapshots, sent {alert_count} alerts'


@shared_task
def send_notification_email(notification_id: int):
    """为新创建的站内通知发送邮件（收件人开启了 email_notifications）。"""
    from notifications.models import Notification
    from core.email_service import send_email

    try:
        notif = Notification.objects.select_related('recipient').get(id=notification_id)
    except Notification.DoesNotExist:
        return f'Notification {notification_id} not found'

    user = notif.recipient
    if not user.email or not getattr(user, 'email_notifications', True):
        return f'User {user.id} email notifications disabled or no email'

    subject = f'UniMind — {notif.title}'
    body = f'{notif.content}\n\n— UniMind 通知'
    if notif.link:
        body += f'\n查看详情：{notif.link}'

    try:
        send_email(user.email, subject, body)
        return f'Email sent to {user.email} for notification {notification_id}'
    except Exception as e:
        return f'Failed to send email: {e}'
