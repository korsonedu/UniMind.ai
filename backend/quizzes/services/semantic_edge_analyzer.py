"""
语义边分析服务：对指定学科的 KnowledgePoint 做全量 LLM 语义边分析。

提取自 management/commands/analyze_semantic_edges.py，
供 management command 和 Celery task 共用。
"""
import json
import logging
import time
from collections import defaultdict

from django.db import transaction

from quizzes.models import KnowledgePoint, KnowledgeEdge

logger = logging.getLogger(__name__)

RELATION_TYPES = ['prerequisite', 'similar', 'contrast', 'confusion', 'co_occur', 'derivation']

# 对称关系：边方向可逆，source↔target 都成立
SYMMETRIC_RELATIONS = {'similar', 'contrast', 'confusion', 'co_occur'}

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


def run_semantic_edge_analysis(*, subject: str, institution_id: int = None,
                                min_confidence: float = 0.6, dry_run: bool = False) -> dict:
    """
    对指定学科执行全量语义边分析。

    dry_run 只返回待审核候选，不写入。
    """
    t0 = time.time()

    # ── 1. 加载 KP，按 SEC 分组 ──
    scoped_points = KnowledgePoint.objects.filter(subject=subject, level='kp', institution_id=institution_id)
    kps = list(scoped_points.select_related('parent').order_by('parent_id', 'order', 'id'))

    if not kps:
        logger.warning("semantic_edge_analyzer: subject=%s has no KPs", subject)
        return {"created": 0, "valid_edges": 0, "raw_results": 0, "elapsed": time.time() - t0}

    sec_groups = {}
    for kp in kps:
        parent = kp.parent if kp.parent and kp.parent.institution_id == institution_id else None
        sec_id = parent.pk if parent else None
        sec_name = parent.name if parent else '(无章节)'
        sec_groups.setdefault(sec_id, {'name': sec_name, 'kps': []})
        sec_groups[sec_id]['kps'].append({
            'id': kp.id, 'name': kp.name, 'order': kp.order,
        })

    all_summary_lines = []
    ids_by_name = defaultdict(list)
    for sec_id, group in sec_groups.items():
        for kp in group['kps']:
            line = f"[{kp['id']}] {group['name']} › {kp['name']}"
            all_summary_lines.append(line)
            ids_by_name[kp['name']].append(kp['id'])
    all_summary = "\n".join(all_summary_lines)

    sec_ids = list(sec_groups.keys())
    logger.info("semantic_edge_analyzer: subject=%s, %d KPs, %d SECs", subject, len(kps), len(sec_ids))

    # ── 2. 逐 SEC 送 LLM ──
    all_results = []
    raw_results = 0
    for idx, sec_id in enumerate(sec_ids):
        group = sec_groups[sec_id]
        sec_kps = group['kps']

        kp_list = "\n".join(
            f"{i+1}. {kp['name']}" for i, kp in enumerate(sec_kps)
        )

        user_msg = (
            f"## 当前 SEC: {group['name']}\n\n"
            f"知识点列表：\n{kp_list}\n\n"
            f"## 其他所有知识点（全局摘要）\n{all_summary}"
        )

        batch_results = _call_llm(SYSTEM_PROMPT, user_msg)

        if batch_results:
            raw_results += len(batch_results)
            section_points = {kp['id'] for kp in sec_kps}
            mapped = 0
            for r in batch_results:
                sources = [pk for pk in ids_by_name.get(r.get('source_name'), ()) if pk in section_points]
                targets = ids_by_name.get(r.get('target_name'), ())
                if len(sources) == len(targets) == 1:
                    all_results.append({**r, 'source_id': sources[0], 'target_id': targets[0]})
                    mapped += 1
            logger.info("  [%d/%d] %s: %d raw → %d mapped",
                        idx + 1, len(sec_ids), group['name'][:40], len(batch_results), mapped)
        else:
            logger.info("  [%d/%d] %s: no results", idx + 1, len(sec_ids), group['name'][:40])

        if idx < len(sec_ids) - 1:
            time.sleep(0.3)

    # ── 3. 过滤 ──
    valid = [r for r in all_results
             if r.get('relation') != 'none'
             and r.get('confidence', 0) >= min_confidence
             and r['source_id'] != r['target_id']]

    # ── 4. 写入 ──
    with transaction.atomic():
        point_ids = {row[key] for row in valid for key in ('source_id', 'target_id')}
        points = scoped_points.filter(pk__in=point_ids).order_by('pk')
        if not dry_run:
            points = points.select_for_update()
        visible = set(points.values_list('pk', flat=True))
        valid = [row for row in valid if row['source_id'] in visible and row['target_id'] in visible]
        created = 0 if dry_run else _create_edges(valid, institution_id)
    elapsed = time.time() - t0
    logger.info("semantic_edge_analyzer: %d edges created, %.1fs", created, elapsed)
    result = {
        "created": created,
        "valid_edges": len(valid),
        "raw_results": raw_results,
        "elapsed": round(elapsed, 1),
    }
    if dry_run:
        result['preview'] = valid
    return result


def _call_llm(system_msg: str, user_msg: str) -> list:
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
        logger.warning("semantic_edge_analyzer: structured_output returned empty")
        return []
    return result


def _create_edges(results: list[dict], institution_id: int = None) -> int:
    """去重并写入 KnowledgeEdge（source_type='llm', is_active=False）。

    对称关系（similar/contrast/confusion/co_occur）双向写入；
    有向关系（prerequisite/derivation）仅保留原始方向。
    """
    from django.db import IntegrityError

    best = {}
    for r in results:
        if r.get('relation') == 'none':
            continue
        pair_key = (r['source_id'], r['target_id'])
        if pair_key not in best or r.get('confidence', 0) > best[pair_key].get('confidence', 0):
            best[pair_key] = r

    created = 0
    for r in best.values():
        weight = min(1.0, r.get('confidence', 0.7))
        kwargs = {
            'weight': weight,
            'source_type': 'llm',
            'is_active': False,
        }
        is_symmetric = r['relation'] in SYMMETRIC_RELATIONS
        directions = (
            [(r['source_id'], r['target_id']), (r['target_id'], r['source_id'])]
            if is_symmetric
            else [(r['source_id'], r['target_id'])]
        )
        for src, tgt in directions:
            try:
                _, is_new = KnowledgeEdge.objects.get_or_create(
                    source_id=src,
                    target_id=tgt,
                    edge_type=r['relation'],
                    institution_id=institution_id,
                    defaults=kwargs,
                )
                if is_new:
                    created += 1
            except IntegrityError:
                pass
    return created
