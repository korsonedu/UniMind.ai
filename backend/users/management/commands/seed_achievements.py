"""幂等创建预置成就。每次运行，已存在的跳过。"""
from django.core.management.base import BaseCommand
from users.services.achievements import seed_achievements


class Command(BaseCommand):
    help = '创建/更新预置成就定义（幂等）'

    def handle(self, *args, **options):
        seed_achievements()
        from users.models import Achievement
        count = Achievement.objects.count()
        self.stdout.write(self.style.SUCCESS(f'预置成就已同步，当前共 {count} 条'))
