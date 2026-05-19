import re
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from users.models import Institution
from quizzes.models import KnowledgePoint

User = get_user_model()

class Command(BaseCommand):
    help = '解析 Markdown 知识树并导入数据库，按机构隔离'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Markdown 文件的本地路径')
        parser.add_argument('--force', action='store_true', help='跳过确认提示，直接清空并导入')
        parser.add_argument('--institution', type=str, help='机构 slug，将此知识树分配给指定机构')
        parser.add_argument('--institution-id', type=int, help='机构 ID，将此知识树分配给指定机构')
        parser.add_argument('--global', action='store_true', help='导入为全局知识树（不属于任何机构）')
        parser.add_argument('--subject', type=str, help='学科名称（如 金融431、法学），用于多学科全局共存')

    def handle(self, *args, **kwargs):
        file_path = kwargs['file_path']
        institution = None

        if kwargs.get('institution_id'):
            institution = Institution.objects.filter(id=kwargs['institution_id']).first()
            if not institution:
                self.stdout.write(self.style.ERROR(f'未找到 ID 为 {kwargs["institution_id"]} 的机构'))
                return
        elif kwargs.get('institution'):
            institution = Institution.objects.filter(slug=kwargs['institution']).first()
            if not institution:
                self.stdout.write(self.style.ERROR(f'未找到 slug 为 {kwargs["institution"]} 的机构'))
                return
        elif not kwargs.get('global'):
            self.stdout.write(self.style.WARNING(
                '⚠️  未指定 --institution / --institution-id / --global，将导入为全局知识树（不属于任何机构）。\n'
                '   如需分配给机构，请使用 --institution=<slug> 或 --institution-id=<id>'
            ))

        subject = kwargs.get('subject') or ''

        if subject and not institution and not kwargs.get('global'):
            self.stdout.write(self.style.ERROR('--subject 要求同时使用 --global 或 --institution'))
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f'找不到文件: {file_path}'))
            return

        # 只删除同一 institution 的知识点（NULL 也视为一组）
        if institution:
            if subject:
                scope_filter = {'institution': institution, 'subject': subject}
                scope_label = f'机构「{institution.name}」「{subject}」'
            else:
                scope_filter = {'institution': institution}
                scope_label = f'机构「{institution.name}」'
        elif kwargs.get('global'):
            if subject:
                scope_filter = {'institution__isnull': True, 'subject': subject}
                scope_label = f'全局「{subject}」'
            else:
                scope_filter = {'institution__isnull': True}
                scope_label = '全局'
        else:
            scope_filter = {'institution__isnull': True}
            scope_label = '全局'
        existing = KnowledgePoint.objects.filter(**scope_filter).count()

        if not kwargs.get('force'):
            if existing > 0:
                confirm = input(
                    f'{scope_label} 当前有 {existing} 个节点。'
                    f'清空并重新导入？[y/N] '
                )
                if confirm.strip().lower() != 'y':
                    self.stdout.write('已取消。')
                    return

        KnowledgePoint.objects.filter(**scope_filter).delete()
        self.stdout.write(f"清理了 {scope_label} 的旧知识树数据。")

        stack = {}
        order_counter = {}  # level_depth → parent_id → next order
        count = 0

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 正则匹配形如: # [SUB-01] 货币经济学 或 - [MB-1001] 货币的起源
            match = re.match(r'^(#+|-)\s+\[(.*?)\]\s+(.*)$', line)
            if not match:
                continue

            prefix_symbol, code, raw_name = match.groups()

            # 去除中英文括号存入 name（给用户看），完整内容保留在 description（给 AI 看）
            clean_name = re.sub(r'[（\(].*?[）\)]', '', raw_name).strip()

            # 确定层级与深度
            if prefix_symbol.startswith('#'):
                level_depth = len(prefix_symbol)
                level_str = {1: 'sub', 2: 'ch', 3: 'sec'}.get(level_depth, 'sec')
            else:
                level_depth = 4
                level_str = 'kp'

            # 通过深度寻找父节点，找不到则向上回溯祖先
            parent = None
            for ancestor_level in range(level_depth - 1, 0, -1):
                parent = stack.get(ancestor_level)
                if parent is not None:
                    break

            # 计算同级排序：以父节点 + 层级为 key
            parent_id = parent.id if parent else None
            order_key = (level_depth, parent_id)
            order_counter[order_key] = order_counter.get(order_key, 0) + 1

            # 创建节点，关联到机构
            kp = KnowledgePoint.objects.create(
                code=code.strip(),
                name=clean_name,
                description=raw_name,
                level=level_str,
                parent=parent,
                order=order_counter[order_key],
                institution=institution,
                subject=subject,
            )

            # 更新当前深度的父节点栈
            stack[level_depth] = kp

            # 清理比当前更深的层级
            keys_to_remove = [k for k in stack.keys() if k > level_depth]
            for k in keys_to_remove:
                del stack[k]

            count += 1
            self.stdout.write(f"成功导入: [{level_str}] {code} - {clean_name}")

        self.stdout.write(self.style.SUCCESS(
            f'✅ {scope_label} 知识树导入完成，共 {count} 个节点！'
        ))
