"""
对指定学科的 KnowledgePoint 做全量语义边分析（SEC 批量模式）。

用法:
  python manage.py analyze_semantic_edges --subject CFA
  python manage.py analyze_semantic_edges --subject CFA --dry-run

流程:
  1. 加载所有 KP，按 SEC 分组
  2. 每个 SEC 一批，送 LLM：给定本 SEC 的所有 KP + 其他所有 KP 的摘要列表
     让 LLM 找出与本 SEC 中每个 KP 相关的其他 KP，并判断关系类型
  3. 创建 KnowledgeEdge (source_type='llm', is_active=False)
"""

import json
import math
import time

from django.core.management.base import BaseCommand
from quizzes.models import KnowledgePoint, KnowledgeEdge

RELATION_TYPES = ['prerequisite', 'similar', 'contrast', 'confusion', 'co_occur', 'derivation']

SYSTEM_PROMPT = """你是教育领域的知识图谱专家。
给定一个 SEC（章节）下的若干个知识点，以及一个"其他所有知识点"的摘要列表，
请找出与每个给定知识点有语义关系的其他知识点。

关系类型：
- prerequisite: 必须先学 A 才能学 B（A 是 B 的前置知识）
- similar: 概念相近，同一学科内关联
- contrast: 对立/互补概念，对比学习能加深理解
- confusion: 容易被学生搞混
- co_occur: 考试中经常一起出现
- derivation: B 从 A 推导而来

调用 submit_edges 工具提交结果。每项格式：
{"source_name": "给定KP名", "target_name": "相关KP名", "relation": "关系类型", "confidence": 0.0-1.0}

source_name 和 target_name 必须与给定列表中的名称**逐字一致**。
没有关系的 KP 不提交。confidence < 0.6 的关系也不提交。"""


