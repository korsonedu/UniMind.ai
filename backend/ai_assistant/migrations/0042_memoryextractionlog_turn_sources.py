from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ai_assistant', '0041_identify_xiaoyu')]

    operations = [
        migrations.AddField('memoryextractionlog', 'source_message_id', models.PositiveBigIntegerField(null=True, blank=True)),
        migrations.AddField('memoryextractionlog', 'answer_message_id', models.PositiveBigIntegerField(null=True, blank=True)),
    ]
