"""
对指定学科的 KnowledgePoint 做全量语义边分析。

用法:
  python manage.py analyze_semantic_edges --subject CFA
  python manage.py analyze_semantic_edges --subject CFA --batch-size 15 --dry-run

流程:
  1. Embedding 阶段：批量获取所有 KP 的向量表示
  2. 召回阶段：每个 KP 找其他 SEC 下 top-N 最相似的 KP
  3. LLM 判定阶段：分批送 LLM，判断每对 KP 的关系类型
  4. 写入阶段：创建 KnowledgeEdge (source_type='llm', is_active=False)
"""

import json
import math
import time
from collections import defaultdict

from django.core.management.base import BaseCommand
from quizzes.models import KnowledgePoint, KnowledgeEdge

# 关系类型定义 + LLM 判定 prompt
RELATION_TYPES = ['prerequisite', 'similar', 'contrast', 'confusion', 'co_occur', 'derivation']

JUDGE_PROMPT = """你是一个教育领域的知识图谱专家。下面列出若干对知识点，请判断每对之间的关系。

关系类型定义：
- prerequisite: 必须先学 A 才能学 B（A 是 B 的前置知识）
- similar: A 和 B 是相近的概念，同一学科内的关联
- contrast: A 和 B 是对立/互补的概念，对比学习能加深理解
- confusion: A 和 B 容易被学生搞混
- co_occur: A 和 B 在考试中经常一起出现
- derivation: B 是从 A 推导出来的
- none: 没有明显关系

请对每对知识点返回 JSON 数组，每项格式：
{"a": "KP名字A", "b": "KP名字B", "relation": "关系类型", "confidence": 0.0-1.0}

只返回 JSON 数组，不要其他文字。"""


