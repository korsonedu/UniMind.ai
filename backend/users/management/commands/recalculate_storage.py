"""校准所有机构的 storage_used_bytes。

用法：python manage.py recalculate_storage [--dry-run]
"""

from django.core.management.base import BaseCommand
from django.db.models import Sum
from users.models import Institution


class Command(BaseCommand):
    help = "重新计算所有机构的存储用量（storage_used_bytes）"

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='仅显示差异，不写入')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        institutions = Institution.objects.all()

        for inst in institutions:
            actual = self._calc_storage(inst)
            diff = actual - inst.storage_used_bytes
            if diff != 0:
                sign = '+' if diff > 0 else ''
                self.stdout.write(
                    f"  {inst.name}: {inst.storage_used_bytes} -> {actual} ({sign}{diff} bytes)"
                )
                if not dry_run:
                    inst.storage_used_bytes = actual
                    inst.save(update_fields=['storage_used_bytes'])
            else:
                self.stdout.write(f"  {inst.name}: {inst.storage_used_bytes} (unchanged)")

        self.stdout.write(self.style.SUCCESS(
            f"{'[DRY RUN] ' if dry_run else ''}Done. {institutions.count()} institutions processed."
        ))

    def _calc_storage(self, inst) -> int:
        """计算机构下所有文件的实际总大小。"""
        from courses.models import Course
        from articles.models import Article
        from faq_system.models import Question

        total = 0

        # Course files
        for course in Course.objects.filter(institution=inst):
            for field in (course.video_file, course.cover_image, course.courseware, course.reference_materials):
                try:
                    if field:
                        total += field.size or 0
                except Exception:
                    pass

        # Article cover images
        for article in Article.objects.filter(institution=inst):
            try:
                if article.cover_image:
                    total += article.cover_image.size or 0
            except Exception:
                pass

        # FAQ attachments
        for question in Question.objects.filter(institution=inst):
            try:
                if question.attachment:
                    total += question.attachment.size or 0
            except Exception:
                pass

        return total
