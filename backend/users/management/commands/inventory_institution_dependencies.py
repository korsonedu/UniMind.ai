"""只读盘点历史机构及所有显式外键，不合并或修改业务数据。"""
import json

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.models import Count

from users.models import Institution


class Command(BaseCommand):
    help = '只读输出历史机构及关联行数，供单平台物理迁移前核对。'

    def handle(self, *args, **options):
        dependencies = []
        pending_tables = []
        existing_tables = set(connection.introspection.table_names())
        for model in apps.get_models():
            for field in model._meta.fields:
                if getattr(field, 'related_model', None) is not Institution:
                    continue
                if model._meta.db_table not in existing_tables:
                    pending_tables.append({'model': model._meta.label, 'field': field.name})
                    continue
                rows = model._base_manager.values(field.attname).annotate(count=Count('pk'))
                dependencies.append({
                    'model': model._meta.label, 'field': field.name,
                    'on_delete': field.remote_field.on_delete.__name__,
                    'counts': list(rows.order_by(field.attname)),
                })
        report = {
            'read_only': True,
            'content_scope': settings.UNIMIND_CONTENT_INSTITUTION_ID or 'UNCONFIGURED',
            'institutions': list(Institution.objects.values('id', 'name', 'is_active').order_by('id')),
            'foreign_keys': dependencies,
            'pending_tables': pending_tables,
            'limitations': [
                'JSON payload、缓存键、对象存储路径和外部 Directus 数据仍需人工核对。',
                '本命令不判断历史机构可否合并，不改用户角色、学习历史或 Memorix 状态。',
                '物理迁移前须完成备份、资源归属映射及账号与审计身份核对。',
            ],
        }
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, default=str))
