from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ai_assistant', '0045_auxiliary_work_claims')]

    operations = [
        migrations.AddField(model_name='pendingmemoryextraction', name='provider_retry_used',
                            field=models.BooleanField(default=False, db_default=False)),
    ]
