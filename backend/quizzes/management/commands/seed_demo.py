"""
Seed demo data for UniMind landing page screenshots.
All time-series data spans the last 7 days for realistic charts.
Idempotent — safe to run multiple times.

Usage: python manage.py seed_demo
"""
import random
from datetime import datetime, timedelta, date
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()

# ── time helpers ──

def days_ago(days, hour=12, minute=0):
    """Return a datetime exactly `days` ago at given hour."""
    t = timezone.now() - timedelta(days=days)
    return t.replace(hour=hour, minute=minute, second=0, microsecond=0)

def rand_time(days_ago_min, days_ago_max):
    """Random datetime between days_ago_min and days_ago_max ago."""
    minutes = random.randint(days_ago_min * 24 * 60, days_ago_max * 24 * 60)
    return timezone.now() - timedelta(minutes=minutes)

def fix_auto_now(model_class, pk, **time_fields):
    """Bypass auto_now_add by using .update() which skips save()."""
    model_class.objects.filter(pk=pk).update(**time_fields)


# ── users ──

def get_or_create_admin():
    user, created = User.objects.get_or_create(
        email='demo@unimind.ai',
        defaults={
            'username': 'demo_admin', 'nickname': '张老师', 'role': 'student',
            'is_staff': False, 'is_superuser': False, 'is_member': True,
            'membership_tier': 'pro', 'email_verified': True, 'elo_score': 1850,
            'bio': 'UniMind 演示机构管理员 | 5年考研辅导经验',
        }
    )
    if created:
        user.set_password('demo123456')
        user.save()
    return user


def get_or_create_students(count=5):
    names = ['李明', '王芳', '刘洋', '陈静', '赵磊']
    directions = ['金融431', '法学', 'CPA']
    students = []
    for i in range(count):
        s, created = User.objects.get_or_create(
            email=f'student{i+1}@demo.unimind',
            defaults={
                'username': f'demo_student_{i+1}', 'nickname': names[i],
                'role': 'student', 'is_member': True, 'membership_tier': 'basic',
                'email_verified': True, 'elo_score': random.randint(900, 1600),
                'bio': f'备考中 | {directions[i % 3]}方向',
            }
        )
        if created:
            s.set_password('demo123456')
            s.save()
        students.append(s)
    return students


# ── knowledge points ──

def build_knowledge_tree():
    from quizzes.models import KnowledgePoint
    tree = {
        '金融431': {
            '货币银行学': ['货币与货币制度', '利息与利率', '货币政策工具', '货币供给理论', '通货膨胀与通货紧缩'],
            '国际金融': ['汇率决定理论', '国际收支调节', '外汇市场与汇率制度', '开放经济下的宏观经济政策'],
            '公司理财': ['资本预算', '资本结构理论', '股利政策', '营运资本管理'],
        },
        '法学': {
            '民法': ['民事法律关系', '物权法', '合同法', '侵权责任法', '善意取得制度'],
            '刑法': ['犯罪构成要件', '正当防卫与紧急避险', '共同犯罪', '刑罚体系'],
        },
        'CPA': {
            '会计': ['合并财务报表', '长期股权投资', '收入确认', '金融工具', '租赁'],
            '财务成本管理': ['资本成本计算', '企业价值评估', '投资项目评价', '本量利分析'],
        },
    }
    all_kps = {}
    for subject, chapters in tree.items():
        subj, _ = KnowledgePoint.objects.get_or_create(
            name=subject, defaults={'level': 'sub', 'code': f'SUBJ-{subject[:2]}'})
        all_kps.setdefault(subject, []).append(subj)
        for chapter, sections in chapters.items():
            ch, _ = KnowledgePoint.objects.get_or_create(
                name=chapter, defaults={'level': 'ch', 'parent': subj, 'code': f'CH-{chapter[:4]}'})
            all_kps.setdefault(subject, []).append(ch)
            for section in sections:
                sec, _ = KnowledgePoint.objects.get_or_create(
                    name=section, defaults={'level': 'kp', 'parent': ch, 'code': f'KP-{section[:6]}'})
                all_kps.setdefault(subject, []).append(sec)
    return all_kps


# ── questions ──

