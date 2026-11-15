from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [('users', '0077_login_session')]
    operations = [
        migrations.AddField(
            model_name='loginsession', name='last_seen_at',
            field=models.DateTimeField(default=timezone.now),
        ),
    ]
