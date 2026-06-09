"""
从 KnowledgePoint 树结构生成/重建 KnowledgeEdge 边。

用法:
  python manage.py seed_knowledge_edges --subject CFA          # 首次 seed（= 全量重建）
  python manage.py seed_knowledge_edges --subject CFA --dry-run # 干跑
  python manage.py seed_knowledge_edges --all                  # 所有学科
  python manage.py seed_knowledge_edges --subject CFA --resync # 显式全量重建（删旧建新）

树变更后无需手动运行——Django signal 会自动增量同步单 KP 的边。
此命令用于批量导入、migration 后首次灌边、或手动全量修复。
"""
from django.core.management.base import BaseCommand
from quizzes.models import KnowledgePoint
from quizzes.services.knowledge_edge_sync import rebuild_subject_edges


class Command(BaseCommand):
    help = '从 KnowledgePoint 树生成 KnowledgeEdge 边'

    def add_arguments(self, parser):
        parser.add_argument('--subject', type=str, help='学科名称')
        parser.add_argument('--all', action='store_true', help='处理所有学科')
        parser.add_argument('--dry-run', action='store_true', help='只统计不写入')
        parser.add_argument('--resync', action='store_true',
                           help='全量重建（删除所有 tree 边后重建）')

    def handle(self, *args, **options):
        subject = options['subject']
        do_all = options['all']
        dry_run = options['dry_run']

        if not subject and not do_all:
            self.stderr.write("必须指定 --subject 或 --all")
            return

        subjects = [subject] if subject else list(
            KnowledgePoint.objects.exclude(subject__isnull=True)
            .exclude(subject='')
            .filter(level='kp')
            .values_list('subject', flat=True)
            .distinct()
        )

        total = {'kp_count': 0, 'old': 0, 'new': 0, 'pc': 0, 'sg': 0}

        for subj in subjects:
            result = rebuild_subject_edges(subj, dry_run=dry_run)

            kp_c = result['kp_count']
            if 'would_create' in result:
                self.stdout.write(
                    f"  {subj}: {kp_c} KPs → {result['old_tree_edges']} old edges "
                    f"→ {result['would_create']} would create "
                    f"({result['parent_child_pairs']} P-C pairs, "
                    f"{result['sibling_groups']} sibling groups) [DRY-RUN]"
                )
                total['old'] += result['old_tree_edges']
                total['new'] += result['would_create']
            else:
                self.stdout.write(
                    f"  {subj}: {kp_c} KPs → {result['old_tree_edges']} old deleted, "
                    f"{result['new_edges_created']} created, "
                    f"{result['new_edges_skipped']} skipped "
                    f"({result['parent_child_pairs']} P-C pairs, "
                    f"{result['sibling_groups']} sibling groups)"
                )
                total['old'] += result['old_tree_edges']
                total['new'] += result['new_edges_created']

            total['kp_count'] += kp_c
            total['pc'] += result['parent_child_pairs']
            total['sg'] += result['sibling_groups']

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n总计: {total['kp_count']} KPs, {total['old']} old → "
                    f"{total['new']} would create "
                    f"({total['pc']} P-C, {total['sg']} sibling groups)"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n总计: {total['kp_count']} KPs, {total['old']} deleted, "
                    f"{total['new']} created "
                    f"({total['pc']} P-C, {total['sg']} sibling groups)"
                )
            )