def seed_questions(kps_by_subject):
    from quizzes.models import Question
    templates = {
        '金融431': [
            {'text': '在公开市场操作中，中央银行买入政府债券会导致：', 'q_type': 'objective', 'difficulty_level': 'normal', 'difficulty': 1200,
             'options': ['A. 货币供给减少，利率上升', 'B. 货币供给增加，利率下降', 'C. 货币供给不变，利率不变', 'D. 货币供给增加，利率上升'], 'correct_answer': 'B'},
            {'text': '简述凯恩斯流动性偏好理论中货币需求的三大动机。', 'q_type': 'subjective', 'subjective_type': 'short', 'difficulty_level': 'normal', 'difficulty': 1250,
             'grading_points': '1.交易动机（2分）\n2.预防动机（2分）\n3.投机动机（2分）',
             'correct_answer': '凯恩斯认为人们持有货币的动机包括：交易动机——为日常交易需要而持有货币；预防动机——为应对意外支出而持有货币；投机动机——为在债券市场中投机获利而持有货币。'},
            {'text': '根据购买力平价理论，如果中国通货膨胀率高于美国，则人民币应该：', 'q_type': 'objective', 'difficulty_level': 'easy', 'difficulty': 1050,
             'options': ['A. 升值', 'B. 贬值', 'C. 保持不变', 'D. 无法确定'], 'correct_answer': 'B'},
            {'text': '某公司拟投资一个项目，初始投资额100万元，预计未来5年每年产生30万元现金流入，折现率10%。计算NPV并判断是否应该投资。', 'q_type': 'subjective', 'subjective_type': 'calculate', 'difficulty_level': 'hard', 'difficulty': 1450,
             'grading_points': '1.列出现金流（2分）\n2.NPV公式（3分）\n3.结果NPV=13.72万（3分）\n4.判断投资（2分）',
             'correct_answer': 'NPV = -100 + 30/1.1 + 30/1.1² + 30/1.1³ + 30/1.1⁴ + 30/1.1⁵ = 13.72万元 > 0，应投资。'},
            {'text': '货币政策传导机制中，利率渠道的核心逻辑是什么？', 'q_type': 'subjective', 'subjective_type': 'essay', 'difficulty_level': 'hard', 'difficulty': 1500,
             'grading_points': '1.货币供给→利率（3分）\n2.利率→投资（3分）\n3.投资→总产出（2分）\n4.IS-LM图示（2分）',
             'correct_answer': '央行通过货币政策工具改变货币供给→影响市场利率→影响企业投资和居民消费/储蓄→最终影响总需求和总产出。这是凯恩斯主义货币政策理论的核心。'},
        ],
        '法学': [
            {'text': '甲将其电脑交由乙保管，乙未经同意以合理价格出售给不知情的丙。根据《民法典》，丙是否取得所有权？', 'q_type': 'objective', 'difficulty_level': 'normal', 'difficulty': 1250,
             'options': ['A. 取得，丙是善意第三人', 'B. 不能取得，乙无权处分', 'C. 取得但甲可请求赔偿', 'D. 不能取得，电脑属甲'], 'correct_answer': 'A'},
            {'text': '简述正当防卫的成立要件。', 'q_type': 'subjective', 'subjective_type': 'short', 'difficulty_level': 'normal', 'difficulty': 1220,
             'grading_points': '1.防卫起因（2分）\n2.防卫时间（2分）\n3.防卫对象（2分）\n4.防卫限度（2分）',
             'correct_answer': '(1)存在现实的不法侵害；(2)不法侵害正在进行；(3)针对不法侵害者本人；(4)不能明显超过必要限度造成重大损害。'},
            {'text': '张三与李四签房屋买卖合同200万，张三付50万首付后李四反悔。李四辩称该房是唯一住房无法交付。法院如何处理？', 'q_type': 'subjective', 'subjective_type': 'essay', 'difficulty_level': 'hard', 'difficulty': 1520,
             'grading_points': '1.合同效力（3分）\n2.继续履行条件（3分）\n3.唯一住房抗辩（2分）\n4.替代救济（2分）',
             'correct_answer': '合同有效，张三有权请求继续履行。唯一住房不构成免除履行义务的法定事由。如房屋已转善意第三人致无法履行，张三可主张违约损害赔偿。'},
        ],
        'CPA': [
            {'text': '合并财务报表中，母公司对子公司的长期股权投资应采用什么方法进行后续计量？', 'q_type': 'objective', 'difficulty_level': 'normal', 'difficulty': 1280,
             'options': ['A. 成本法', 'B. 权益法', 'C. 成本法，合并底稿中调为权益法', 'D. 公允价值法'], 'correct_answer': 'C'},
            {'text': '甲公司持有乙公司80%股权。甲公司售商品给乙公司，成本60万售价100万，乙公司当年全部对外出售。编制合并抵销分录。', 'q_type': 'subjective', 'subjective_type': 'calculate', 'difficulty_level': 'hard', 'difficulty': 1550,
             'grading_points': '1.识别内部交易（2分）\n2.抵销分录（5分）\n3.抵销逻辑（3分）',
             'correct_answer': '借：营业收入 100万\n  贷：营业成本 100万\n乙公司已全部对外出售，内部交易损益已实现，仅需抵销内部销售收入和成本。'},
            {'text': '企业用CAPM计算权益资本成本：Rf=3%，市场风险溢价=7%，β=1.2。计算权益资本成本。', 'q_type': 'subjective', 'subjective_type': 'calculate', 'difficulty_level': 'easy', 'difficulty': 1100,
             'grading_points': '1.CAPM公式（3分）\n2.带入参数（3分）\n3.结果11.4%（4分）',
             'correct_answer': '权益资本成本 = Rf + β×(Rm-Rf) = 3% + 1.2×7% = 11.4%'},
        ],
    }

    created = {}
    for subject, question_list in templates.items():
        kps = kps_by_subject.get(subject, [])
        leaf_kps = [kp for kp in kps if kp.level == 'kp'] or kps
        subject_questions = []
        for i, tmpl in enumerate(question_list):
            kp = leaf_kps[i % len(leaf_kps)]
            q, _ = Question.objects.get_or_create(text=tmpl['text'], defaults={
                'knowledge_point': kp, 'q_type': tmpl.get('q_type', 'objective'),
                'subjective_type': tmpl.get('subjective_type'),
                'difficulty_level': tmpl.get('difficulty_level', 'normal'),
                'difficulty': tmpl.get('difficulty', 1200),
                'options': tmpl.get('options'), 'correct_answer': tmpl.get('correct_answer'),
                'grading_points': tmpl.get('grading_points'),
            })
            subject_questions.append(q)
        for i in range(3):
            kp = leaf_kps[(len(question_list) + i) % len(leaf_kps)]
            q, _ = Question.objects.get_or_create(
                text=f'[{subject}] 模拟选择题 #{i+1}：关于{kp.name}的正确表述是？',
                defaults={'knowledge_point': kp, 'q_type': 'objective',
                          'difficulty_level': random.choice(['easy', 'normal', 'hard']),
                          'difficulty': random.randint(1000, 1500),
                          'options': ['A. 选项A', 'B. 选项B', 'C. 选项C', 'D. 选项D'],
                          'correct_answer': random.choice(['A', 'B', 'C', 'D'])})
            subject_questions.append(q)
        created[subject] = subject_questions
    return created


