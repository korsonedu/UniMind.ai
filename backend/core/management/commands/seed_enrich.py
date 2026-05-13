"""
Enrich mock data with cover images (UniMind logo) and English content.
Run AFTER `python manage.py seed_demo` for best results.
Idempotent — safe to run multiple times.

Usage: python manage.py seed_enrich
"""
import os
from django.core.files import File
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()
LOGO_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..',
                         'frontend', 'Unimind_logo.png')


def _logo():
    """Return a File wrapper for the UniMind logo, or None if missing."""
    path = os.path.abspath(LOGO_PATH)
    if not os.path.exists(path):
        return None
    return File(open(path, 'rb'), name='unimind_logo.png')


# ── Courses: add covers + English content ──

def enrich_courses():
    from courses.models import Album, Course
    from quizzes.models import KnowledgePoint
    logo = _logo()

    # ── Albums ──
    albums = [
        ('金融431 核心课程', '货币银行学、国际金融、公司理财三大模块系统精讲 · Systematic Finance'),
        ('法学考研精讲', '民法与刑法核心考点深度解析 · Legal Studies Essentials'),
        ('English Finance Series', 'International finance concepts explained in English for bilingual learners'),
        ('CPA 财务成本管理', '资本成本、企业估值、投资评价 —— 计算题专项突破'),
        ('Macroeconomics Foundations', 'Monetary policy, exchange rates, and open-economy macro models'),
    ]
    album_objs = {}
    for name, desc in albums:
        alb, _ = Album.objects.get_or_create(name=name, defaults={'description': desc})
        if logo and not alb.cover_image:
            alb.cover_image.save('album_cover.png', logo, save=True)
            # Re-open logo after each save since ImageField consumes the file handle
            logo.close()
            logo = _logo()
        album_objs[name] = alb

    kp_list = list(KnowledgePoint.objects.filter(level='kp'))
    if not kp_list:
        from quizzes.models import KnowledgePoint as KP
        KP.objects.get_or_create(name='金融431', defaults={'level': 'sub', 'code': 'SUBJ-01'})
        kp_list = list(KP.objects.filter(level='kp'))

    courses = [
        # ── Chinese ──
        ('货币银行学精讲', album_objs.get('金融431 核心课程'),
         '覆盖黄达《金融学》核心内容：货币与货币制度、利息与利率决定理论、货币政策工具与传导机制、通货膨胀与通货紧缩。适合零基础入门。',
         kp_list[0] if kp_list else None),
        ('国际金融与汇率理论', album_objs.get('金融431 核心课程'),
         '汇率决定理论（购买力平价/利率平价/资产市场说）、国际收支调节机制、开放经济下的宏观经济政策。奚君羊+姜波克体系。',
         kp_list[1] if len(kp_list) > 1 else None),
        ('公司理财与资本预算', album_objs.get('金融431 核心课程'),
         'NPV/IRR 计算专题、资本结构理论（MM定理/权衡理论）、股利政策、营运资本管理。Ross+Bodie 双教材精讲。',
         kp_list[2] if len(kp_list) > 2 else None),
        ('民法总论与物权法', album_objs.get('法学考研精讲'),
         '民事法律关系构成、物权变动模式、善意取得制度、担保物权体系。每章配套案例题讲解。',
         kp_list[3] if len(kp_list) > 3 else None),
        ('刑法总论', album_objs.get('法学考研精讲'),
         '犯罪构成四要件/三阶层、正当防卫与紧急避险的界限、共同犯罪形态、刑罚裁量。',
         kp_list[4] if len(kp_list) > 4 else None),
        ('合并财务报表专题', album_objs.get('CPA 财务成本管理'),
         '长期股权投资核算方法转换、内部交易抵销（存货/固资/债权债务）、合并工作底稿编制。',
         kp_list[0] if kp_list else None),
        ('企业价值评估', album_objs.get('CPA 财务成本管理'),
         'DCF 模型、相对估值法（PE/PB/PS）、CAPM 计算权益资本成本、WACC 加权平均资本成本。',
         kp_list[1] if len(kp_list) > 1 else None),
        # ── English ──
        ('Monetary Policy & Central Banking', album_objs.get('English Finance Series'),
         'Open market operations, discount window, reserve requirements, quantitative easing. '
         'Key readings: Mishkin ch.15-17, Romer ch.10. Includes case studies on Fed and ECB policy responses.',
         kp_list[0] if kp_list else None),
        ('Exchange Rate Determination', album_objs.get('English Finance Series'),
         'Purchasing Power Parity (absolute/relative), Interest Rate Parity (covered/uncovered), '
         'Asset Market Approach, Dornbusch Overshooting Model. Krugman & Obstfeld framework.',
         kp_list[1] if len(kp_list) > 1 else None),
        ('Corporate Finance: Capital Budgeting', album_objs.get('English Finance Series'),
         'NPV, IRR, Payback Period, Profitability Index. Incremental cash flows, '
         'sunk costs, opportunity costs, externalities. Ross ch.5-7 + case studies.',
         kp_list[2] if len(kp_list) > 2 else None),
        ('Intermediate Macroeconomics', album_objs.get('Macroeconomics Foundations'),
         'IS-LM model, AD-AS framework, Phillips Curve, Solow growth model. '
         'Mankiw & Blanchard textbooks. Emphasis on policy implications and empirical evidence.',
         kp_list[0] if kp_list else None),
        ('International Trade & Finance', album_objs.get('Macroeconomics Foundations'),
         'Comparative advantage, Heckscher-Ohlin model, trade policy instruments, '
         'balance of payments, Mundell-Fleming model. WTO and regional trade agreements.',
         kp_list[1] if len(kp_list) > 1 else None),
    ]

    admin = User.objects.filter(is_superuser=True).first()
    created = 0
    for title, album, desc, kp in courses:
        if album is None:
            continue
        _, is_new = Course.objects.get_or_create(
            title=title,
            defaults={
                'album_obj': album, 'description': desc,
                'knowledge_point': kp, 'elo_reward': [30, 50, 80][created % 3],
                'author': admin,
            })
        if is_new:
            created += 1

    # Add logo cover to courses that don't have one
    if logo:
        for course in Course.objects.filter(cover_image=''):
            course.cover_image.save('course_cover.png', logo, save=True)
            logo.close()
            logo = _logo()
        print(f'  Course covers: set on {Course.objects.exclude(cover_image="").count()} courses')
    else:
        print('  ⚠️  Logo not found, skipped image assignment')
    print(f'  Courses: {created} new, {Course.objects.count()} total')


