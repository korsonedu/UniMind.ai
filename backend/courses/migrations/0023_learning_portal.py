import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('courses', '0022_delete_teachingplan'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name='videoprogress', name='duration', field=models.FloatField(default=0, help_text='视频时长（秒）')),
        migrations.CreateModel(name='LearningActivity', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('event_id', models.UUIDField(default=uuid.uuid4)),
            ('watched_seconds', models.FloatField(default=0)),
            ('completed', models.BooleanField(default=False)),
            ('elo_earned', models.IntegerField(default=0)),
            ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
            ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='courses.course')),
            ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ], options={'constraints': [models.UniqueConstraint(fields=('user', 'event_id'), name='unique_course_learning_event')]}),
        migrations.CreateModel(name='WatchLater', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='courses.course')),
            ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ], options={'ordering': ['created_at', 'pk'], 'constraints': [models.UniqueConstraint(fields=('user', 'course'), name='unique_course_watch_later')]}),
    ]
