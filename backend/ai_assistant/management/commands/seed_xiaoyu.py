from django.core.management.base import BaseCommand
from ai_assistant.models import Bot


class Command(BaseCommand):
    help = '创建或更新小宇（XiaoYu）学习规划师 Bot'

    def handle(self, *args, **options):
        from ai_assistant.prompt_sync import sync_bot_prompt

        bot, created = Bot.objects.get_or_create(is_xiaoyu=True, defaults={'name': '小宇'})
        if not bot.is_active:
            bot.is_active = True
            bot.save(update_fields=['is_active'])

        sync_bot_prompt(bot)

        action = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(
            f'{action} 小宇 bot (id={bot.id}, type={bot.bot_type})'
        ))
