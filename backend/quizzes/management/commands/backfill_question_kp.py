"""
回填题目知识点关联：对 knowledge_point_id 为 NULL 的题目，用 LLM 分类匹配到最匹配的 KP。

用法:
  python manage.py backfill_question_kp
  python manage.py backfill_question_kp --dry-run
"""
import json
import time

from django.core.management.base import BaseCommand
from quizzes.models import Question, KnowledgePoint


SYSTEM_PROMPT = """你是教育领域的内容分类专家。给定一道题目和一个知识点列表，找出该题目最匹配的知识点。

返回 JSON 对象：{"kp_id": 数字ID, "confidence": 0.0-1.0}
如果题目无法匹配任何知识点，返回 {"kp_id": null, "confidence": 0}
只返回 JSON 对象，不要其他文字。"""


class Command(BaseCommand):
    help = '回填题目→知识点关联'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        questions = list(Question.objects.filter(knowledge_point__isnull=True))
        if not questions:
            self.stdout.write("所有题目已关联知识点")
            return

        self.stdout.write(f"待处理: {len(questions)} 题")

        # 加载所有 KP，按 subject 分组
        all_kps = list(KnowledgePoint.objects.filter(level='kp').order_by('subject', 'id'))
        kps_by_subject = {}
        kp_id_map = {}
        for kp in all_kps:
            kps_by_subject.setdefault(kp.subject or '', []).append(kp)
            kp_id_map[kp.id] = kp

        assigned = 0
        failed = 0

        for idx, q in enumerate(questions):
            # 从题目文本推断学科
            q_text = q.text or ''
            subject = self._guess_subject(q_text, list(kps_by_subject.keys()))

            kps = kps_by_subject.get(subject, [])
            if not kps:
                # fallback: 用全部 KP
                kps = all_kps[:200]

            kp_list = '\n'.join(
                f"[{kp.id}] {kp.name}" for kp in kps[:200]
            )

            user_msg = (
                f"题目：{q_text[:500]}\n\n"
                f"可选知识点：\n{kp_list}"
            )

            result = self._call_llm(SYSTEM_PROMPT, user_msg)
            kp_id = result.get('kp_id') if result else None
            confidence = result.get('confidence', 0) if result else 0

            if kp_id and confidence >= 0.5 and kp_id in kp_id_map:
                if not dry_run:
                    q.knowledge_point_id = kp_id
                    q.save(update_fields=['knowledge_point'])
                assigned += 1
                self.stdout.write(
                    f"  [{idx+1}/{len(questions)}] Q{q.id} → "
                    f"[{kp_id_map[kp_id].name[:30]}] (conf={confidence:.2f})"
                )
            else:
                failed += 1
                self.stdout.write(
                    f"  [{idx+1}/{len(questions)}] Q{q.id} → 未匹配"
                )

            if idx < len(questions) - 1:
                time.sleep(0.2)

        self.stdout.write(
            self.style.SUCCESS(
                f"\n完成: {assigned} 已分配, {failed} 未匹配"
                f"{' [DRY-RUN]' if dry_run else ''}"
            )
        )

    def _guess_subject(self, text: str, subjects: list) -> str:
        """从题目文本猜测学科"""
        keywords = {
            '金融431': ['货币', '利率', '银行', '金融', '投资', '汇率', '通胀', 'GDP', '凯恩斯',
                        'IS-LM', '货币政策', '财政政策', '资本', '债券', '股票', '期权'],
            '高中数学': ['sin', 'cos', 'tan', '函数', '方程', '导数', '积分', '向量',
                         '概率', '三角', '数列', '几何', '椭圆', '抛物线'],
            '高中物理': ['力', '速度', '加速度', '电场', '磁场', '能量', '动量', '牛顿',
                         '电路', '光学', '热', '波', '量子'],
            'CPA': ['会计', '审计', '税法', '报表', '资产', '负债', '利润', '成本'],
            '法考': ['刑法', '民法', '合同', '侵权', '诉讼', '判决', '法律', '法院',
                     '犯罪', '证据', '权利', '义务'],
            'CFA': ['portfolio', 'equity', 'bond', 'derivative', 'risk', 'return',
                    'CAPM', 'WACC', 'DCF', 'financial', 'valuation'],
            '计算机408': ['算法', '数据结构', '操作系统', '进程', '内存', 'CPU', '网络',
                          'TCP', 'HTTP', '数据库', 'SQL', '编译'],
            '教资': ['教学', '学生', '课堂', '教育', '课程', '教师'],
            '教育学311': ['教育', '教学', '课程', '学习', '理论'],
            '法学': ['法律', '权利', '义务', '法官', '判决'],
            'USMLE': ['patient', 'diagnosis', 'treatment', 'symptom', 'disease',
                      'drug', 'surgery', 'medical'],
        }
        for subject, keywords_list in keywords.items():
            if any(kw.lower() in text.lower() for kw in keywords_list):
                if subject in subjects:
                    return subject
        return ''

    def _call_llm(self, system_msg, user_msg):
        import os
        import httpx
        from django.conf import settings as django_settings

        api_key = os.getenv('LLM_API_KEY', '')
        base_url = os.getenv('LLM_BASE_URL', 'https://api.deepseek.com/v1/chat/completions')
        model = getattr(django_settings, 'LLM_MODEL', 'deepseek-v4-flash') or 'deepseek-v4-flash'

        try:
            resp = httpx.post(
                base_url,
                json={
                    'model': model,
                    'messages': [
                        {'role': 'system', 'content': system_msg},
                        {'role': 'user', 'content': user_msg},
                    ],
                    'temperature': 0.1,
                    'max_tokens': 256,
                },
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data['choices'][0]['message']['content'].strip()
        except Exception as e:
            self.stderr.write(f" ❌ LLM: {e}")
            return {}

        return self._parse_json(content)

    def _parse_json(self, content):
        content = content.strip()
        if content.startswith('```'):
            lines = content.split('\n')
            content = '\n'.join(lines[1:])
            if content.endswith('```'):
                content = content[:-3]
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {}