# ── exams + FSRS (all in last 7 days) ──

def seed_exams_and_fsrs(admin, students, all_questions):
    from quizzes.models import (
        QuizExam, ExamQuestionResult, QuizAttempt,
        UserQuestionStatus, UserKnowledgeState, FSRSProfile,
        ReviewLog, FSRSOptimizationLog, KnowledgePoint,
    )

    all_qs = [q for qs in all_questions.values() for q in qs]
    if not all_qs:
        return

    for student in students:
        # FSRS profile
        FSRSProfile.objects.get_or_create(user=student, defaults={
            'weights': [0.5, 0.5, 1.0, 2.0, 0.1, 1.5, 0.2, 0.8,
                       0.01, 0.6, 1.2, 0.05, 0.3, 1.0, 0.15, 1.8, 0.0],
            'last_optimized_at': days_ago(2), 'total_reviews_used': random.randint(150, 400),
            'current_loss': round(random.uniform(0.15, 0.30), 4),
        })

        # FSRS optimization — one entry per day for days 7,5,3,1 ago
        for d in [7, 5, 3, 1]:
            prev = round(random.uniform(0.28, 0.45), 4)
            new = round(prev * random.uniform(0.72, 0.88), 4)
            note = f'FSRS参数第{random.randint(1,5)}次在线调优'
            # Don't include created_at in filter — auto_now_add would break get_or_create
            opt_log, created = FSRSOptimizationLog.objects.get_or_create(
                user=student, note=note,
                defaults={'previous_loss': prev, 'new_loss': new,
                          'improvement_ratio': round((prev - new) / prev * 100, 1),
                          'reviews_used': random.randint(40, 180), 'accepted': True})
            if created:
                fix_auto_now(FSRSOptimizationLog, opt_log.pk, created_at=days_ago(d, 10))

        # ── 7 daily exams (days 7..1 ago) ──
        scores_trend = []
        base_score = random.randint(55, 70)
        for day in range(7, 0, -1):
            score = min(98, base_score + random.randint(-3, 8))
            base_score = score
            scores_trend.append(score)
            exam_ts = days_ago(day, random.randint(9, 21))
            exam = QuizExam.objects.create(
                user=student, total_score=score, max_score=100,
                elo_change=random.randint(-5, 20),
                summary=f'第{8 - day}天 · 模拟练习',
            )
            fix_auto_now(QuizExam, exam.pk, created_at=exam_ts)
            exam_qs = random.sample(all_qs, min(random.randint(5, 8), len(all_qs)))
            for q in exam_qs:
                correct = random.random() > 0.35
                mx = 10
                ExamQuestionResult.objects.create(
                    exam=exam, question=q,
                    user_answer=q.correct_answer if correct else '考生答案（模拟）',
                    score=mx if correct else random.randint(0, int(mx * 0.6)),
                    max_score=mx, is_correct=correct,
                    feedback='回答正确！' if correct else '请注意该知识点。')
            attempt = QuizAttempt.objects.create(user=student, score=score,
                                                  elo_change=exam.elo_change)
            fix_auto_now(QuizAttempt, attempt.pk, created_at=exam_ts)

        # ── UserQuestionStatus (FSRS per-question) ──
        for q in all_qs:
            wc = random.randint(0, 3)
            reps = random.randint(1, 7)
            UserQuestionStatus.objects.get_or_create(user=student, question=q, defaults={
                'is_favorite': random.random() > 0.7, 'is_mastered': random.random() > 0.5,
                'wrong_count': wc, 'stability': round(random.uniform(0.8, 18.0), 2),
                'difficulty': round(random.uniform(0.1, 0.9), 2),
                'reps': reps, 'lapses': min(wc, reps - 1),
                'last_review': rand_time(0, 7), 'last_correct': random.random() > 0.3,
            })

        # ── UserKnowledgeState ──
        seen = set()
        for q in all_qs:
            if q.knowledge_point and q.knowledge_point.id not in seen:
                seen.add(q.knowledge_point.id)
                UserKnowledgeState.objects.get_or_create(
                    user=student, knowledge_point=q.knowledge_point,
                    defaults={'mastery_score': round(random.uniform(0.25, 0.95), 2)})

        # ── ReviewLogs: ~3 per day for last 7 days ──
        # NOTE: review_time has auto_now_add=True. Django's bulk_create also
        # overrides auto_now_add fields, so we must .create() + .update().
        kp_list = list(KnowledgePoint.objects.filter(level='kp'))
        for day in range(7):
            for _ in range(3):
                log = ReviewLog.objects.create(
                    user=student,
                    knowledge_point=random.choice(kp_list),
                    grade=random.choices([1, 2, 3, 4], weights=[10, 18, 42, 30])[0],
                    elapsed_days=round(random.uniform(0.5, 14.0), 1),
                    predicted_retrievability=round(random.uniform(0.3, 0.95), 2),
                )
                fix_auto_now(ReviewLog, log.pk,
                             review_time=days_ago(day, random.randint(8, 22)))