# ── Articles: rich content + English ──

def enrich_articles():
    from articles.models import Article
    from quizzes.models import KnowledgePoint
    logo = _logo()
    admin = User.objects.filter(is_superuser=True).first()

    kp_list = list(KnowledgePoint.objects.filter(level='kp'))
    if not kp_list:
        kp_list = [None] * 10

    articles = [
        # ── Chinese ──
        ('货币政策传导机制深度解析', kp_list[0 % len(kp_list)],
         """## 货币政策传导机制：从理论到实践

货币政策传导机制描述央行通过货币政策工具如何影响实体经济的过程。理解传导机制是金融考研的核心考点。

### 1. 利率渠道（凯恩斯主义）

央行改变货币供给 → 影响市场利率 → 企业投资和居民消费变化 → 总需求变化 → 产出变化。

**核心公式：** $M \\uparrow \\Rightarrow r \\downarrow \\Rightarrow I \\uparrow \\Rightarrow Y \\uparrow$

### 2. 信贷渠道

强调银行信贷的特殊作用，分为银行贷款渠道和资产负债表渠道。

### 3. 资产价格渠道

托宾 q 理论和财富效应。当货币供给增加 → 股价上升 → q 值上升 → 企业增加投资。

### 总结

不同渠道相互补充，共同构成货币政策传导的完整机制。考试侧重利率渠道和信贷渠道的对比分析。""", ['货币政策', '利率', '考研']),
        ('汇率决定理论对比：PPP vs IRP vs 资产市场说', kp_list[1 % len(kp_list)],
         """## 三大汇率决定理论

### 购买力平价（PPP）

**绝对形式：** $S = \\frac{P}{P^*}$

**相对形式：** $\\frac{\\Delta S}{S} = \\pi - \\pi^*$

核心逻辑：一价定律 → 商品市场套利 → 汇率调整。

### 利率平价（IRP）

**抵补利率平价：** $\\frac{F - S}{S} = i - i^*$

**非抵补利率平价：** $E(\\Delta S) = i - i^*$

核心逻辑：资本自由流动 → 套利 → 远期汇率调整。

### 资产市场说

汇率由资产市场均衡决定。货币供给、国民收入、通胀预期等变量通过货币需求函数影响汇率。

### 考试建议

重点掌握 PPP 和 IRP 的推导过程，以及各自的成立条件。""", ['汇率', '国际金融', 'PPP']),
        ('NPV vs IRR：资本预算决策方法比较', kp_list[2 % len(kp_list)],
         """## NPV 与 IRR 的深度比较

### 净现值法（NPV）

$$NPV = \\sum_{t=1}^{n} \\frac{CF_t}{(1+r)^t} - I_0$$

**决策准则：** NPV > 0 → 接受项目

**优点：** 直接衡量价值创造；使用实际折现率；无多重解问题

### 内部收益率法（IRR）

$$0 = \\sum_{t=1}^{n} \\frac{CF_t}{(1+IRR)^t} - I_0$$

**决策准则：** IRR > r → 接受项目

**局限性：**
- 非常规现金流可能导致多重 IRR
- 互斥项目可能与 NPV 结论矛盾
- 隐含再投资收益率假设不现实

### 互斥项目冲突

当项目规模或现金流时间分布差异大时，NPV 和 IRR 可能给出不同建议。此时以 **NPV 结论为准**。""", ['公司理财', 'NPV', '资本预算']),
        ('善意取得制度详解', kp_list[3 % len(kp_list)],
         """## 善意取得制度：保护交易安全的核心

### 构成要件

1. **无权处分**：处分人无处分权（或处分权受限）
2. **有偿行为**：须以合理价格进行交易
3. **善意**：受让人不知且不应知处分人无权
4. **完成公示**：动产已交付 / 不动产已登记

### 法理基础

善意取得是物权公示公信原则的体现，在真实权利人与善意第三人之间，法律选择保护交易安全。

### 典型例题

> 甲将电脑交由乙保管，乙以市价出售给不知情的丙并交付。问：丙是否取得所有权？

**答案：** 丙善意取得所有权，甲可向乙主张违约或侵权损害赔偿。""", ['民法', '物权法', '善意取得']),
        # ── English ──
        ('Understanding the IS-LM Model', kp_list[4 % len(kp_list)],
         """## The IS-LM Framework

The IS-LM model, developed by Hicks (1937), formalizes Keynes' General Theory into a
tractable general-equilibrium framework.

### IS Curve: Goods Market Equilibrium

$$Y = C(Y - T) + I(r) + G$$

The IS curve slopes downward: lower interest rates stimulate investment, raising output.

### LM Curve: Money Market Equilibrium

$$\\frac{M}{P} = L(Y, r)$$

The LM curve slopes upward: higher output increases money demand, requiring higher
interest rates to restore equilibrium.

### Policy Analysis

| Policy | Shift | Effect on Y | Effect on r |
|--------|-------|-------------|-------------|
| Fiscal expansion | IS right | ↑ | ↑ |
| Monetary expansion | LM right | ↑ | ↓ |
| Mixed (both) | Both right | ↑↑ | ? |

### Limitations

- Fixed price level (no inflation dynamics)
- Closed economy assumption
- Static expectations""", ['macroeconomics', 'IS-LM', 'Keynes']),
        ('CAPM: Theory and Applications', kp_list[0 % len(kp_list)],
         """## Capital Asset Pricing Model

### The Model

$$E(R_i) = R_f + \\beta_i [E(R_m) - R_f]$$

Where:
- $E(R_i)$ = expected return on asset $i$
- $R_f$ = risk-free rate
- $\\beta_i$ = systematic risk measure
- $E(R_m) - R_f$ = market risk premium

### Key Assumptions

1. Investors are mean-variance optimizers
2. Homogeneous expectations
3. No taxes or transaction costs
4. Unlimited borrowing and lending at $R_f$
5. Perfectly divisible assets

### Beta Interpretation

| Beta | Interpretation |
|------|---------------|
| β = 1 | Moves with market |
| β > 1 | More volatile than market |
| β < 1 | Less volatile than market |
| β = 0 | Uncorrelated with market |

### Practice Problem

> Given $R_f = 3\\%$, $E(R_m) = 10\\%$, $\\beta = 1.2$, calculate $E(R_i)$.

$$E(R_i) = 3\\% + 1.2 \\times (10\\% - 3\\%) = 11.4\\%$$""", ['CAPM', 'finance', 'asset pricing']),
        ('Mundell-Fleming Model: Open Economy Macroeconomics', kp_list[1 % len(kp_list)],
         """## The Mundell-Fleming Model

### IS* Curve

$$Y = C(Y - T) + I(r^*) + G + NX(e)$$

Under perfect capital mobility, the domestic interest rate equals the world rate: $r = r^*$.

### LM* Curve

$$\\frac{M}{P} = L(r^*, Y)$$

Money market equilibrium at the world interest rate.

### Policy Effectiveness

| Exchange Rate Regime | Fiscal Policy | Monetary Policy | Trade Policy |
|---------------------|---------------|-----------------|--------------|
| Floating | Ineffective | Effective | Ineffective |
| Fixed | Effective | Ineffective | Effective |

### The Impossible Trinity

A country cannot simultaneously maintain:
1. Free capital mobility
2. Fixed exchange rate
3. Independent monetary policy

This is the central insight of open-economy macroeconomics. Choose two, sacrifice one.""", ['Mundell-Fleming', 'open economy', 'exchange rate']),
    ]

    created = 0
    for title, kp, content, tags in articles:
        _, is_new = Article.objects.get_or_create(
            title=title,
            defaults={
                'knowledge_point': kp, 'content': content, 'tags': tags,
                'author': admin, 'author_display_name': admin.nickname if admin else '张老师',
                'views': (len(content) * 3) % 1500,
            })
        if is_new:
            created += 1

    if logo:
        for art in Article.objects.filter(cover_image=''):
            art.cover_image.save('article_cover.png', logo, save=True)
            logo.close()
            logo = _logo()
        print(f'  Article covers: set on {Article.objects.exclude(cover_image="").count()} articles')

    print(f'  Articles: {created} new, {Article.objects.count()} total')


