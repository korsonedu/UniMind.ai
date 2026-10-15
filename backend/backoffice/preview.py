"""Explicit fixtures for an isolated local preview database only."""
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model

from courses.models import Course, CourseModule
from quizzes.models import KnowledgePoint, Question
from users.models import LearningProduct


def seed():
    database = Path(settings.DATABASES['default']['NAME']).resolve()
    expected = Path(settings.BASE_DIR).parent / 'admin-extension' / '.preview' / 'django.sqlite3'
    if database != expected.resolve() or not settings.DEBUG:
        raise RuntimeError('Preview fixtures require the dedicated admin-extension/.preview/django.sqlite3 database.')
    User = get_user_model()
    for number in (1, 2):
        User.objects.update_or_create(username=f'preview-admin-{number}', defaults={
            'email': f'admin-{number}@preview.invalid', 'nickname': f'预览管理员 {number}',
            'is_staff': True, 'is_superuser': True, 'is_active': True, 'email_verified': True})
    User.objects.get_or_create(username='preview-student', defaults={
        'email': 'student@preview.invalid', 'nickname': '预览学员', 'is_active': True, 'email_verified': True})
    module, _ = CourseModule.objects.get_or_create(name='预览模块', institution=None)
    Course.objects.get_or_create(title='预览课程：待归类', defaults={'institution': None})
    product, _ = LearningProduct.objects.get_or_create(name='预览学习服务', defaults={
        'duration_days': 30, 'monthly_ai_calls': 200, 'price_cents': 9900})
    product.modules.add(module)
    parent = None
    for level, name in [('sub', '预览科目'), ('ch', '预览篇章'), ('sec', '预览小节'), ('kp', '预览考点')]:
        parent, _ = KnowledgePoint.objects.get_or_create(name=name, level=level, institution=None,
                                                       defaults={'subject': '预览学科', 'parent': parent})
    Question.objects.get_or_create(text='预览题目：请选择第二个选项。', institution=None, defaults={
        'knowledge_point': parent, 'options': ['预览选项一', '预览选项二'], 'correct_answer': 'B'})
    Question.objects.get_or_create(text='预览题目：请说明你的判断依据。', institution=None, defaults={
        'knowledge_point': parent, 'q_type': 'subjective', 'subjective_type': 'short',
        'correct_answer': '这是本地预览参考答案。', 'grading_points': '清楚陈述判断依据。'})
    print('Isolated preview fixtures ready; Django operator IDs:',
          list(User.objects.filter(username__startswith='preview-admin-').values_list('id', flat=True)))