# ── pipeline tasks (last 7 days) ──

def seed_pipeline_tasks(admin, kps_by_subject):
    from quizzes.models import ContentPipelineTask, KnowledgePoint

    kp_list = list(KnowledgePoint.objects.filter(level='kp'))
    if not kp_list:
        return

    # spread across last 7 days
    tasks = [
        (7, 'completed'), (7, 'completed'), (6, 'completed'),
        (5, 'completed'), (5, 'review'), (4, 'completed'),
        (3, 'completed'), (3, 'running'), (2, 'completed'),
        (1, 'completed'), (1, 'completed'), (1, 'review'),
        (0, 'running'), (0, 'failed'),
    ]
    for days, status in tasks:
        kp = random.choice(kp_list)
        created_ts = days_ago(days, random.randint(8, 12))
        started_ts = days_ago(days, random.randint(8, 18))
        finished_ts = days_ago(days, random.randint(14, 22)) if status in ('completed', 'failed') else None
        task = ContentPipelineTask.objects.create(
            task_type='ai_generate', status=status,
            title=f'智能出题：{kp.name}',
            description=f'知识点：{kp.name} | 数量：5道 | 题型：选择题+简答题 | 难度：中等',
            progress=100 if status == 'completed' else (55 if status == 'running' else 0),
            payload={'knowledge_point_id': kp.id, 'count': 5, 'difficulty': 'normal',
                     'question_types': ['objective', 'short']},
            result={'generated': 5, 'passed_review': random.randint(3, 5),
                    'quality_scores': [round(random.uniform(0.7, 0.95), 2) for _ in range(5)]}
            if status == 'completed' else {},
            error_message='AI 服务超时，请重试' if status == 'failed' else '',
            created_by=admin, assignee=admin,
        )
        fix_auto_now(ContentPipelineTask, task.pk,
                     created_at=created_ts, started_at=started_ts, finished_at=finished_ts)


