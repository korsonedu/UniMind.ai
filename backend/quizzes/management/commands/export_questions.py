"""
将指定学科的新增题目导出为 seed_questions.json 兼容格式。
使用 KP 名称（非 ID），确保跨环境可移植。

用法：
  # 导出 CFA 全部题目
  python manage.py export_questions --subject=CFA

  # 导出指定日期之后新增的题目
  python manage.py export_questions --subject=CFA --since=2026-06-14

  # 导出所有学科
  python manage.py export_questions --all --since=2026-06-14

  # 指定输出路径
  python manage.py export_questions --subject=CFA --output=backend/export_cfa.json
"""

import json
from datetime import datetime, date
from django.core.management.base import BaseCommand
from quizzes.models import Question, KnowledgePoint


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('--subject', default=None, help='学科名称')
        parser.add_argument('--all', action='store_true', help='导出全部学科')
        parser.add_argument('--since', default=None, help='仅导出此日期之后创建的题目（YYYY-MM-DD）')
        parser.add_argument('--output', default=None, help='输出文件路径')

    def handle(self, **options):
        subject = options.get('subject')
        export_all = options.get('all', False)
        since_str = options.get('since')
        output_path = options.get('output')

        if not subject and not export_all:
            self.stderr.write(self.style.ERROR("请指定 --subject 或 --all"))
            return

        # 构建查询
        qs = Question.objects.select_related('knowledge_point', 'knowledge_point__parent')

        if subject:
            qs = qs.filter(knowledge_point__subject=subject)
            if not qs.exists():
                self.stderr.write(self.style.ERROR(f"学科「{subject}」没有题目"))
                return

        if since_str:
            since_date = datetime.strptime(since_str, '%Y-%m-%d').date()
            qs = qs.filter(created_at__date__gte=since_date)

        total = qs.count()
        if total == 0:
            self.stderr.write("没有匹配的题目")
            return

        self.stdout.write(f"导出 {total} 道题目...")

        # 收集涉及的知识点
        kp_ids = set()
        questions_data = []
        for q in qs.iterator(chunk_size=500):
            q_dict = {
                "text": q.text,
                "question_type": q.q_type,
                "subjective_type": q.subjective_type,
                "difficulty_level": q.difficulty_level,
                "options": q.options,
                "correct_answer": q.correct_answer or "",
                "grading_points": q.grading_points or "",
                "ai_answer": q.ai_answer or "",
                "difficulty_elo": q.difficulty,
                "knowledge_point_name": q.knowledge_point.name if q.knowledge_point else None,
            }
            # 添加父级 KP（如果有）
            if q.knowledge_point and q.knowledge_point.parent:
                q_dict["parent_knowledge_point"] = q.knowledge_point.parent.name

            questions_data.append(q_dict)

            if q.knowledge_point:
                kp_ids.add(q.knowledge_point_id)
                if q.knowledge_point.parent_id:
                    kp_ids.add(q.knowledge_point.parent_id)

        # 收集知识点信息
        kp_data = []
        for kp in KnowledgePoint.objects.filter(id__in=kp_ids).iterator():
            kp_dict = {
                "name": kp.name,
                "description": kp.description or "",
            }
            if kp.parent:
                kp_dict["parent_name"] = kp.parent.name
            kp_data.append(kp_dict)

        output = {
            "knowledge_points": kp_data,
            "questions": questions_data,
            "_meta": {
                "subject": subject or "all",
                "exported_at": datetime.now().isoformat(),
                "total_questions": len(questions_data),
                "total_kps": len(kp_data),
            },
        }

        # 确定输出路径
        if not output_path:
            subj_slug = subject.replace(' ', '_') if subject else 'all'
            date_slug = since_str or datetime.now().strftime('%Y%m%d')
            output_path = f"export_{subj_slug}_{date_slug}.json"

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        self.stdout.write(self.style.SUCCESS(
            f"已导出到 {output_path}\n"
            f"  题目: {len(questions_data)} 道\n"
            f"  知识点: {len(kp_data)} 个"
        ))
