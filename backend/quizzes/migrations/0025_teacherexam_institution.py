# Generated manually for institution isolation

from django.db import migrations


def add_teacherexam_columns(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor == 'sqlite':
        return  # columns already exist locally

    # 0024 already creates these columns on a fresh database.
    schema_editor.execute(
        "ALTER TABLE quizzes_teacherexam "
        "ADD COLUMN IF NOT EXISTS created_by_id bigint NULL "
        "REFERENCES users_user(id) ON DELETE SET NULL"
    )
    schema_editor.execute(
        "ALTER TABLE quizzes_teacherexam "
        "ADD COLUMN IF NOT EXISTS institution_id bigint NULL "
        "REFERENCES users_institution(id) ON DELETE SET NULL"
    )


class Migration(migrations.Migration):

    dependencies = [
        ('quizzes', '0024_remove_contentpipelinetask_quizzes_con_status_21f402_idx_and_more'),
    ]

    operations = [
        migrations.RunPython(add_teacherexam_columns, migrations.RunPython.noop),
    ]