class Command(BaseCommand):
    help = 'LLM 语义分析：SEC 批量模式生成知识边'

    def add_arguments(self, parser):
        parser.add_argument('--subject', type=str, required=True)
        parser.add_argument('--min-confidence', type=float, default=0.6)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        subject = options['subject']
        min_conf = options['min_confidence']
        dry_run = options['dry_run']

        t0 = time.time()

        # ═══ 1. 加载 ═══
        kps = list(KnowledgePoint.objects.filter(
            subject=subject, level='kp'
        ).select_related('parent').order_by('parent_id', 'order', 'id'))

        if not kps:
            self.stderr.write(f"学科 {subject} 没有 KP")
            return

        # 按 SEC 分组
        sec_groups = {}
        for kp in kps:
            sec_id = kp.parent_id
            sec_name = kp.parent.name if kp.parent else '(无章节)'
            sec_groups.setdefault(sec_id, {'name': sec_name, 'kps': []})
            sec_groups[sec_id]['kps'].append({
                'id': kp.id, 'name': kp.name, 'order': kp.order,
            })

        # 构建全局摘要（每个 KP 一行，用于 LLM 快速浏览）
        all_summary_lines = []
        id_to_name = {}
        for sec_id, group in sec_groups.items():
            for kp in group['kps']:
                line = f"[{kp['id']}] {group['name']} › {kp['name']}"
                all_summary_lines.append(line)
                id_to_name[kp['id']] = kp['name']
        all_summary = "\n".join(all_summary_lines)

        sec_ids = list(sec_groups.keys())
        self.stdout.write(f"📚 {subject}: {len(kps)} KPs, {len(sec_ids)} SECs")

        # ═══ 2. 逐 SEC 送 LLM ═══
        all_results = []
        for idx, sec_id in enumerate(sec_ids):
            group = sec_groups[sec_id]
            sec_kps = group['kps']

            # 只分析有 2+ KP 的 SEC（单个 KP 的 SEC 也可以，但边际收益低）
            kp_list = "\n".join(
                f"{i+1}. {kp['name']}" for i, kp in enumerate(sec_kps)
            )

            user_msg = (
                f"## 当前 SEC: {group['name']}\n\n"
                f"知识点列表：\n{kp_list}\n\n"
                f"## 其他所有知识点（全局摘要）\n{all_summary}"
            )

            self.stdout.write(
                f"  [{idx+1}/{len(sec_ids)}] {group['name'][:40]} "
                f"({len(sec_kps)} KPs)...", ending=''
            )

            batch_results = self._call_llm(SYSTEM_PROMPT, user_msg)

            if batch_results:
                # 映射名字回 ID
                mapped = 0
                for r in batch_results:
                    src_name = r.get('source_name', '')
                    tgt_name = r.get('target_name', '')
                    # 在全局摘要中找 ID
                    src_id = self._find_id(src_name, all_summary_lines)
                    tgt_id = self._find_id(tgt_name, all_summary_lines)
                    if src_id and tgt_id:
                        r['source_id'] = src_id
                        r['target_id'] = tgt_id
                        mapped += 1
                self.stdout.write(f" ✓ {len(batch_results)} raw → {mapped} mapped")
                all_results.extend(batch_results)
            else:
                self.stdout.write(" ⚠️ 无结果")

            if idx < len(sec_ids) - 1:
                time.sleep(0.3)

        # ═══ 3. 过滤 ═══
        valid = [r for r in all_results
                 if r.get('relation') != 'none'
                 and r.get('confidence', 0) >= min_conf
                 and r.get('source_id') and r.get('target_id')
                 and r['source_id'] != r['target_id']]
        self.stdout.write(f"\n有效边: {len(valid)} / {len(all_results)} 条判定")

        # ═══ 4. 写入 ═══
        if dry_run:
            self.stdout.write("\n[Dry-run] 预览:")
            # 按类型分组统计
            from collections import Counter
            type_dist = Counter(r['relation'] for r in valid)
            for rel, cnt in type_dist.most_common():
                self.stdout.write(f"  {rel:14}: {cnt}")
            self.stdout.write(f"\n预览前 20 条:")
            for r in valid[:20]:
                self.stdout.write(
                    f"  {r.get('source_name', '?')[:30]:30} → "
                    f"{r.get('target_name', '?')[:30]:30} "
                    f"{r['relation']:14} conf={r['confidence']:.2f}"
                )
            self.stdout.write(f"\n总计 {len(valid)} 条边（未写入）")
        else:
            created = self._create_edges(valid)
            self.stdout.write(f"✅ 创建 {created} 条边（source_type=llm, 待审核）")

        elapsed = time.time() - t0
        self.stdout.write(f"⏱ 总耗时: {elapsed:.1f}s")

    def _call_llm(self, system_msg, user_msg):
        """调用 LLM，使用 structured_output 保证 JSON 合法性"""
        from ai_engine.service import AIEngine

        schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_name": {
                        "type": "string",
                        "description": "当前 SEC 中的知识点名称，与给定的列表精确一致",
                    },
                    "target_name": {
                        "type": "string",
                        "description": "全局摘要中相关知识点的名称，与摘要中的名称精确一致",
                    },
                    "relation": {
                        "type": "string",
                        "enum": RELATION_TYPES,
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                    },
                },
                "required": ["source_name", "target_name", "relation", "confidence"],
            },
        }

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

        result = AIEngine.structured_output(
            messages=messages,
            schema=schema,
            tool_name="submit_edges",
            tool_description="提交语义边列表",
            temperature=0.2,
            max_tokens=8192,
            operation='knowledge_edge_analyze',
        )
        if not result:
            self.stderr.write(" ⚠️ structured_output 返回空")
            return []
        return result

    def _find_id(self, name, summary_lines):
        """在全局摘要中按名字找 KP ID"""
        for line in summary_lines:
            if name and name in line:
                # 解析 [id] 格式
                start = line.find('[')
                end = line.find(']')
                if start >= 0 and end > start:
                    try:
                        return int(line[start+1:end])
                    except ValueError:
                        pass
        return None

    def _parse_json_response(self, content):
        """鲁棒 JSON 解析：处理 markdown 包裹、截断等"""
        # 去掉 markdown 包裹
        if content.startswith('```'):
            lines = content.split('\n')
            content = '\n'.join(lines[1:])
            if content.endswith('```'):
                content = content[:-3]

        # 尝试完整解析
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # 截断修复：找到最后一个完整的对象 }，补上数组结尾 ]
        content = content.strip()
        if content.startswith('['):
            # 找到最后一个 } 后面没有逗号或紧跟换行/空格的位置
            last_brace = content.rfind('}')
            if last_brace > 0:
                truncated = content[:last_brace + 1] + '\n]'
                try:
                    return json.loads(truncated)
                except json.JSONDecodeError:
                    # 再试：找到最后一个 }, 加上 ]
                    last_comma_obj = content.rfind('},')
                    if last_comma_obj > 0:
                        truncated = content[:last_comma_obj + 1] + '\n]'
                        try:
                            return json.loads(truncated)
                        except json.JSONDecodeError:
                            pass

        self.stderr.write(f" ⚠️ JSON parse failed, raw: {content[:150]}")
        return []

    def _create_edges(self, results):
        # 去重：同一对 KP 可能被 LLM 返回多个关系，只保留最高置信度的
        best = {}  # (src, tgt, relation) → max confidence entry
        for r in results:
            if r.get('relation') == 'none':
                continue
            # 每个 (src, tgt) 只保留最高置信度的一条
            pair_key = (r['source_id'], r['target_id'])
            if pair_key not in best or r.get('confidence', 0) > best[pair_key].get('confidence', 0):
                best[pair_key] = r

        created = 0
        for r in best.values():
            weight = min(1.0, r.get('confidence', 0.7))
            for src, tgt in [(r['source_id'], r['target_id']),
                              (r['target_id'], r['source_id'])]:
                try:
                    _, is_new = KnowledgeEdge.objects.get_or_create(
                        source_id=src,
                        target_id=tgt,
                        edge_type=r['relation'],
                        defaults={
                            'weight': weight,
                            'source_type': 'llm',
                            'is_active': False,
                        },
                    )
                    if is_new:
                        created += 1
                except Exception:
                    # 并发或重复导致的 IntegrityError，跳过
                    pass
        return created
