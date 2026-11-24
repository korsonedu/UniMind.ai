import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ai_assistant', '0043_pendingmemoryextraction')]

    operations = [
        migrations.CreateModel(
            name='PendingConversationTitle',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('expected_title', models.CharField(max_length=120)),
                ('dispatch_after', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('answer_message', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                    related_name='+', to='ai_assistant.aichatmessage')),
                ('conversation', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                    related_name='+', to='ai_assistant.conversation')),
            ],
        ),
    ]
