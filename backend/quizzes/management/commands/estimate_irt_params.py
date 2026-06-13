"""
管理命令：运行 IRT 参数估计。

用法：
    python manage.py estimate_irt_params               # 全量估计
    python manage.py estimate_irt_params --dry-run      # 预览不写入
    python manage.py estimate_irt_params --min 100      # 提高最小答题数门槛
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = '估计题目的 IRT 3PL 参数和学生能力 θ'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='预览模式：仅打印结果，不写入数据库',
        )
        parser.add_argument(
            '--min', type=int, default=50,
            dest='min_responses',
            help='估计所需最少答题记录数（默认 50）',
        )

    def handle(self, **options):
        from quizzes.services.irt_estimator import IRTEstimator

        dry_run = options['dry_run']
        min_responses = options['min_responses']

        self.stdout.write(
            self.style.NOTICE(
                f"{'[DRY RUN] ' if dry_run else ''}"
                f"开始 IRT 参数估计（min_responses={min_responses}）..."
            )
        )

        result = IRTEstimator.run_batch_estimation(
            min_responses=min_responses,
            dry_run=dry_run,
        )

        self.stdout.write(self.style.SUCCESS(f"结果: {result['message']}"))
        self.stdout.write(
            f"  题目总数: {result['total_questions']}, "
            f"已估计参数: {result['items_estimated']}, "
            f"学生能力 θ: {result['users_estimated']}"
        )
