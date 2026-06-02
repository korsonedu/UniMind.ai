import logging
from datetime import timedelta

from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone

logger = logging.getLogger(__name__)

User = get_user_model()


@shared_task
def check_membership_expiry():
    """每日检查会员到期，自动降级。"""
    now = timezone.now()

    expired = User.objects.filter(
        is_member=True,
        membership_expires_at__lt=now,
    )
    count = expired.update(
        is_member=False,
        membership_tier='free',
        membership_expires_at=None,
        membership_source=None,
    )

    if count > 0:
        logger.info("check_membership_expiry: %s users downgraded", count)


@shared_task
def notify_trial_expiring():
    """提前 3 天提醒试用即将到期，提前 1 天再次提醒。"""
    from notifications.models import Notification

    now = timezone.now()
    for days_left in (3, 1):
        target_date = now + timedelta(days=days_left)
        users = User.objects.filter(
            is_member=True,
            membership_source='trial',
            membership_expires_at__date=target_date.date(),
        )
        for user in users:
            Notification.objects.create(
                recipient=user,
                ntype='system',
                title='试用即将到期' if days_left == 3 else '试用明天到期',
                content=f'您的 {days_left} 天免费试用即将结束，到期后将降级为 Free 方案。升级方案即可保留全部功能。',
                link='/settings/billing',
            )
        if users:
            logger.info("notify_trial_expiring: %s users notified for %s days left", users.count(), days_left)


@shared_task
def send_membership_expiry_reminders():
    """提前 7/3/1 天给付费会员发邮件提醒续费。"""
    from core.email_service import send_email

    now = timezone.now()
    for days_left in (7, 3, 1):
        target_date = now + timedelta(days=days_left)
        users = User.objects.filter(
            is_member=True,
            membership_source='payment',
            membership_expires_at__date=target_date.date(),
        )
        for user in users:
            tier_labels = {'starter': 'Starter', 'growth': 'Growth', 'enterprise': 'Enterprise'}
            label = tier_labels.get(user.membership_tier, user.membership_tier)
            subject = f'UniMind {label} 版即将到期（{days_left}天后）'
            body = (
                f'您好，{user.nickname or user.email}：\n\n'
                f'您的 UniMind {label} 会员将于 '
                f'{user.membership_expires_at.strftime("%Y年%m月%d日")} 到期，剩余 {days_left} 天。\n\n'
                f'到期后将降级为 Free 方案，部分功能将受限。\n'
                f'请登录 UniMind 及时续费以保持服务不中断。\n\n'
                f'UniMind.ai 团队'
            )
            try:
                send_email(user.email, subject, body)
            except Exception:
                logger.warning("send_membership_expiry_reminders: failed to email %s", user.email, exc_info=True)
        if users:
            logger.info("send_membership_expiry_reminders: %s emails sent for %s days left", users.count(), days_left)


@shared_task
def check_performance_drops():
    """每日运行：检测各机构 KP 正确率本周 vs 上周下降 >15% → 通知老师/机构主。"""
    from django.db.models import Sum
    from notifications.models import Notification
    from users.models import Institution
    from quizzes.models import UserQuestionStatus

    now = timezone.now()
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    institutions = Institution.objects.filter(is_active=True)

    for inst in institutions:
        student_ids = list(
            inst.students.filter(institution_role='student').values_list('id', flat=True)
        )
        if not student_ids:
            continue

        # Per-KP, per-period aggregation
        qs = (
            UserQuestionStatus.objects
            .filter(
                user_id__in=student_ids,
                question__knowledge_point__isnull=False,
                last_review__gte=two_weeks_ago,
            )
            .values('question__knowledge_point__id', 'question__knowledge_point__name')
        )

        kp_data: dict[int, dict] = {}
        for row in qs:
            kp_id = row['question__knowledge_point__id']
            kp_data.setdefault(kp_id, {
                'name': row['question__knowledge_point__name'] or '',
                'tw_reps': 0, 'tw_lapses': 0, 'lw_reps': 0, 'lw_lapses': 0,
            })

        # Get detailed per-period data
        detail_qs = (
            UserQuestionStatus.objects
            .filter(
                user_id__in=student_ids,
                question__knowledge_point__isnull=False,
                last_review__gte=two_weeks_ago,
            )
            .values(
                'question__knowledge_point__id',
                'question__knowledge_point__name',
                'last_review__date',
            )
            .annotate(
                day_reps=Sum('reps'),
                day_lapses=Sum('lapses'),
            )
        )

        kp_detail: dict[int, dict] = {}
        for row in detail_qs:
            kp_id = row['question__knowledge_point__id']
            date = row['last_review__date']
            kp_detail.setdefault(kp_id, {
                'name': row['question__knowledge_point__name'] or '',
                'tw_reps': 0, 'tw_lapses': 0, 'lw_reps': 0, 'lw_lapses': 0,
            })
            if date >= week_ago.date():
                kp_detail[kp_id]['tw_reps'] += row['day_reps'] or 0
                kp_detail[kp_id]['tw_lapses'] += row['day_lapses'] or 0
            else:
                kp_detail[kp_id]['lw_reps'] += row['day_reps'] or 0
                kp_detail[kp_id]['lw_lapses'] += row['day_lapses'] or 0

        # Detect drops > 15%
        alerts = []
        for kp_id, data in kp_detail.items():
            tw_total = data['tw_reps'] + data['tw_lapses']
            lw_total = data['lw_reps'] + data['lw_lapses']
            if tw_total < 5 or lw_total < 5:
                continue
            tw_rate = data['tw_reps'] / tw_total
            lw_rate = data['lw_reps'] / lw_total
            drop = lw_rate - tw_rate
            if drop > 0.15:
                alerts.append({
                    'kp_name': data['name'],
                    'drop': round(drop * 100, 1),
                    'this_week_rate': round(tw_rate * 100, 1),
                    'last_week_rate': round(lw_rate * 100, 1),
                })

        if not alerts:
            continue

        # Notify all teachers + owners of this institution
        staff = inst.students.filter(institution_role__in=('teacher', 'owner'))
        for alert in alerts[:5]:  # Cap at 5 alerts per institution per day
            title = f"班级知识点下降告警：{alert['kp_name']}"
            content = (
                f"「{alert['kp_name']}」本周正确率 {alert['this_week_rate']}%，"
                f"较上周 {alert['last_week_rate']}% 下降了 {alert['drop']} 个百分点。"
                f"建议关注并安排针对性练习。"
            )
            for staff_user in staff:
                Notification.objects.create(
                    recipient=staff_user,
                    ntype='performance_alert',
                    title=title,
                    content=content,
                    link='/management/analytics',
                )

        logger.info(
            "check_performance_drops: institution=%s alerts=%d",
            inst.name, len(alerts),
        )
