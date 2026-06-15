"""
批量出题管理命令。

用法：
  # 为整个学科生成 500 道题
  python manage.py bulk_generate --subject=高中数学 --target=500

  # 指定难度分布
  python manage.py bulk_generate --subject=CFA --target=300 --difficulty=normal

  # 只补充单个知识点
  python manage.py bulk_generate --subject=金融431 --target=50 --kp-code=FIN431.01

  # 自定义难度/题型分布（JSON）
  python manage.py bulk_generate --subject=法学 --target=200 --diff-dist='{"easy":0.2,"normal":0.6,"hard":0.2}'

  # 试运行（不实际调用 LLM，只打印计划）
  python manage.py bulk_generate --subject=高中数学 --target=100 --dry-run
"""

import json
from django.core.management.base import BaseCommand
from django.utils import timezone
from quizzes.models import ContentPipelineTask
from quizzes.services.bulk_pipeline import (
    run_bulk_pipeline,
    _select_target_kps,
    _distribute_quotas,
    _execute_bulk_pipeline,
    DEFAULT_DIFFICULTY_DIST,
    DEFAULT_TYPE_DIST,
)


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('--subject', required=True, help='学科名称（如 高中数学、CFA）')
        parser.add_argument('--target', type=int, default=500, help='目标生成总数（默认 500）')
        parser.add_argument('--difficulty', default=None, help='单一难度（easy/normal/hard/extreme），覆盖 diff-dist')
        parser.add_argument('--diff-dist', default=None, help='难度分布 JSON，如 {"easy":0.25,"normal":0.5,"hard":0.25}')
        parser.add_argument('--type-dist', default=None, help='题型分布 JSON，如 {"objective":0.4,"subjective":0.6}')
        parser.add_argument('--kp-code', default=None, help='限定单个知识点编码')
        parser.add_argument('--dry-run', action='store_true', help='仅打印计划，不执行')
        parser.add_argument('--sync', action='store_true', help='同步执行（不走 Celery，适合小批量测试）')

    def handle(self, **options):
        subject = options['subject']
        target = options['target']
        difficulty = options.get('difficulty')
        diff_dist_raw = options.get('diff_dist')
        type_dist_raw = options.get('type_dist')
        kp_code = options.get('kp_code')
        dry_run = options.get('dry_run', False)
        sync = options.get('sync', False)

        # 解析分布
        if difficulty:
            difficulty_dist = {difficulty: 1.0}
        elif diff_dist_raw:
            difficulty_dist = json.loads(diff_dist_raw)
        else:
            difficulty_dist = DEFAULT_DIFFICULTY_DIST

        if type_dist_raw:
            type_dist = json.loads(type_dist_raw)
        else:
            type_dist = DEFAULT_TYPE_DIST

        # Dry-run: 只打印计划
        if dry_run:
            kps = _select_target_kps(subject, target, kp_code=kp_code)
            if not kps:
                self.stderr.write(self.style.ERROR(f"学科「{subject}」下没有可用知识点"))
                return

            quota_map = _distribute_quotas(kps, target, difficulty_dist, type_dist)

            self.stdout.write(self.style.SUCCESS(
                f"学科：{subject}  目标：{target} 道  知识点数：{len(kps)}"
            ))
            self.stdout.write(f"难度分布：{difficulty_dist}")
            self.stdout.write(f"题型分布：{type_dist}")
            self.stdout.write("")

            total_allocated = 0
            for kp, quotas in quota_map.items():
                kp_total = sum(quotas.values())
                total_allocated += kp_total
                existing = getattr(kp, '_question_count', 0)
                self.stdout.write(
                    f"  {kp.code} | {kp.name} | 已有 {existing} 道 | 新增 {kp_total} 道 "
                    f"({', '.join(f'{d}={n}' for d, n in quotas.items())})"
                )

            self.stdout.write("")
            self.stdout.write(f"总计分配：{total_allocated} 道（目标 {target}）")
            self.stdout.write(f"预估入库：~{int(total_allocated * 0.7)} 道（按 70% 通过率）")
            self.stdout.write("\n[dry-run] 不实际执行，去掉 --dry-run 可正式运行。")
            return

        # 正式运行（Celery 异步）
        self.stdout.write(self.style.SUCCESS(
            f"启动批量出题：{subject} → 目标 {target} 道\n"
            f"难度分布：{difficulty_dist}\n"
            f"题型分布：{type_dist}"
        ))

        if sync:
            # 同步执行：不走 Celery，直接在当前进程跑
            self.stdout.write("\n[sync mode] 开始同步执行...\n")
            from django.contrib.auth import get_user_model
            User = get_user_model()
            sys_user = User.objects.filter(is_superuser=True).first() or User.objects.first()
            task = ContentPipelineTask.objects.create(
                task_type="ai_generate",
                status="running",
                title=f"批量出题：{subject}",
                description=f"目标 {target} 道（sync）",
                payload={"subject": subject, "total_target": target, "difficulty_dist": difficulty_dist, "type_dist": type_dist, "kp_code": kp_code, "bulk_mode": True, "stages": []},
                progress=0,
                created_by=sys_user,
                started_at=timezone.now(),
            )
            try:
                _execute_bulk_pipeline(
                    task=task,
                    subject=subject,
                    total_target=target,
                    difficulty_dist=difficulty_dist,
                    type_dist=type_dist,
                    kp_code=kp_code,
                )
                task.refresh_from_db()
                summary = (task.result or {}).get('summary', {})
                self.stdout.write(self.style.SUCCESS(
                    f"\n批量出题完成！\n"
                    f"  生成: {summary.get('generated', 0)} 道\n"
                    f"  入库: {summary.get('saved', 0)} 道\n"
                    f"  通过率: {summary.get('pass_rate', 0)}\n"
                    f"  答案错误: {summary.get('answer_errors', 0)}\n"
                    f"  难度不匹配: {summary.get('difficulty_mismatches', 0)}\n"
                    f"  去重跳过: {summary.get('skipped_duplicates', 0)}"
                ))
            except Exception as exc:
                task.status = 'failed'
                task.error_message = str(exc)[:500]
                task.finished_at = timezone.now()
                task.save()
                self.stderr.write(self.style.ERROR(f"批量出题失败: {exc}"))
            return

        task_id = run_bulk_pipeline(
            subject=subject,
            total_target=target,
            difficulty_dist=difficulty_dist,
            type_dist=type_dist,
            kp_code=kp_code,
        )

        self.stdout.write(self.style.SUCCESS(
            f"\n批量出题已启动！pipeline_task_id = {task_id}\n"
            f"可通过 ContentPipelineTask 监控进度。"
        ))
