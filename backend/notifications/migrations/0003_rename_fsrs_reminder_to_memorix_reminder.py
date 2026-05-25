# Rename fsrs_reminder to memorix_reminder in notification types

from django.db import migrations


def rename_fsrs_reminder(apps, schema_editor):
    """Update existing notification ntype from fsrs_reminder to memorix_reminder."""
    Notification = apps.get_model('notifications', 'Notification')
    Notification.objects.filter(ntype='fsrs_reminder').update(ntype='memorix_reminder')


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0002_alter_notification_is_read_alter_notification_ntype'),
    ]

    operations = [
        migrations.RunPython(rename_fsrs_reminder, migrations.RunPython.noop),
    ]
