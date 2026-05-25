# Rename all FSRS references to Memorix

from django.conf import settings
from django.db import migrations, models


def rename_fsrs_rating_in_details(apps, schema_editor):
    """Rename 'fsrs_rating' key to 'memorix_rating' in ExamQuestionResult.details JSON."""
    ExamQuestionResult = apps.get_model('quizzes', 'ExamQuestionResult')
    for result in ExamQuestionResult.objects.filter(details__has_key='fsrs_rating'):
        details = result.details
        details['memorix_rating'] = details.pop('fsrs_rating')
        result.details = details
        result.save(update_fields=['details'])


class Migration(migrations.Migration):

    dependencies = [
        ('quizzes', '0033_alter_contentpipelinetask_status_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # RenameModel handles both Django internal model name + DB table rename
        migrations.RenameModel(
            old_name='FSRSProfile',
            new_name='MemorixProfile',
        ),
        migrations.RenameModel(
            old_name='FSRSOptimizationLog',
            new_name='MemorixOptimizationLog',
        ),
        # Update related_names after model rename
        migrations.AlterField(
            model_name='memorixprofile',
            name='user',
            field=models.OneToOneField(
                on_delete=models.CASCADE,
                related_name='memorix_profile',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='memorixoptimizationlog',
            name='user',
            field=models.ForeignKey(
                on_delete=models.CASCADE,
                related_name='memorix_optimization_logs',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        # Data migration: rename fsrs_rating key in ExamQuestionResult.details
        migrations.RunPython(rename_fsrs_rating_in_details, migrations.RunPython.noop),
    ]
