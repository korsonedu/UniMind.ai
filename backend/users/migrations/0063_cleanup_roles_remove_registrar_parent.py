"""Remap registrar→teacher, parent→student; export & drop ParentStudentLink."""

import csv
import os
from datetime import datetime

from django.db import migrations


def export_parent_student_links(apps, schema_editor):
    """Export all ParentStudentLink rows to CSV before deletion."""
    ParentStudentLink = apps.get_model('users', 'ParentStudentLink')
    links = ParentStudentLink.objects.select_related('parent', 'student').all()
    if not links:
        return

    csv_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        f'parent_student_links_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
    )
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['parent_id', 'parent_username', 'student_id', 'student_username',
                          'verified', 'created_at', 'verified_at'])
        for link in links:
            writer.writerow([
                link.parent_id, link.parent.username,
                link.student_id, link.student.username,
                link.verified, link.created_at, link.verified_at,
            ])
    print(f"  ParentStudentLink 数据已导出到 {csv_path} ({len(links)} 条)")


def remap_roles(apps, schema_editor):
    User = apps.get_model('users', 'User')

    # Registrar → teacher
    updated = User.objects.filter(institution_role='registrar').update(institution_role='teacher')
    print(f"  registrar → teacher: {updated} 个用户")

    # Parent (platform role) → student
    updated = User.objects.filter(role='parent').update(role='student')
    print(f"  role parent → student: {updated} 个用户")

    # Parent (institution role) → student
    updated = User.objects.filter(institution_role='parent').update(institution_role='student')
    print(f"  institution_role parent → student: {updated} 个用户")


def reverse_remap(apps, schema_editor):
    """Cannot distinguish original registrars/parents from genuine teachers/students.
    This is intentionally irreversible — roll back the code changes instead."""
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0062_add_class_category'),
    ]

    operations = [
        migrations.RunPython(remap_roles, reverse_remap),
        migrations.RunPython(export_parent_student_links, migrations.RunPython.noop),
        migrations.DeleteModel(name='ParentStudentLink'),
    ]