# ── courses ──

def seed_courses(admin, kps_by_subject):
    from courses.models import Album, Course
    from quizzes.models import KnowledgePoint

    for name, desc in [('金融431 核心课程', '货币银行学、国际金融、公司理财三大模块'),
                       ('法学考研精讲', '民法与刑法核心考点深度解析')]:
        Album.objects.get_or_create(name=name, defaults={'description': desc})

    albums = list(Album.objects.all())
    courses_data = [
        ('货币银行学精讲', 0, '覆盖黄达《金融学》核心内容，货币政策、利率、通胀等'),
        ('国际金融与汇率理论', 0, '汇率决定、国际收支、开放经济政策'),
        ('公司理财与资本预算', 0, 'NPV/IRR/资本结构/股利政策——计算题突破'),
        ('民法总论与物权法', 1, '民事法律关系、物权变动、善意取得'),
        ('刑法总论', 1, '犯罪构成、正当防卫、共同犯罪——案例题专项'),
    ]
    kp_list = list(KnowledgePoint.objects.filter(level='kp'))
    for i, (title, aidx, desc) in enumerate(courses_data):
        Course.objects.get_or_create(title=title, defaults={
            'album_obj': albums[aidx], 'description': desc,
            'knowledge_point': kp_list[i % len(kp_list)] if kp_list else None,
            'elo_reward': random.choice([30, 50, 80]), 'author': admin,
        })


# ── Q&A (last 7 days) ──

def seed_qa_threads(admin, students):
    from faq_system.models import Question as QAQuestion, Answer

    threads = [
        {'content': '货币政策传导机制中，信贷渠道和利率渠道的主要区别是什么？论述题应该如何组织答案？', 'is_solved': True,
         'answers': [('利率渠道强调货币供给→利率→投资→产出的传导路径，核心是资金价格机制。信贷渠道则强调银行信贷的特殊作用。论述建议先概述两种渠道定义，再对比传导机制差异，最后结合实际案例。', True)]},
        {'content': '合并报表中内部交易的抵销分录总是记不住，有什么好的记忆方法？', 'is_solved': True,
         'answers': [('核心原则：合并报表反映的是集团与外部第三方交易，内部交易全部抵销。存货→抵销收入成本；固资→抵销处置损益并调整折旧。多做题就熟了。', True),
                     ('补充：画交易关系图，把母子公司的资金流画出来，抵销分录就是把这些线擦掉。', False)]},
        {'content': '法学考研的案例分析题有没有答题模板？每次做案例题都不知道从哪里入手。', 'is_solved': False,
         'answers': [('建议三段论：1.提炼案件事实中的法律要素；2.找到对应法律规范；3.事实与规范比对分析得出结论。多加练习自然熟练。', True)]},
    ]
    for td in threads:
        asker = random.choice(students)
        q, created = QAQuestion.objects.get_or_create(content=td['content'], user=asker, defaults={
            'is_solved': td['is_solved'], 'is_starred': random.random() > 0.5,
        })
        if created:
            fix_auto_now(QAQuestion, q.pk,
                         created_at=days_ago(random.randint(0, 6), random.randint(9, 20)))
        for content, is_teacher in td['answers']:
            answerer = admin if is_teacher else random.choice(students)
            Answer.objects.get_or_create(question=q, content=content, user=answerer,
                                         defaults={'is_teacher': is_teacher})