# ── Startup Materials ──

def enrich_startup_materials():
    from courses.models import StartupMaterial
    admin = User.objects.filter(is_superuser=True).first()

    materials = [
        ('金融431 考试大纲 2027', '教育部最新发布的金融硕士431科目考试大纲完整版'),
        ('黄达《金融学》电子版', '经典教材电子版，适合基础阶段系统学习'),
        ('罗斯《公司理财》第11版 习题解答', 'Chapter 1-31 全部课后习题详细解答（英文原版）'),
        ('历年真题汇编 2019-2026', '全国重点院校金融431真题汇总，含选择题+简答+论述'),
        ('金融英语核心词汇表', '200+ 金融专业术语中英对照，附例句'),
        ('Ross Corporate Finance 11e Solutions', 'Complete solutions manual for all end-of-chapter problems'),
        ('Mishkin Money & Banking 13e Slides', 'Lecture slides for all 25 chapters, English edition'),
    ]
    created = 0
    for name, desc in materials:
        _, is_new = StartupMaterial.objects.get_or_create(
            name=name, defaults={'description': desc})
        if is_new:
            created += 1
    print(f'  Startup Materials: {created} new, {StartupMaterial.objects.count()} total')


# ── Additional English questions ──

def enrich_questions():
    from quizzes.models import Question, KnowledgePoint
    kp_list = list(KnowledgePoint.objects.filter(level='kp'))
    if not kp_list:
        kp_list = [None] * 10

    english_questions = [
        {
            'text': 'If the central bank conducts an open market purchase of government bonds, what happens to the money supply and interest rates?',
            'q_type': 'objective',
            'difficulty_level': 'normal', 'difficulty': 1200,
            'options': ['A. Money supply decreases, interest rates rise', 'B. Money supply increases, interest rates fall',
                        'C. Money supply unchanged, interest rates unchanged', 'D. Money supply increases, interest rates rise'],
            'correct_answer': 'B',
            'knowledge_point': kp_list[0 % len(kp_list)],
        },
        {
            'text': 'Explain the three motives for holding money according to Keynesian liquidity preference theory.',
            'q_type': 'subjective',
            'subjective_type': 'short',
            'difficulty_level': 'normal', 'difficulty': 1250,
            'grading_points': '1. Transactions motive (2pts)\n2. Precautionary motive (2pts)\n3. Speculative motive (2pts)',
            'correct_answer': 'Keynes identified three motives: (1) Transactions motive — holding money for everyday purchases; (2) Precautionary motive — holding money for unexpected expenses; (3) Speculative motive — holding money to speculate on bond price movements.',
            'knowledge_point': kp_list[0 % len(kp_list)],
        },
        {
            'text': 'A company is considering a project with initial investment of $1,000,000. Expected annual cash inflows are $300,000 for 5 years. The discount rate is 10%. Calculate the NPV and recommend whether to invest.',
            'q_type': 'subjective',
            'subjective_type': 'calculate',
            'difficulty_level': 'hard', 'difficulty': 1450,
            'grading_points': '1. Cash flow timeline (2pts)\n2. NPV formula (3pts)\n3. NPV = $137,200 (3pts)\n4. Investment decision (2pts)',
            'correct_answer': 'NPV = -1,000,000 + 300,000/1.1 + 300,000/1.1² + 300,000/1.1³ + 300,000/1.1⁴ + 300,000/1.1⁵ = $137,200 > 0. Since NPV > 0, the project should be accepted.',
            'knowledge_point': kp_list[2 % len(kp_list)],
        },
        {
            'text': 'According to the Purchasing Power Parity theory, if the inflation rate in China is higher than in the US, the RMB should:',
            'q_type': 'objective',
            'difficulty_level': 'easy', 'difficulty': 1050,
            'options': ['A. Appreciate', 'B. Depreciate', 'C. Remain unchanged', 'D. Cannot be determined'],
            'correct_answer': 'B',
            'knowledge_point': kp_list[1 % len(kp_list)],
        },
        {
            'text': 'Calculate the cost of equity using CAPM: risk-free rate = 3%, market risk premium = 7%, beta = 1.2.',
            'q_type': 'subjective',
            'subjective_type': 'calculate',
            'difficulty_level': 'easy', 'difficulty': 1100,
            'grading_points': '1. CAPM formula (3pts)\n2. Substitution (3pts)\n3. Result 11.4% (4pts)',
            'correct_answer': 'Cost of equity = Rf + β × (Rm - Rf) = 3% + 1.2 × 7% = 11.4%',
            'knowledge_point': kp_list[0 % len(kp_list)],
        },
    ]

    created = 0
    for tmpl in english_questions:
        kp = tmpl.pop('knowledge_point', None)
        _, is_new = Question.objects.get_or_create(text=tmpl['text'], defaults={
            **tmpl, 'knowledge_point': kp,
        })
        if is_new:
            created += 1

    print(f'  English Questions: {created} new')
    print(f'  Total Questions: {Question.objects.count()}')


