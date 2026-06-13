"""
Debug: Print tasks.generate_conversation_title source.
Usage: cd backend && python3 manage.py debug_title_task
"""
import inspect
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def handle(self, **options):
        from ai_assistant.tasks import generate_conversation_title
        src = inspect.getsource(generate_conversation_title)
        self.stdout.write(src)
