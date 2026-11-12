from django.core.management.base import BaseCommand, CommandError
from rest_framework.exceptions import APIException
from ai_assistant.services.function_sample import seed_content


class Command(BaseCommand):
    help = '显式准备函数基础原创样板的四个知识点和十二道单选题，只写当前配置的内容分区。'

    def handle(self, *args, **options):
        try:
            result = seed_content()
        except APIException as error:
            raise CommandError(str(error.detail)) from error
        self.stdout.write(f"函数基础 v{result['version']}：新增 {result['created_knowledge_points']} 个知识点、{result['created_questions']} 道原创单选题。")