# ── study room (last 7 days) ──

def seed_study_room(admin, students):
    from study_room.models import ChatMessage, StudyPlan, WeeklyTask

    for student in students[:3]:
        StudyPlan.objects.get_or_create(user=student, defaults={
            'target_date': (timezone.now() + timedelta(days=random.randint(90, 180))).date(),
            'target_score': random.choice([120, 130, 140]),
            'daily_hours': round(random.uniform(3.0, 6.0), 1),
            'weekly_summary': '本周重点复习货币政策与汇率理论，完成对应题库练习。',
        })
        for title, status in [('完成货币银行学选择题 50 道', 'pending'),
                              ('复习国际金融汇率理论', 'in_progress'),
                              ('整理错题笔记', 'completed')]:
            WeeklyTask.objects.get_or_create(user=student, title=title, defaults={
                'status': status, 'week_start': date.today() - timedelta(days=3),
                'week_end': date.today() + timedelta(days=4),
            })

    # Chat: 2-3 messages per day over last 7 days
    chat_templates = [
        (admin, '同学们，今天的货币银行学选择题练习准备好了吗？', 'chat'),
        (students[0], '准备好了老师！', 'chat'),
        (students[1], '老师，汇率决定理论能再讲讲吗？做题总错。', 'chat'),
        (admin, '汇率这块可以看看知识工作台，你的薄弱点在购买力平价。下午我单独讲。', 'chat'),
        (students[2], '完成了 30 道金融题，正确率 83% 💪', 'task_complete'),
        (students[0], '开始学习：货币政策选择题专项', 'task_start'),
        (admin, '今天正确率不错，继续保持！注意复习一下昨天的错题。', 'chat'),
        (students[3], '刚做完公司理财计算题，NPV那道终于搞懂了', 'chat'),
        (students[4], '明天模考，今晚再刷一遍错题', 'chat'),
        (admin, '模考前看看知识图谱，红色节点优先复习，效果最好。', 'chat'),
    ]
    for day in range(7, -1, -1):
        for tmpl in random.sample(chat_templates, min(2, len(chat_templates))):
            user, content, mtype = tmpl
            msg, created = ChatMessage.objects.get_or_create(
                user=user, content=content, message_type=mtype)
            if created:
                fix_auto_now(ChatMessage, msg.pk,
                             timestamp=days_ago(day, random.randint(8, 22)))


# ── notifications (last 7 days) ──

def seed_notifications(admin, students):
    from notifications.models import Notification
    templates = [
        ('学习提醒', '你今天还有 15 道题待复习，Memorix 建议在遗忘临界点前完成。', 'fsrs_reminder'),
        ('答疑回复', '你在"货币政策传导机制"问题下收到了老师的回复。', 'qa_reply'),
        ('系统通知', 'FSRS 算法已完成在线参数调优，你的个性化复习计划已更新。', 'system'),
        ('学习提醒', '知识工作台中"汇率决定理论"掌握度下降，建议今天复习 10 道相关题目。', 'fsrs_reminder'),
        ('答疑回复', '老师回答了"合并报表抵销分录"的问题。', 'qa_reply'),
    ]
    for student in students[:3]:
        for title, content, ntype in templates:
            notif, created = Notification.objects.get_or_create(
                recipient=student, title=title, defaults={
                    'content': content, 'ntype': ntype,
                    'sender': admin if ntype != 'system' else None,
                    'is_read': random.random() > 0.3,
                })
            if created:
                fix_auto_now(Notification, notif.pk,
                             created_at=days_ago(random.randint(0, 6), random.randint(8, 22)))


