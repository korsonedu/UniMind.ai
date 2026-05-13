from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0022_plan_invite_code'),
    ]

    operations = [
        migrations.AddField(
            model_name='planinvitecode',
            name='duration_days',
            field=models.IntegerField(default=30, verbose_name='有效天数（0=永久）'),
        ),
    ]
