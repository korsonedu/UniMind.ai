from django.test import SimpleTestCase

from school_system.celery import app


class NotificationTaskDiscoveryTests(SimpleTestCase):
    def test_default_worker_registers_notification_email(self):
        app.loader.import_default_modules()
        self.assertIn('notifications.tasks_reminder.send_notification_email', app.tasks)
