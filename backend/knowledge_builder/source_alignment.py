"""Tree-to-Tree semantic alignment engine (PageIndex-inspired)."""
import logging
import re
from concurrent.futures import ThreadPoolExecutor

from django.db import transaction

from ai_engine import config
from . import prompts
from .models import BlockStepAtom, KnowledgeTreeBuild, SourceAlignment, TreeSourceDocument
from .source_parsers import clean_resource_excerpt, flatten_toc_nodes

logger = logging.getLogger(__name__)

ALIGN_BATCH_SIZE = 28
DEFAULT_CONFIDENCE_THRESHOLD = 0.55
MAX_ALIGNMENTS_PER_ATOM = 2


def _default_role_for_source(source_kind: str) -> str:
    if source_kind in (TreeSourceDocument.SourceKind.BILIBILI_SERIES, TreeSourceDocument.SourceKind.COURSE_ALBUM):
        return SourceAlignment.AlignmentRole.VIDEO_LECTURE
    return SourceAlignment.AlignmentRole.PRIMARY_TEXTBOOK


def _tokenize(text: str) -> set[str]:
    low = (text or '').casefold()
    tokens = set(re.findall(r'[a-z0-9_]{2,}', low))
    for seg in re.findall(r'[\u4e00-\u9fff]{2,}', low):
        tokens.add(seg)
        for i in range(len(seg) - 1):
            tokens.add(seg[i:i + 2])
    return tokens


def _heuristic_align_batch(
    atoms_payload: list[dict],
    source_nodes: list[dict],
    raw_sections: dict[str, str],
    default_role: str,
) -> list[dict]:
    """Deterministic lexical fallback when DeepSeek key is absent or a batch call fails."""
    node_tokens = {}
    for node in source_nodes:
        nid = node['node_id']
        haystack = f"{node.get('title', '')} {node.get('locator', '')} {node.get('summary', '')} {raw_sections.get(nid, '')[:400]}"
        node_tokens[nid] = (_tokenize(haystack), haystack.casefold())

    results = []
    for atom in atoms_payload:
        name = (atom['name'] or '').strip()
        name_low = name.casefold()
        query_text = f"{name} {' '.join(atom.get('key_elements') or [])} {atom.get('goal_statement', '')}"
        q_tokens = _tokenize(query_text)
        if not q_tokens:
            continue
        scored = []
        for node in source_nodes:
            nid = node['node_id']
            ntok, hay_low = node_tokens[nid]
            overlap = len(q_tokens & ntok)
            if not overlap:
                continue
            ratio = overlap / max(min(len(q_tokens), 8), 2)
            exact_bonus = 0.35 if (len(name_low) >= 2 and name_low in hay_low) else 0.0
            conf = round(min(0.95, 0.35 + ratio * 0.55 + exact_bonus), 2)
            if conf >= DEFAULT_CONFIDENCE_THRESHOLD:
                scored.append((conf, node))
        scored.sort(key=lambda pair: (-pair[0], pair[1]['node_id']))
        for conf, node in scored[:MAX_ALIGNMENTS_PER_ATOM]:
            reason = f"对应章节《{node['title'][:18]}》覆盖该知识点核心内容"[:30]
            results.append({
                'atom_code': atom['code'],
                'source_node_id': node['node_id'],
                'alignment_role': default_role,
                'match_reason': reason,
                'confidence': conf,
            })
    return results


def _align_batch_via_llm(build: KnowledgeTreeBuild, source_doc: TreeSourceDocument, source_nodes: list[dict], batch: list[dict]) -> list[dict]:
    context = {
        'subject': build.subject,
        'source_title': source_doc.title,
        'source_kind': source_doc.source_kind,
        'source_nodes': [
            {
                'node_id': n['node_id'],
                'title': n['title'],
                'locator': n['locator'],
                'summary': n['summary'][:120],
            }
            for n in source_nodes[:120]
        ],
        'atoms': batch,
    }
    response = prompts.ask('source_tree_align', context, operation='knowledge_builder_source_align')
    return response.get('alignments') or []


def build_source_coverage_summary(build: KnowledgeTreeBuild, source_doc: TreeSourceDocument | None = None) -> dict:
    """Compute block and atom coverage statistics for a build or a specific source document."""
    total_blocks = build.blocks.count()
    total_atoms = build.atoms.count()
    qs = SourceAlignment.objects.filter(source_document__build=build)
    if source_doc is not None:
        qs = qs.filter(source_document=source_doc)
    aligned_block_ids = set(qs.values_list('block_id', flat=True))
    aligned_atom_ids = set(qs.exclude(atom_id__isnull=True).values_list('atom_id', flat=True))
    return {
        'total_block_count': total_blocks,
        'aligned_block_count': len(aligned_block_ids),
        'total_atom_count': total_atoms,
        'aligned_atom_count': len(aligned_atom_ids),
        'alignment_count': qs.count(),
    }


