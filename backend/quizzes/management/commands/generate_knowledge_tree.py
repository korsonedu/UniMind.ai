import os
from django.core.management.base import BaseCommand
from ai_engine.ai_service import AIService


PROMPT_TEMPLATE = """你是一位教育课程设计专家。请为「{subject}」生成一份完整的知识点树（知识图谱），用于 AI 出题系统的知识体系基础。

## 输出格式要求

严格使用以下 Markdown 层级格式，不得偏离：

```
# [SUB-01] 科目模块名称（英文名）
## [CH-01] 章名称
### [SEC-01] 节名称
- [KP-01] 知识点名称
```

## 规模要求

- 4-8 个 SUB（一级模块）
- 每个 SUB 下 3-8 个 CH（章）
- 每个 CH 下 2-6 个 SEC（节）
- 每个 SEC 下 3-10 个 KP（知识点）
- 每个知识点的 code 格式：KP-序号，每节内从 01 开始重新编号

## 内容要求

1. 覆盖该学科的核心知识体系，基于公开考纲和主流教材
2. 知识点颗粒度适中：既不能太粗（一个 KP 涵盖过大范围），也不能太细（拆分到无意义的细节）
3. 名称后可加括号备注英文，如 `[SUB-01] 货币银行学（Monetary Banking）`
4. 知识点名称简洁明确，一句话说清是什么

## 学科背景

{subject_context}

请直接输出 Markdown，不要加任何前言后语。"""

SUBJECT_CONTEXTS = {
    '法学': '法学硕士（法律硕士）全国联考核心知识体系，涵盖法理学、宪法学、法制史、民法学、刑法学、行政法学、诉讼法学等核心科目。',
    '计算机408': '全国硕士研究生招生考试计算机学科专业基础综合（408），涵盖数据结构、计算机组成原理、操作系统、计算机网络四大核心科目。',
    '教育学311': '全国硕士研究生招生考试教育学专业基础综合（311），涵盖教育学原理、中外教育史、教育心理学、教育研究方法等核心科目。',
    'CPA': '中国注册会计师（CPA）全国统一考试专业阶段，涵盖会计、审计、财务成本管理、经济法、税法、公司战略与风险管理六科。',
    'CFA': 'CFA（特许金融分析师）考试知识体系，涵盖道德与职业标准、定量方法、经济学、财务报表分析、公司金融、权益投资、固定收益、衍生品、另类投资、投资组合管理。',
    '法考': '国家统一法律职业资格考试，涵盖中国特色社会主义法治理论、法理学、宪法、刑法、刑事诉讼法、民法、民事诉讼法、行政法与行政诉讼法、商经法、国际法等。',
    '教资': '教师资格证考试（中学段）核心知识体系，涵盖教育学、心理学、教育心理学、教育法律法规、教师职业道德、新课程改革等。',
    'SAT': 'SAT (Scholastic Assessment Test) — covers Reading, Writing and Language, Math (with and without calculator), and optional Essay sections aligned with College Board standards.',
    'ACT': 'ACT (American College Testing) — covers English, Mathematics, Reading, Science Reasoning, and optional Writing sections.',
    'MCAT': 'MCAT (Medical College Admission Test) — covers Biological and Biochemical Foundations, Chemical and Physical Foundations, Psychological/Social/Biological Foundations, and Critical Analysis and Reasoning Skills (CARS).',
    'LSAT': 'LSAT (Law School Admission Test) — covers Logical Reasoning, Analytical Reasoning (Logic Games), Reading Comprehension, and Writing Sample sections.',
    'GRE': 'GRE (Graduate Record Examination) General Test — covers Verbal Reasoning, Quantitative Reasoning, and Analytical Writing sections.',
    'GMAT': 'GMAT (Graduate Management Admission Test) — covers Quantitative Reasoning, Verbal Reasoning, Integrated Reasoning, and Analytical Writing Assessment.',
    'USMLE': 'USMLE (United States Medical Licensing Examination) — Step 1 (basic sciences), Step 2 CK (clinical knowledge), Step 3 (clinical management), covering foundational and clinical medical sciences.',
    'IELTS': 'IELTS (International English Language Testing System) — Academic and General Training modules covering Listening, Reading, Writing, and Speaking sections.',
    'TOEFL': 'TOEFL iBT (Test of English as a Foreign Language) — covers Reading, Listening, Speaking, and Writing sections aligned with ETS standards.',
}


class Command(BaseCommand):
    help = '使用 AI 批量生成学科知识树 Markdown 文件'

    def add_arguments(self, parser):
        parser.add_argument('--subject', type=str, required=True, help='学科名称，如 法学、IELTS')
        parser.add_argument('--dry-run', action='store_true', help='仅预览 AI 输出，不写入文件')
        parser.add_argument('--output-dir', type=str, default=None, help='输出目录，默认 backend/knowledge_trees/')

    def handle(self, *args, **kwargs):
        subject = kwargs['subject']
        dry_run = kwargs['dry_run']
        output_dir = kwargs['output_dir']

        if output_dir is None:
            output_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                'knowledge_trees'
            )

        context = SUBJECT_CONTEXTS.get(subject, f'{subject} 的核心知识体系。')
        prompt = PROMPT_TEMPLATE.format(subject=subject, subject_context=context)

        self.stdout.write(f'正在为「{subject}」生成知识树...')

        result = AIService.simple_chat_text(
            system_prompt='你是一位资深教育课程设计师，精通知识体系构建。请严格按照指定格式生成内容，不添加任何额外说明。',
            user_prompt=prompt,
            temperature=0.3,
            max_tokens=16384,
            operation='generate_knowledge_tree',
        )

        if not result:
            self.stdout.write(self.style.ERROR('AI 返回为空，请重试。'))
            return

        if dry_run:
            self.stdout.write('─── 预览（dry-run）───')
            self.stdout.write(result)
            self.stdout.write('─── 结束 ───')
            return

        os.makedirs(output_dir, exist_ok=True)
        filename = f'{subject}.md'
        filepath = os.path.join(output_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(result)

        self.stdout.write(self.style.SUCCESS(f'知识树已保存到: {filepath}'))
