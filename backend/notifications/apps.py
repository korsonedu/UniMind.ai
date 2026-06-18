from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'notifications'
    verbose_name = '站内通知'

    def ready(self):
        from django.db.models.signals import post_save
        from django.dispatch import receiver
        from notifications.models import Notification

        # 触发邮件通知的事件类型
        _EMAIL_TYPES = {'system', 'performance_alert', 'join_request'}

        @receiver(post_save, sender=Notification)
        def _on_notification(sender, instance, created, **kwargs):
            if created and instance.ntype in _EMAIL_TYPES:
                from notifications.tasks_reminder import send_notification_email
                send_notification_email.delay(instance.id)
