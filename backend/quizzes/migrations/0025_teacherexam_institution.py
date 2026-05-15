# Generated manually for institution isolation

from django.db import migrations


def add_teacherexam_columns(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor == 'sqlite':
        return  # columns already exist locally

    cursor = schema_editor.connection.cursor()
    cursor.execute(
        "ALTER TABLE quizzes_teacherexam "
        "ADD COLUMN created_by_id bigint NULL "
        "REFERENCES users_user(id) ON DELETE SET NULL"
    )
    cursor.execute(
        "ALTER TABLE quizzes_teacherexam "
        "ADD COLUMN institution_id bigint NULL "
        "REFERENCES users_institution(id) ON DELETE SET NULL"
    )


def remove_teacherexam_columns(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor == 'sqlite':
        return
    cursor = schema_editor.connection.cursor()
    cursor.execute("ALTER TABLE quizzes_teacherexam DROP COLUMN IF EXISTS created_by_id")
    cursor.execute("ALTER TABLE quizzes_teacherexam DROP COLUMN IF EXISTS institution_id")


class Migration(migrations.Migration):

    dependencies = [
        ('quizzes', '0024_remove_contentpipelinetask_quizzes_con_status_21f402_idx_and_more'),
    ]

    operations = [
        migrations.RunPython(add_teacherexam_columns, remove_teacherexam_columns),
    ]
