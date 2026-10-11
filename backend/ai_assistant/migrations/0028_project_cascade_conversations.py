from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('ai_assistant', '0027_project_instructions')]

    operations = [
        migrations.AlterField(
            model_name='conversation',
            name='project',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='conversations', to='ai_assistant.conversationproject'),
        ),
    ]
