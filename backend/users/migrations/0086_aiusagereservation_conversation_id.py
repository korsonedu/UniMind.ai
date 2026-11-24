from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('users', '0085_remove_elo_ordering')]

    operations = [
        migrations.AddField(
            model_name='aiusagereservation',
            name='conversation_id',
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.AddConstraint(
            model_name='aiusagereservation',
            constraint=models.UniqueConstraint(fields=('user', 'conversation_id'),
                condition=models.Q(status='pending', conversation_id__isnull=False), name='unique_pending_ai_conversation'),
        ),
    ]
