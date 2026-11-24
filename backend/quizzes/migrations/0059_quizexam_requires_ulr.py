from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('quizzes', '0058_exam_ui_language')]

    operations = [
        migrations.AddField(
            model_name='quizexam',
            name='requires_ulr',
            field=models.BooleanField(default=False),
        ),
    ]