def align_source_document(
    source_doc: TreeSourceDocument,
    *,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> dict:
    """Align a TreeSourceDocument's TOC tree against all atoms in its KnowledgeTreeBuild."""
    build = source_doc.build
    source_nodes = flatten_toc_nodes(source_doc.toc_tree)
    raw_sections = source_doc.raw_sections if isinstance(source_doc.raw_sections, dict) else {}
    node_by_id = {n['node_id']: n for n in source_nodes}
    default_role = _default_role_for_source(source_doc.source_kind)

    assignments = list(
        BlockStepAtom.objects.filter(step__block__build=build)
        .select_related('atom', 'step__block')
        .order_by('step__block__order', 'step__step_index', 'position', 'pk')
    )
    atom_meta_by_code = {}
    atom_payloads = []
    for row in assignments:
        atom = row.atom
        if atom.code in atom_meta_by_code:
            continue
        atom_meta_by_code[atom.code] = (row.step.block, atom)
        atom_payloads.append({
            'code': atom.code,
            'block_title': row.step.block.short_title,
            'name': atom.name,
            'goal_statement': atom.goal_statement[:180],
            'key_elements': list(atom.key_elements or [])[:6],
        })

    if not source_nodes or not atom_payloads:
        return {
            'source_id': source_doc.pk,
            'used_ai': False,
            'created_count': 0,
            'coverage': build_source_coverage_summary(build, source_doc),
            'alignments': [],
        }

    batches = [atom_payloads[i:i + ALIGN_BATCH_SIZE] for i in range(0, len(atom_payloads), ALIGN_BATCH_SIZE)]
    used_ai = bool(config._get_api_key())
    raw_items: list[dict] = []

    if used_ai:
        def _run_batch(batch):
            try:
                return _align_batch_via_llm(build, source_doc, source_nodes, batch)
            except Exception as exc:
                logger.warning('Tree-to-Tree LLM align batch failed, using lexical fallback: %s', exc)
                return _heuristic_align_batch(batch, source_nodes, raw_sections, default_role)

        if len(batches) == 1:
            raw_items.extend(_run_batch(batches[0]))
        else:
            with ThreadPoolExecutor(max_workers=min(4, len(batches))) as pool:
                for batch_result in pool.map(_run_batch, batches):
                    raw_items.extend(batch_result)
    else:
        for batch in batches:
            raw_items.extend(_heuristic_align_batch(batch, source_nodes, raw_sections, default_role))

    # Validate node_ids against real source nodes, enforce per-atom cap and confidence threshold.
    per_atom_best: dict[str, list[dict]] = {}
    for item in raw_items:
        code = str(item.get('atom_code') or '').strip()
        nid = str(item.get('source_node_id') or '').strip()
        if code not in atom_meta_by_code or nid not in node_by_id:
            continue
        try:
            conf = float(item.get('confidence', 0.0))
        except (TypeError, ValueError):
            continue
        if conf < confidence_threshold or conf > 1.0:
            continue
        role = str(item.get('alignment_role') or default_role).strip()
        if role not in SourceAlignment.AlignmentRole.values:
            role = default_role
        reason = clean_resource_excerpt(str(item.get('match_reason') or ''), max_len=60)[:30]
        per_atom_best.setdefault(code, []).append({
            'source_node_id': nid,
            'alignment_role': role,
            'match_reason': reason,
            'confidence': round(conf, 3),
        })

    created_rows: list[SourceAlignment] = []
    with transaction.atomic():
        # Preserve manually verified alignments; replace unverified auto alignments for this source.
        verified_keys = set(
            SourceAlignment.objects.filter(source_document=source_doc, is_verified=True)
            .values_list('block_id', 'atom_id', 'source_node_id')
        )
        SourceAlignment.objects.filter(source_document=source_doc, is_verified=False).delete()

        for code, candidates in per_atom_best.items():
            block, atom = atom_meta_by_code[code]
            dedup = {}
            for cand in sorted(candidates, key=lambda c: -c['confidence']):
                dedup.setdefault(cand['source_node_id'], cand)
            for cand in list(dedup.values())[:MAX_ALIGNMENTS_PER_ATOM]:
                nid = cand['source_node_id']
                if (block.pk, atom.pk, nid) in verified_keys:
                    continue
                node = node_by_id[nid]
                section_text = raw_sections.get(nid) or node.get('summary') or node['title']
                excerpt = clean_resource_excerpt(section_text, max_len=300)
                source_url = node.get('url') or source_doc.url or ''
                row = SourceAlignment.objects.create(
                    source_document=source_doc,
                    block=block,
                    atom=atom,
                    source_node_id=nid,
                    section_title=node['title'][:240],
                    locator=(node.get('locator') or node['title'])[:160],
                    source_url=source_url[:1000],
                    excerpt_quote=excerpt,
                    alignment_role=cand['alignment_role'],
                    match_reason=cand['match_reason'],
                    confidence=cand['confidence'],
                    is_verified=False,
                )
                created_rows.append(row)

    all_rows = list(
        SourceAlignment.objects.filter(source_document=source_doc)
        .select_related('source_document', 'block', 'atom')
        .order_by('-is_verified', '-confidence', 'id')
    )
    return {
        'source_id': source_doc.pk,
        'used_ai': used_ai,
        'created_count': len(created_rows),
        'coverage': build_source_coverage_summary(build, source_doc),
        'alignments': all_rows,
    }