# ── More daily plans for richer demo ──

def enrich_daily_plans():
    from users.models import DailyPlan
    import random
    students = User.objects.filter(email__endswith='@demo.unimind')
    plans = [
        '完成货币银行学选择题 30 道', '复习国际金融汇率理论笔记',
        '整理本周错题集', 'FSRS 记忆复习：货币政策 + 通胀',
        '阅读公司理财第5章', '做一套金融431模拟卷',
        '背英语单词 50 个', '看教学视频：汇率决定理论',
        '完成 CAPM 练习题', 'Review IS-LM model notes',
        'Practice 20 MCQs on monetary policy', 'Read Bodie Investments ch.7',
        'Study session: 2 hours focused', 'Peer discussion: exchange rate regimes',
    ]
    created = 0
    for student in students:
        for _ in range(5):
            content = random.choice(plans)
            _, is_new = DailyPlan.objects.get_or_create(
                user=student, content=content,
                defaults={'is_completed': random.random() > 0.4})
            if is_new:
                created += 1
    print(f'  Daily Plans: {created} new')


# ── Articles with both CN/EN ──


# ── Command ──

class Command(BaseCommand):
    help = 'Enrich demo data: course/article covers (logo), English content, more variety.'

    def handle(self, *args, **options):
        self.stdout.write('Enriching demo data...\n')

        enrich_courses()
        self.stdout.write('')

        enrich_articles()
        self.stdout.write('')

        enrich_startup_materials()
        self.stdout.write('')

        enrich_questions()
        self.stdout.write('')

        enrich_daily_plans()

        self.stdout.write(self.style.SUCCESS(
            '\n✅ Demo data enriched!\n'
            '   Courses now have cover images.\n'
            '   English courses + articles + questions added.\n'
            '   Ready for screen recording.'
        ))
