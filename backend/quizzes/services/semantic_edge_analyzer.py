"""
语义边分析服务：对指定学科的 KnowledgePoint 做全量 LLM 语义边分析。

提取自 management/commands/analyze_semantic_edges.py，
供 management command 和 Celery task 共用。
"""
import json
import logging
import time

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
                                min_confidence: float = 0.6) -> dict:
    """
    对指定学科执行全量语义边分析。

    返回: {"created": int, "valid_edges": int, "raw_results": int, "elapsed": float}
    """
    t0 = time.time()

    # ── 1. 加载 KP，按 SEC 分组 ──
    qs = KnowledgePoint.objects.filter(subject=subject, level='kp').select_related('parent')
    if institution_id:
        qs = qs.filter(institution_id=institution_id)
    kps = list(qs.order_by('parent_id', 'order', 'id'))

    if not kps:
        logger.warning("semantic_edge_analyzer: subject=%s has no KPs", subject)
        return {"created": 0, "valid_edges": 0, "raw_results": 0, "elapsed": time.time() - t0}

    sec_groups = {}
    for kp in kps:
        sec_id = kp.parent_id
        sec_name = kp.parent.name if kp.parent else '(无章节)'
        sec_groups.setdefault(sec_id, {'name': sec_name, 'kps': []})
        sec_groups[sec_id]['kps'].append({
            'id': kp.id, 'name': kp.name, 'order': kp.order,
        })

    all_summary_lines = []
    id_to_name = {}
    for sec_id, group in sec_groups.items():
        for kp in group['kps']:
            line = f"[{kp['id']}] {group['name']} › {kp['name']}"
            all_summary_lines.append(line)
            id_to_name[kp['id']] = kp['name']
    all_summary = "\n".join(all_summary_lines)

    sec_ids = list(sec_groups.keys())
    logger.info("semantic_edge_analyzer: subject=%s, %d KPs, %d SECs", subject, len(kps), len(sec_ids))

    # ── 2. 逐 SEC 送 LLM ──
    all_results = []
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
            mapped = 0
            for r in batch_results:
                src_name = r.get('source_name', '')
                tgt_name = r.get('target_name', '')
                src_id = _find_id(src_name, all_summary_lines)
                tgt_id = _find_id(tgt_name, all_summary_lines)
                if src_id and tgt_id:
                    r['source_id'] = src_id
                    r['target_id'] = tgt_id
                    mapped += 1
            logger.info("  [%d/%d] %s: %d raw → %d mapped",
                        idx + 1, len(sec_ids), group['name'][:40], len(batch_results), mapped)
            all_results.extend(batch_results)
        else:
            logger.info("  [%d/%d] %s: no results", idx + 1, len(sec_ids), group['name'][:40])

        if idx < len(sec_ids) - 1:
            time.sleep(0.3)

    # ── 3. 过滤 ──
    valid = [r for r in all_results
             if r.get('relation') != 'none'
             and r.get('confidence', 0) >= min_confidence
             and r.get('source_id') and r.get('target_id')
             and r['source_id'] != r['target_id']]

    # ── 4. 写入 ──
    created = _create_edges(valid, institution_id)
    elapsed = time.time() - t0
    logger.info("semantic_edge_analyzer: %d edges created, %.1fs", created, elapsed)
    return {
        "created": created,
        "valid_edges": len(valid),
        "raw_results": len(all_results),
        "elapsed": round(elapsed, 1),
    }


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


def _find_id(name: str, summary_lines: list[str]) -> int | None:
    """在全局摘要中按名字精确匹配 KP ID。

    summary line 格式: [id] SEC名称 › KP名称
    只匹配 › 之后的 KP 名称部分，避免子串误匹配
    （如 "极限" 误匹配 "极限存在准则" 或 SEC 名 "极限与连续"）。
    """
    if not name:
        return None
    for line in summary_lines:
        sep = ' › '
        sep_idx = line.rfind(sep)
        if sep_idx == -1:
            continue
        if line[sep_idx + len(sep):] != name:
            continue
        start = line.find('[')
        end = line.find(']')
        if start >= 0 and end > start:
            try:
                return int(line[start + 1:end])
            except ValueError:
                pass
    return None


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
        if institution_id:
            kwargs['institution_id'] = institution_id

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
                    defaults=kwargs,
                )
                if is_new:
                    created += 1
            except IntegrityError:
                pass
    return created