class Command(BaseCommand):
    help = 'LLM 语义分析：为学科 KP 生成跨 SEC 的知识边'

    def add_arguments(self, parser):
        parser.add_argument('--subject', type=str, required=True)
        parser.add_argument('--batch-size', type=int, default=15,
                           help='每批送 LLM 的候选对数')
        parser.add_argument('--top-k', type=int, default=5,
                           help='每个 KP 召回的最相似 KP 数')
        parser.add_argument('--min-confidence', type=float, default=0.6,
                           help='最小置信度阈值')
        parser.add_argument('--dry-run', action='store_true',
                           help='只统计不写入')

    def handle(self, *args, **options):
        subject = options['subject']
        batch_size = options['batch_size']
        top_k = options['top_k']
        min_conf = options['min_confidence']
        dry_run = options['dry_run']

        t0 = time.time()

        # ═══ 1. 加载 KP ═══
        kps = list(KnowledgePoint.objects.filter(
            subject=subject, level='kp'
        ).select_related('parent').order_by('id'))

        if not kps:
            self.stderr.write(f"学科 {subject} 没有 KP")
            return

        kp_texts = []
        kp_meta = []  # [(id, name, sec_id, sec_name)]
        for kp in kps:
            # 构建描述文本：SEC名 + KP名
            sec_name = kp.parent.name if kp.parent else ''
            text = f"{sec_name} — {kp.name}"
            kp_texts.append(text)
            kp_meta.append({
                'id': kp.id,
                'name': kp.name,
                'sec_id': kp.parent_id,
                'sec_name': sec_name,
            })

        self.stdout.write(f"📚 {subject}: {len(kps)} KPs, "
                          f"{len(set(k['sec_id'] for k in kp_meta))} SECs")

        # ═══ 2. Embedding ═══
        self.stdout.write("🧮 获取 embeddings...")
        embeddings = self._batch_embed(kp_texts)

        # ═══ 3. 召回：每个 KP 找其他 SEC 下 top-K ═══
        self.stdout.write(f"🔍 召回 top-{top_k} 跨 SEC 候选...")
        candidates = self._recall_candidates(kp_meta, embeddings, top_k)
        self.stdout.write(f"   候选对: {len(candidates)}")

        if not candidates:
            self.stdout.write("   无跨 SEC 候选对，跳过")
            return

        # ═══ 4. LLM 判定 ═══
        self.stdout.write(f"🤖 LLM 判定 (batch={batch_size})...")
        all_results = []
        total_batches = math.ceil(len(candidates) / batch_size)

        for batch_idx in range(total_batches):
            start = batch_idx * batch_size
            end = min(start + batch_size, len(candidates))
            batch = candidates[start:end]

            # 构建 prompt
            pair_lines = []
            for i, (a, b, sim) in enumerate(batch):
                pair_lines.append(
                    f"{i+1}. A: {a['sec_name']} › {a['name']}\n"
                    f"   B: {b['sec_name']} › {b['name']}"
                )
            pairs_text = "\n".join(pair_lines)

            result = self._judge_batch(pairs_text, batch, batch_idx, total_batches)

            if result:
                all_results.extend(result)

            # 速率控制
            if batch_idx < total_batches - 1:
                time.sleep(0.5)

        # 过滤低置信度
        valid = [r for r in all_results
                 if r['relation'] != 'none' and r['confidence'] >= min_conf]
        self.stdout.write(f"   有效边: {len(valid)} / {len(all_results)} 条判定")

        # ═══ 5. 写入 ═══
        if dry_run:
            self.stdout.write("\n[Dry-run] 预览前 20 条:")
            for r in valid[:20]:
                self.stdout.write(
                    f"  {r['source_name'][:30]:30} → {r['target_name'][:30]:30} "
                    f"{r['relation']:14} conf={r['confidence']:.2f}"
                )
            self.stdout.write(f"\n总计 {len(valid)} 条边（未写入）")
        else:
            created = self._create_edges(valid, subject)
            self.stdout.write(f"✅ 创建 {created} 条边（source_type=llm, 待审核）")

        elapsed = time.time() - t0
        self.stdout.write(f"\n⏱ 总耗时: {elapsed:.1f}s")

    # ── helpers ──

    def _batch_embed(self, texts):
        """批量获取 embeddings，每批最多 50 个"""
        from ai_engine.tool_router import _call_embedding_api

        all_embeddings = []
        embed_batch_size = 50
        for i in range(0, len(texts), embed_batch_size):
            batch = texts[i:i + embed_batch_size]
            embs = _call_embedding_api(batch)
            all_embeddings.extend(embs)
            if i + embed_batch_size < len(texts):
                time.sleep(0.2)
        return all_embeddings

    def _recall_candidates(self, kp_meta, embeddings, top_k):
        """对每个 KP，找其他 SEC 下余弦相似度最高的 top-K 个 KP"""
        n = len(kp_meta)

        # 按 SEC 分组
        sec_to_kps = defaultdict(list)
        for idx, meta in enumerate(kp_meta):
            sec_to_kps[meta['sec_id']].append(idx)

        candidates = []
        for i in range(n):
            a_meta = kp_meta[i]
            a_emb = embeddings[i]
            a_sec = a_meta['sec_id']

            # 只考虑其他 SEC
            scores = []
            for sec_id, kp_indices in sec_to_kps.items():
                if sec_id == a_sec:
                    continue
                for j in kp_indices:
                    sim = self._cosine_sim(a_emb, embeddings[j])
                    scores.append((j, sim))

            scores.sort(key=lambda x: -x[1])
            for j, sim in scores[:top_k]:
                if sim > 0.5:  # 最低相似度阈值
                    candidates.append((kp_meta[i], kp_meta[j], sim))

        # 去重（A→B 和 B→A 算同一条）
        seen = set()
        deduped = []
        for a, b, sim in candidates:
            key = tuple(sorted([a['id'], b['id']]))
            if key not in seen:
                seen.add(key)
                deduped.append((a, b, sim))

        return deduped

    def _judge_batch(self, pairs_text, batch, batch_idx, total_batches):
        """送一批候选对给 LLM 判定关系"""
        from ai_engine.service import AIService

        messages = [
            {"role": "system", "content": JUDGE_PROMPT},
            {"role": "user", "content": pairs_text},
        ]

        self.stdout.write(f"   batch {batch_idx+1}/{total_batches} "
                          f"({len(batch)} pairs)...", ending='')

        try:
            response = AIService.call_ai(
                messages, temperature=0.2, max_tokens=2048,
                operation='quizzes.semantic_edges',
            )
        except Exception as e:
            self.stdout.write(f" ❌ {e}")
            return []

        if not response:
            self.stdout.write(" ⚠️ 无响应")
            return []

        # 解析 JSON
        content = response.strip()
        # 清理可能的 markdown 包裹
        if content.startswith('```'):
            content = content.split('\n', 1)[-1]
            if content.endswith('```'):
                content = content[:-3]

        try:
            results = json.loads(content)
        except json.JSONDecodeError:
            self.stdout.write(f" ⚠️ JSON 解析失败: {content[:100]}")
            return []

        if not isinstance(results, list):
            self.stdout.write(f" ⚠️ 非数组响应")
            return []

        # 映射回 KP ID
        mapped = []
        for r in results:
            a_name = r.get('a', '')
            b_name = r.get('b', '')
            relation = r.get('relation', 'none')
            confidence = float(r.get('confidence', 0))

            # 在 batch 中查找匹配
            source_meta = None
            target_meta = None
            for a, b, _ in batch:
                if a['name'] in a_name and b['name'] in b_name:
                    source_meta, target_meta = a, b
                    break
                if b['name'] in a_name and a['name'] in b_name:
                    source_meta, target_meta = b, a
                    break

            if source_meta and target_meta and relation in RELATION_TYPES + ['none']:
                mapped.append({
                    'source_id': source_meta['id'],
                    'source_name': source_meta['name'],
                    'target_id': target_meta['id'],
                    'target_name': target_meta['name'],
                    'relation': relation,
                    'confidence': confidence,
                })

        self.stdout.write(f" ✓ {len(mapped)} 条")
        return mapped

    def _create_edges(self, results, subject):
        """创建 KnowledgeEdge 记录"""
        created = 0
        for r in results:
            if r['relation'] == 'none':
                continue
            # 双向创建（知识图的边是有向的，但语义关系通常双向）
            for src, tgt in [(r['source_id'], r['target_id']),
                              (r['target_id'], r['source_id'])]:
                weight = min(1.0, r['confidence'])
                _, is_new = KnowledgeEdge.objects.get_or_create(
                    source_id=src,
                    target_id=tgt,
                    edge_type=r['relation'],
                    defaults={
                        'weight': weight,
                        'source_type': 'llm',
                        'is_active': False,  # 待审核
                    },
                )
                if is_new:
                    created += 1
        return created

    @staticmethod
    def _cosine_sim(a, b):
        """余弦相似度"""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
