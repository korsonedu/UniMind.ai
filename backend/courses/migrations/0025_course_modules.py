import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('courses', '0024_learning_goal'),
    ]

    operations = [
        migrations.CreateModel(
            name='CourseModule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='模块名称')),
                ('description', models.TextField(blank=True, verbose_name='模块简介')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='显示顺序')),
                ('institution', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='course_modules', to='users.institution')),
            ],
            options={
                'ordering': ['sort_order', 'id'],
                'constraints': [
                    models.UniqueConstraint(fields=('institution', 'name'), name='unique_institution_course_module'),
                    models.UniqueConstraint(condition=models.Q(institution__isnull=True), fields=('name',), name='unique_global_course_module'),
                ],
            },
        ),
        migrations.AddField(
            model_name='course',
            name='module',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='courses', to='courses.coursemodule', verbose_name='所属模块'),
        ),
    ]
