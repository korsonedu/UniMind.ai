from django.core.management.base import BaseCommand
from django.db.models import Count
from django.db.models.functions import Lower
from users.models import User


class Command(BaseCommand):
    help = '只读检查已验证邮箱重复情况，仅输出重复数量与用户 ID。'

    def handle(self, *args, **options):
        duplicates = (User.objects.filter(email_verified=True).exclude(email='')
                      .annotate(normalized_email=Lower('email')).values('normalized_email')
                      .annotate(total=Count('pk')).filter(total__gt=1))
        groups = list(duplicates)
        self.stdout.write(f'重复已验证邮箱组数：{len(groups)}')
        for group in groups:
            ids = list(User.objects.filter(email_verified=True, email__iexact=group['normalized_email'])
                       .order_by('pk').values_list('pk', flat=True))
            self.stdout.write(f'用户 ID：{ids}')
        if groups:
            self.stderr.write('请先人工核实，勿迁移邮箱唯一约束。未修改任何账号。')
