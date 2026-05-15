"""
将 seed_questions.json 中的题目和知识点导入（或更新）到数据库。

用法：python manage.py seed_questions [--path /custom/path/seed_questions.json]
"""

import json
from django.core.management.base import BaseCommand
from quizzes.models import Question, KnowledgePoint


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument(
            '--path',
            default=None,
            help='seed_questions.json 的路径（默认为 backend/seed_questions.json）',
        )

    def handle(self, **options):
        from pathlib import Path

        seed_path = Path(options['path']) if options['path'] else (
            Path(__file__).resolve().parent.parent.parent.parent / "seed_questions.json"
        )

        if not seed_path.exists():
            self.stderr.write(self.style.ERROR(f"找不到种子文件：{seed_path}"))
            return

        with open(seed_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        kp_data = data.get("knowledge_points", [])
        q_data = data.get("questions", [])

        self.stdout.write(f"种子文件包含: {len(q_data)} 道题目")
        self.stdout.write("开始导入...\n")

        kp_map = {}

        if kp_data:
            parent_map = {}
            for kp in kp_data:
                obj, created = KnowledgePoint.objects.get_or_create(
                    name=kp["name"],
                    defaults={"description": kp.get("description", "")},
                )
                if not created and kp.get("description"):
                    obj.description = kp["description"]
                    obj.save(update_fields=["description"])
                kp_map[kp["name"]] = obj
                if kp.get("parent_name"):
                    parent_map[kp["name"]] = kp["parent_name"]

            for name, parent_name in parent_map.items():
                if name in kp_map and parent_name in kp_map:
                    child = kp_map[name]
                    parent = kp_map[parent_name]
                    if child.parent != parent:
                        child.parent = parent
                        child.save(update_fields=["parent"])
            self.stdout.write(self.style.SUCCESS(
                f"提取并加载了 {len(kp_map)} 条旧版知识点配置..."
            ))

        created_count = 0
        updated_count = 0
        error_count = 0

        for i, q in enumerate(q_data):
            text = q.get("text") or q.get("question_text", "")
            text = text.strip()
            if not text:
                continue

            kp_raw = q.get("knowledge_point_name") or q.get("knowledge_point") or q.get("kp_name")
            kp_name = kp_raw.get("name") if isinstance(kp_raw, dict) else kp_raw
            parent_kp_name = q.get("parent_knowledge_point") or q.get("parent_kp")

            kp_obj = None
            if kp_name:
                if kp_name in kp_map:
                    kp_obj = kp_map[kp_name]
                else:
                    parent_obj = None
                    if parent_kp_name:
                        parent_obj, _ = KnowledgePoint.objects.get_or_create(name=parent_kp_name)

                    kp_obj, _ = KnowledgePoint.objects.get_or_create(name=kp_name)
                    if parent_obj and kp_obj.parent != parent_obj:
                        kp_obj.parent = parent_obj
                        kp_obj.save(update_fields=["parent"])

                    kp_map[kp_name] = kp_obj

            try:
                diff_level = q.get("difficulty_level", "normal")
                diff_elo = q.get("difficulty_elo") or q.get("difficulty")

                defaults = {
                    "q_type": q.get("question_type") or q.get("q_type", "subjective"),
                    "subjective_type": q.get("subjective_type"),
                    "difficulty_level": diff_level,
                    "options": q.get("options"),
                    "correct_answer": q.get("correct_answer", ""),
                    "grading_points": q.get("grading_points", ""),
                    "ai_answer": q.get("ai_explanation") or q.get("ai_answer", ""),
                    "difficulty": diff_elo if diff_elo else Question.DIFFICULTY_MAP.get(diff_level, 1200),
                    "knowledge_point": kp_obj,
                }

                qid = q.get("id")
                if qid:
                    defaults["text"] = text
                    obj, created = Question.objects.update_or_create(id=qid, defaults=defaults)
                else:
                    obj, created = Question.objects.update_or_create(text=text, defaults=defaults)

                if created:
                    created_count += 1
                else:
                    updated_count += 1

                if (i + 1) % 20 == 0:
                    self.stdout.write(f"  进度: {i + 1}/{len(q_data)}...")

            except Exception as e:
                self.stderr.write(f"  题目处理失败: {str(e)[:80]}")
                error_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"\n题目导入完成！新增: {created_count} 更新: {updated_count} 错误: {error_count}"
        ))
        self.stdout.write(f"  当前数据库总题数: {Question.objects.count()} 道")
        self.stdout.write(
            "\n提示：为了安全支持仅含新题的 JSON 增量导入，已移除旧版的自动删除缺失题目逻辑。"
        )
