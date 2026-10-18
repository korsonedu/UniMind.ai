from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def mark_completed_exams(apps, schema_editor):
    exam_model = apps.get_model('quizzes', 'QuizExam')
    exam_model.objects.using(schema_editor.connection.alias).filter(max_score__gt=0).update(
        grading_completed_at=models.F('created_at'),
    )


class Migration(migrations.Migration):
    dependencies = [
        ('quizzes', '0053_remove_assignmentquestion_assignment_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='memorixprofile',
            name='optimizer_state',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='quizexam',
            name='grading_completed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(mark_completed_exams, migrations.RunPython.noop),
        migrations.CreateModel(
            name='PracticeSubmission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('session_id', models.UUIDField(unique=True)),
                ('answers_hash', models.CharField(max_length=64)),
                ('response', models.JSONField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='practice_submissions', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
