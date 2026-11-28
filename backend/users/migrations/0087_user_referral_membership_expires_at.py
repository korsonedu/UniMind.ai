from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('users', '0086_aiusagereservation_conversation_id')]

    operations = [
        migrations.AddField(
            model_name='user',
            name='referral_membership_expires_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='邀请会员到期时间'),
        ),
    ]
