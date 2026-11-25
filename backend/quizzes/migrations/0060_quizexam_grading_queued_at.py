from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('quizzes', '0059_quizexam_requires_ulr')]

    operations = [
        migrations.AddField(
            model_name='quizexam',
            name='grading_queued_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
