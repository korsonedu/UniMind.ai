import re
from django.core.management.base import BaseCommand
from quizzes.models import KnowledgePoint

class Command(BaseCommand):
    help = '解析 Markdown 知识树并导入数据库'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Markdown 文件的本地路径')
        parser.add_argument('--force', action='store_true', help='跳过确认提示，直接清空并导入')

    def handle(self, *args, **kwargs):
        file_path = kwargs['file_path']

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f'找不到文件: {file_path}'))
            return

        if not kwargs.get('force'):
            existing = KnowledgePoint.objects.count()
            if existing > 0:
                confirm = input(f'当前知识树有 {existing} 个节点。清空并重新导入？[y/N] ')
                if confirm.strip().lower() != 'y':
                    self.stdout.write('已取消。')
                    return

        KnowledgePoint.objects.all().delete()
        self.stdout.write("清理了旧的知识树数据。")
        
        stack = {}
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
            
            # 【核心修复1】去除中英文括号存入 name（给用户看），完整内容保留在 description（给 AI 看）
            clean_name = re.sub(r'[（\(].*?[）\)]', '', raw_name).strip()
            
            # 确定层级与深度
            if prefix_symbol.startswith('#'):
                level_depth = len(prefix_symbol)
                level_str = {1: 'sub', 2: 'ch', 3: 'sec'}.get(level_depth, 'sec')
            else:
                level_depth = 4
                level_str = 'kp'
            
            # 【核心修复2】通过深度寻找父节点，彻底解决平级问题
            parent = stack.get(level_depth - 1)

            # 创建节点
            kp = KnowledgePoint.objects.create(
                code=code.strip(),
                name=clean_name,
                description=raw_name,
                level=level_str,
                parent=parent
            )
            
            # 更新当前深度的父节点栈
            stack[level_depth] = kp
            
            # 清理比当前更深的层级（防止树枝挂错）
            keys_to_remove = [k for k in stack.keys() if k > level_depth]
            for k in keys_to_remove:
                del stack[k]

            count += 1
            self.stdout.write(f"成功导入: [{level_str}] {code} - {clean_name}")

        self.stdout.write(self.style.SUCCESS(f'✅ 知识树导入完成，共精准挂载 {count} 个节点！'))