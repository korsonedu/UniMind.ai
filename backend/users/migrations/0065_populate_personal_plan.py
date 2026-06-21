"""Populate personal_plan from membership_tier for institution-less users."""

from django.db import migrations


def populate_personal_plan(apps, schema_editor):
    User = apps.get_model('users', 'User')
    # Institution-less users: copy membership_tier → personal_plan
    updated = 0
    for user in User.objects.filter(institution_id__isnull=True):
        tier = user.membership_tier or 'free'
        if user.personal_plan != tier:
            user.personal_plan = tier
            user.save(update_fields=['personal_plan'])
            updated += 1
    print(f"  personal_plan populated for {updated} institution-less users")

    # Users with institution: personal_plan stays 'free' (plan comes from institution)
    User.objects.filter(institution_id__isnull=False).update(personal_plan='free')
    print(f"  institution users reset to personal_plan='free'")


def reverse_populate(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0064_add_personal_plan'),
    ]

    operations = [
        migrations.RunPython(populate_personal_plan, reverse_populate),
    ]
