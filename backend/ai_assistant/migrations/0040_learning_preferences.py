from django.db import migrations, models


def retain_existing_plans(apps, schema_editor):
    states = apps.get_model('ai_assistant', 'ProjectLearning').objects.using(schema_editor.connection.alias)
    states.exclude(plan={}).update(planning_enabled=True)
    states.update(followup_at=None, followup_text='')


class Migration(migrations.Migration):
    dependencies = [('ai_assistant', '0039_teaching_sidecar_6ab')]
    operations = [
        migrations.AddField(model_name='projectlearning', name='planning_enabled', field=models.BooleanField(default=False)),
        migrations.AddField(model_name='projectlearning', name='reminders_enabled', field=models.BooleanField(default=False)),
        migrations.RunPython(retain_existing_plans, migrations.RunPython.noop),
    ]
