from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ai_assistant', '0044_pendingconversationtitle')]

    operations = [
        migrations.AddField(model_name='pendingmemoryextraction', name='running_until',
                            field=models.DateTimeField(null=True)),
        migrations.AddField(model_name='pendingconversationtitle', name='running_until',
                            field=models.DateTimeField(null=True)),
    ]
