from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('courses', '0027_module_subject'),
    ]

    operations = [
        migrations.AlterField(
            model_name='coursetag',
            name='institution',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='course_tags', to='users.institution'),
        ),
        migrations.AddConstraint(
            model_name='coursetag',
            constraint=models.UniqueConstraint(condition=models.Q(institution__isnull=True), fields=('slug',), name='unique_global_course_tag_slug'),
        ),
    ]
