"""
Detect orphan KnowledgePoints — nodes whose parent was deleted (SET_NULL)
and that should have a parent based on their level.

Usage:
  python manage.py detect_orphan_kps                    # list all orphans
  python manage.py detect_orphan_kps --institution=xxx  # scope to institution
  python manage.py detect_orphan_kps --delete            # delete detected orphans
"""
from django.core.management.base import BaseCommand

from users.models import Institution
from quizzes.models import KnowledgePoint


class Command(BaseCommand):
    help = 'Detect and optionally delete orphan KnowledgePoints (parent=NULL but not root-level)'

    def add_arguments(self, parser):
        parser.add_argument('--institution', type=str, help='机构 slug')
        parser.add_argument('--institution-id', type=int, help='机构 ID')
        parser.add_argument('--global', action='store_true', help='针对全局知识树')
        parser.add_argument('--delete', action='store_true', help='删除检测到的孤儿节点')

    def handle(self, *args, **kwargs):
        institution = None
        if kwargs.get('institution_id'):
            institution = Institution.objects.filter(id=kwargs['institution_id']).first()
            if not institution:
                self.stdout.write(self.style.ERROR(f'未找到机构 ID={kwargs["institution_id"]}'))
                return
        elif kwargs.get('institution'):
            institution = Institution.objects.filter(slug=kwargs['institution']).first()
            if not institution:
                self.stdout.write(self.style.ERROR(f'未找到机构 slug={kwargs["institution"]}'))
                return
        elif not kwargs.get('global'):
            # Default: check all scopes
            pass

        if institution:
            scope_label = f'机构「{institution.name}」'
        elif kwargs.get('global'):
            scope_label = '全局'
        else:
            scope_label = '所有范围'

        base_qs = KnowledgePoint.objects.all()
        if institution:
            base_qs = base_qs.filter(institution=institution)
        elif kwargs.get('global'):
            base_qs = base_qs.filter(institution__isnull=True)

        # Orphans: nodes that are NOT root level ('sub') and have no parent
        orphans = base_qs.filter(parent__isnull=True).exclude(level='sub').order_by('level', 'prefix_category', 'code')

        if not orphans.exists():
            self.stdout.write(self.style.SUCCESS(f'✅ {scope_label} 无孤儿节点。'))
            return

        if kwargs.get('delete'):
            count = orphans.count()
            # Collect IDs to report before deleting
            orphan_list = list(orphans.values('id', 'code', 'name', 'level', 'prefix_category'))
            orphans.delete()
            self.stdout.write(self.style.SUCCESS(f'已删除 {count} 个孤儿节点：'))
            for o in orphan_list:
                self.stdout.write(f'  [{o["level"]}] {o["code"] or "?"} — {o["name"]} (prefix={o["prefix_category"] or "?"})')
            return

        # Report mode
        total = orphans.count()
        self.stdout.write(self.style.WARNING(
            f'\n{"=" * 60}\n'
            f'🔍 发现 {total} 个孤儿节点（parent=NULL 但非 sub 级别）\n'
            f'   范围: {scope_label}\n'
            f'{"=" * 60}\n'
        ))

        by_level = {}
        for o in orphans:
            by_level.setdefault(o.level, []).append(o)

        level_order = ['ch', 'sec', 'kp']
        for lvl in level_order:
            nodes = by_level.get(lvl, [])
            if nodes:
                self.stdout.write(f'\n── {lvl} ({len(nodes)} 个) ──')
                for n in nodes:
                    self.stdout.write(f'  [{n.code or "?"}] {n.name}  prefix={n.prefix_category or "?"}  id={n.id}')

        # Also check: root nodes ('sub') with no parent — these are expected, just count
        root_count = base_qs.filter(parent__isnull=True, level='sub').count()
        total_all = base_qs.count()
        self.stdout.write(f'\n统计: 总计 {total_all} 个节点, {root_count} 个学科根节点, {total} 个孤儿')

        self.stdout.write(self.style.WARNING(
            f'\n💡 建议: 重新导入 MD 知识树以修复结构。\n'
            f'   API: POST /api/quizzes/knowledge-points/import-md/\n'
            f'   或: python manage.py import_knowledge_tree <file> --force [--institution=xxx | --global]\n'
            f'   或加 --delete 删除这些孤儿节点'
        ))
