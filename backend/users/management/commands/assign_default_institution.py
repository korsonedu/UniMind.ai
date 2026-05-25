"""
Assign all users without an institution to the 宇艺示范学员 demo institution.
Safe to run multiple times — only targets users with institution IS NULL.

Usage: python manage.py assign_default_institution
"""
from django.core.management.base import BaseCommand
from users.models import User, Institution


class Command(BaseCommand):
    help = 'Assign all institution-less users to 宇艺示范学员'

    def handle(self, *args, **options):
        inst, created = Institution.objects.get_or_create(
            slug='demo-academy',
            defaults={
                'name': '宇艺示范学员',
                'contact_name': '宇艺',
                'contact_email': 'demo@unimind.ai',
                'plan': 'growth',
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created institution: {inst.name}'))
        else:
            self.stdout.write(f'Using existing institution: {inst.name}')

        # Only target non-superuser, non-staff users without an institution
        users = User.objects.filter(
            institution__isnull=True,
            is_superuser=False,
        ).exclude(role='admin')

        count = users.count()
        if count == 0:
            self.stdout.write('No users to assign.')
            return

        updated = users.update(institution=inst, institution_role='student')
        self.stdout.write(self.style.SUCCESS(
            f'Assigned {updated} user(s) to {inst.name} (slug={inst.slug})'
        ))