# ── knowledge annotations ──

def seed_knowledge_annotations(students, kps_by_subject):
    from quizzes.models import KnowledgePointAnnotation, KnowledgePoint
    kp_list = list(KnowledgePoint.objects.filter(level='kp'))
    weights = {'unknown': 5, 'weak': 20, 'learning': 30, 'stable': 25, 'mastered': 20}
    for student in students:
        for kp in random.sample(kp_list, min(random.randint(10, len(kp_list)), len(kp_list))):
            level = random.choices(list(weights.keys()), weights=list(weights.values()))[0]
            KnowledgePointAnnotation.objects.get_or_create(user=student, knowledge_point=kp, defaults={
                'mastery_level': level, 'confidence_score': random.randint(20, 100),
                'priority': random.choice(['low', 'medium', 'high']),
                'source': random.choice(['auto', 'manual']),
            })


# ── command ──

def reset_demo_data():
    """Delete all demo users (cascades to their related data). Then re-seed clean."""
    from quizzes.models import ContentPipelineTask
    from users.models import Institution
    ContentPipelineTask.objects.filter(created_by__email__endswith='@demo.unimind').delete()
    ContentPipelineTask.objects.filter(created_by__email='demo@unimind.ai').delete()
    User.objects.filter(email__endswith='@demo.unimind').delete()
    User.objects.filter(email='demo@unimind.ai').delete()
    Institution.objects.filter(slug='demo-academy').delete()


def seed_institution(admin, students):
    """Create demo institution and link all demo users to it."""
    from users.models import Institution
    inst, _ = Institution.objects.get_or_create(
        slug='demo-academy',
        defaults={
            'name': '宇艺示范学院',
            'contact_name': admin.nickname or '张老师',
            'contact_email': admin.email,
            'plan': 'plus',
            'created_by': admin,
        }
    )
    admin.institution = inst
    admin.institution_role = 'admin'
    admin.save(update_fields=['institution', 'institution_role'])
    for s in students:
        s.institution = inst
        s.institution_role = 'student'
        s.save(update_fields=['institution', 'institution_role'])
    return inst


class Command(BaseCommand):
    help = 'Seed demo data spanning the last 7 days. Use --reset to clear existing first.'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Delete all demo data before seeding')

    def handle(self, *args, **options):
        if options['reset']:
            self.stdout.write('Resetting demo data...')
            reset_demo_data()

        self.stdout.write('Seeding 7-day demo data...')

        admin = get_or_create_admin()
        students = get_or_create_students(5)
        self.stdout.write(f'  Users: 1 admin + {len(students)} students')

        kps_by_subject = build_knowledge_tree()
        self.stdout.write(f'  Knowledge points: {sum(len(v) for v in kps_by_subject.values())} across {len(kps_by_subject)} subjects')

        questions = seed_questions(kps_by_subject)
        self.stdout.write(f'  Questions: {sum(len(v) for v in questions.values())}')

        seed_exams_and_fsrs(admin, students, questions)
        self.stdout.write('  Exams (7 daily) + FSRS + ReviewLogs (3/day): done')

        seed_pipeline_tasks(admin, kps_by_subject)
        self.stdout.write('  AI pipeline tasks (14 across 7 days): done')

        seed_courses(admin, kps_by_subject)
        self.stdout.write('  Courses + Albums: done')

        seed_qa_threads(admin, students)
        self.stdout.write('  Q&A threads: done')

        seed_study_room(admin, students)
        self.stdout.write('  Study room (2-3 msgs/day for 7 days): done')

        seed_notifications(admin, students)
        self.stdout.write('  Notifications (5 per student, last 7 days): done')

        inst = seed_institution(admin, students)
        self.stdout.write(f'  Institution: {inst.name} ({inst.get_plan_display()}) — {inst.student_count} students')

        seed_knowledge_annotations(students, kps_by_subject)
        self.stdout.write('  Knowledge annotations (heatmap): done')

        self.stdout.write(self.style.SUCCESS(
            '\n✅ 7-day demo data seeded!\n'
            '   Admin: demo@unimind.ai / demo123456\n'
            '   Student: student1@demo.unimind / demo123456\n'
            '   All activity spans Day -7 → today 📊'
        ))
