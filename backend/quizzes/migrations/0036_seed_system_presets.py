from django.db import migrations


def seed_system_presets(apps, schema_editor):
    ExamTemplate = apps.get_model('quizzes', 'ExamTemplate')

    presets = [
        {
            'name': '期末模拟卷',
            'description': '覆盖全学科重点知识点，难度偏高，适合考前冲刺',
            'difficulty': 'hard',
            'question_count': 30,
            'question_types': ['objective', 'subjective'],
            'type_ratio': {'objective': 0.5, 'short': 0.2, 'essay': 0.2, 'calculate': 0.1},
            'is_system': True,
        },
        {
            'name': '周测',
            'description': '中等难度，题量适中，适合每周检测学习效果',
            'difficulty': 'normal',
            'question_count': 15,
            'question_types': ['objective', 'subjective'],
            'type_ratio': {'objective': 0.6, 'short': 0.3, 'essay': 0.1},
            'is_system': True,
        },
        {
            'name': '知识点专练',
            'description': '针对特定知识点的强化训练，难度混合',
            'difficulty': 'mixed',
            'question_count': 10,
            'question_types': ['objective', 'subjective'],
            'type_ratio': {'objective': 0.4, 'short': 0.3, 'essay': 0.3},
            'is_system': True,
        },
    ]

    for preset in presets:
        ExamTemplate.objects.get_or_create(
            name=preset['name'],
            is_system=True,
            defaults=preset,
        )


def reverse_seed(apps, schema_editor):
    ExamTemplate = apps.get_model('quizzes', 'ExamTemplate')
    ExamTemplate.objects.filter(is_system=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('quizzes', '0035_examtemplate'),
    ]

    operations = [
        migrations.RunPython(seed_system_presets, reverse_seed),
    ]
