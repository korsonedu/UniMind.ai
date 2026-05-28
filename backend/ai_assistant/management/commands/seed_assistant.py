from django.core.management.base import BaseCommand
from ai_assistant.models import Bot


class Command(BaseCommand):
    help = '创建或更新 AI 助教（全能导师）Bot'

    def handle(self, *args, **options):
        from ai_assistant.prompt_sync import sync_bot_prompt

        bot, created = Bot.objects.update_or_create(
            bot_type='assistant',
            institution=None,
            defaults={
                'name': '全能导师',
                'system_prompt': '',  # 由 sync_bot_prompt 从文件填充
                'is_exclusive': False,
                'is_active': True,
            },
        )

        sync_bot_prompt(bot)

        action = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(
            f'{action} 全能导师 bot (id={bot.id}, type={bot.bot_type})'
        ))
