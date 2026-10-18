"""Apply the reviewed course-to-knowledge-chapter mapping without changing media or history."""
import csv
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.utils import get_content_institution_id
from courses.models import Course, CourseModule
from quizzes.models import KnowledgePoint


class Command(BaseCommand):
    help = '预览科晟现有课程的学科与知识地图章节归类；--apply 才写入。'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        scope = get_content_institution_id()
        points = {point.pk: point for point in KnowledgePoint.objects.filter(institution_id=scope)}
        by_code = {point.code: point for point in points.values() if point.code}
        path = Path(settings.BASE_DIR).parent / 'docs/operations/2026-10-18-course-knowledge-map.csv'
        plan = []
        with path.open(newline='') as source:
            for row in csv.DictReader(source):
                course = Course.objects.select_for_update().filter(pk=row['course_id'], institution_id=scope).first()
                if not course or course.title != row['title']:
                    raise CommandError(f'课程 #{row["course_id"]} 与已核对清单不一致，未写入。')
                point = by_code.get(row['knowledge_code'])
                if not point or point.level != 'sec':
                    raise CommandError(f'知识地图章节 {row["knowledge_code"]} 不存在或层级不符。')
                root = point
                seen = set()
                while root.parent_id:
                    if root.pk in seen or root.parent_id not in points:
                        raise CommandError('知识地图父级链无效。')
                    seen.add(root.pk)
                    root = points[root.parent_id]
                if root.name not in ('货币经济学', '金融理论与现代投资学'):
                    raise CommandError('学科与已核对范围不一致。')
                if course.module_id:
                    module = course.module
                    if (module.subject, module.name) != (root.name, point.name):
                        raise CommandError(f'课程 #{course.pk} 已有不同模块，请人工核对。')
                if course.knowledge_point_id and course.knowledge_point_id not in (root.pk, point.pk):
                    raise CommandError(f'课程 #{course.pk} 已有更具体的知识点，请人工核对。')
                parent = points[point.parent_id]
                plan.append((course, point, root.name, parent.order * 100 + point.order,
                             f'知识地图：{root.name} / {parent.name} / {point.name}'))
        report = []
        for course, point, subject, order, description in plan:
            if options['apply']:
                module, _ = CourseModule.objects.get_or_create(institution_id=scope, subject=subject, name=point.name,
                    defaults={'sort_order': order, 'description': description})
                Course.objects.filter(pk=course.pk, institution_id=scope).update(module=module, knowledge_point=point)
            report.append({'id': course.pk, 'title': course.title, 'subject': subject,
                           'module': point.name, 'knowledge_code': point.code})
        self.stdout.write(json.dumps({'applied': options['apply'], 'count': len(report), 'courses': report}, ensure_ascii=False, indent=2))
