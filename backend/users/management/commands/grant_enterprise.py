from datetime import date
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from users.models_workspace import EnterpriseAccount


class Command(BaseCommand):
    help = '为已有账号开通企业客户服务，仅授予创建机构的资格。'

    def add_arguments(self, parser):
        parser.add_argument('--user', required=True)
        parser.add_argument('--ends-on', required=True, type=date.fromisoformat)
        parser.add_argument('--max-students', required=True, type=int)

    @transaction.atomic
    def handle(self, *args, **options):
        if options['ends_on'] < timezone.localdate() or options['max_students'] < 1:
            raise CommandError('请提供有效服务结束日期和正整数学生名额。')
        user = get_user_model().objects.select_for_update().filter(username=options['user'], is_active=True).first()
        if not user or hasattr(user, 'workspace_learner'):
            raise CommandError('请指定有效的登录账号。')
        EnterpriseAccount.objects.update_or_create(user=user, defaults={
            'service_ends_on': options['ends_on'], 'max_students': options['max_students'], 'is_active': True,
        })
        self.stdout.write(self.style.SUCCESS(f'已开通 {user.username} 的企业客户服务，至 {options["ends_on"]}，每家机构 {options["max_students"]} 个学生名额。'))
