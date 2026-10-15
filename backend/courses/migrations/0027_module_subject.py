from django.db import migrations, models


def populate_subjects(apps, schema_editor):
    Course = apps.get_model('courses', 'Course')
    Module = apps.get_model('courses', 'CourseModule')
    Point = apps.get_model('quizzes', 'KnowledgePoint')
    points = {point['id']: point for point in Point.objects.values('id', 'name', 'subject', 'parent_id')}
    def label(point_id):
        seen, name = set(), ''
        while point_id and point_id not in seen:
            seen.add(point_id)
            point = points.get(point_id)
            if not point:
                return ''
            if point['subject']:
                return point['subject'].strip()
            name, point_id = point['name'], point['parent_id']
        return name
    for module in Module.objects.all().iterator():
        labels = {label(pk) for pk in Course.objects.filter(module=module).values_list('knowledge_point_id', flat=True)}
        if len(labels) == 1 and '' not in labels:
            Module.objects.filter(pk=module.pk).update(subject=labels.pop())


class Migration(migrations.Migration):
    dependencies = [('courses', '0026_personal_learning_access'), ('quizzes', '0032_alter_knowledgepoint_subject')]
    operations = [
        migrations.AddField(model_name='coursemodule', name='subject', field=models.CharField(blank=True, db_index=True, default='', max_length=100, verbose_name='学科')),
        migrations.RemoveConstraint(model_name='coursemodule', name='unique_institution_course_module'),
        migrations.RemoveConstraint(model_name='coursemodule', name='unique_global_course_module'),
        migrations.AddConstraint(model_name='coursemodule', constraint=models.UniqueConstraint(fields=['institution', 'subject', 'name'], name='unique_institution_subject_module')),
        migrations.AddConstraint(model_name='coursemodule', constraint=models.UniqueConstraint(fields=['subject', 'name'], condition=models.Q(institution__isnull=True), name='unique_global_subject_module')),
        migrations.RunPython(populate_subjects, migrations.RunPython.noop),
    ]
