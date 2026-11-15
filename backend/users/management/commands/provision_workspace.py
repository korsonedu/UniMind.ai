from datetime import date
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from users.models import Institution
from users.models_workspace import Workspace, WorkspaceMembership
import secrets


class Command(BaseCommand):
    help = '开通标准机构 workspace，并明确指定首位管理员；不修改历史机构角色。'

    def add_arguments(self, parser):
        parser.add_argument('--name', required=True)
        parser.add_argument('--admin', required=True, help='已有 UniMind.ai 用户名')
        parser.add_argument('--ends-on', required=True, type=date.fromisoformat)
        parser.add_argument('--max-students', required=True, type=int)

    @transaction.atomic
    def handle(self, *args, **options):
        name = options['name'].strip()
        if not name or len(name) > 200 or options['max_students'] < 1 or options['ends_on'] < timezone.localdate():
            raise CommandError('请提供有效机构名称、正整数名额和未来的服务结束日期。')
        user = get_user_model().objects.select_for_update().filter(username=options['admin'], is_active=True).first()
        if not user:
            raise CommandError('管理员账号不存在或已停用。')
        if WorkspaceMembership.objects.filter(user=user).exists():
            raise CommandError('该账号已加入 workspace，请勿重复开通。')
        institution = Institution.objects.create(name=name, slug=f"{slugify(name)[:60] or 'workspace'}-{secrets.token_hex(4)}", created_by=user)
        workspace = Workspace.objects.create(institution=institution, service_ends_on=options['ends_on'], max_students=options['max_students'])
        WorkspaceMembership.objects.create(user=user, workspace=workspace, role='admin')
        self.stdout.write(self.style.SUCCESS(f'已开通 workspace {workspace.pk}：{name}，管理员 {user.username}'))
