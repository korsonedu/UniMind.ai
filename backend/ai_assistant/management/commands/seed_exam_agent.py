from django.core.management.base import BaseCommand
from ai_assistant.models import Bot


class Command(BaseCommand):
    help = '创建或更新命题官 Bot'

    def handle(self, *args, **options):
        from ai_assistant.prompt_sync import sync_bot_prompt

        bot, created = Bot.objects.update_or_create(
            bot_type='exam_generator',
            defaults={
                'name': '命题官',
                'system_prompt': '',  # 由 sync_bot_prompt 从文件填充
                'is_exclusive': False,
                'is_active': True,
                'institution': None,
            },
        )

        sync_bot_prompt(bot)

        action = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(
            f'{action} 命题官 bot (id={bot.id}, type={bot.bot_type})'
        ))
