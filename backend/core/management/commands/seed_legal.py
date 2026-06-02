"""
将 views.py 内置的 v2.0 法律文档写入数据库。

Usage:
    python manage.py seed_legal
    python manage.py seed_legal --force   # 即使 v2.0 已存在也重新写入
"""
from datetime import date

from django.core.management.base import BaseCommand

from core.models import LegalDocument
from core.views import _PRIVACY_HTML, _TERMS_HTML


class Command(BaseCommand):
    help = '将 v2.0 用户协议和隐私政策写入数据库（覆盖旧版 is_active）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force', action='store_true',
            help='即使 v2.0 已存在也重新写入',
        )

    def handle(self, *args, **options):
        force = options['force']
        effective = date(2026, 6, 3)
        version = '2.0'

        docs = [
            ('terms', '用户协议', _TERMS_HTML),
            ('privacy', '隐私政策', _PRIVACY_HTML),
        ]

        for doc_type, title, content in docs:
            exists = LegalDocument.objects.filter(
                doc_type=doc_type, version=version,
            ).exists()

            if exists and not force:
                self.stdout.write(self.style.WARNING(
                    f'{title} v{version} 已存在，跳过（使用 --force 强制覆盖）',
                ))
                continue

            # 旧版同类型文档全部标为失效
            old_count = LegalDocument.objects.filter(
                doc_type=doc_type, is_active=True,
            ).update(is_active=False)

            obj, created = LegalDocument.objects.update_or_create(
                doc_type=doc_type, version=version,
                defaults={
                    'title': title,
                    'content': content,
                    'is_active': True,
                    'effective_date': effective,
                },
            )

            action = '创建' if created else '更新'
            self.stdout.write(self.style.SUCCESS(
                f'{action} {title} v{version}（失效旧文档 {old_count} 条）',
            ))

        self.stdout.write(self.style.SUCCESS('完成'))
