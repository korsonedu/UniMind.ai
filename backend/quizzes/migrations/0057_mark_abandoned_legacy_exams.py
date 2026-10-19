from datetime import timedelta

from django.db import migrations
from django.db.models import Count
from django.utils import timezone


def mark_abandoned_exams(apps, schema_editor):
    exams = apps.get_model('quizzes', 'QuizExam').objects
    abandoned = exams.filter(
        grading_completed_at__isnull=True,
        created_at__lt=timezone.now() - timedelta(hours=1),
    ).annotate(stored_results=Count('results')).filter(stored_results=0)
    exams.filter(pk__in=abandoned.values('pk')).update(
        status='failed', last_error='历史练习未完成批改，未保存可恢复的作答，请重新开始练习。')


class Migration(migrations.Migration):
    dependencies = [('quizzes', '0056_backfill_exam_grading_state')]
    operations = [migrations.RunPython(mark_abandoned_exams, migrations.RunPython.noop)]
