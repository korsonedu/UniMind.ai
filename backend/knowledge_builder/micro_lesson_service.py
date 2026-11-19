"""Source-Grounded native multimodal AtomMicroLesson lazy generation & caching."""
import logging
import re

from django.db import transaction

from ai_engine import config
from . import prompts
from .models import AtomMicroLesson, BlockStepAtom, KnowledgeTreeBuild, SourceAlignment, TreeAtomPoint
from .public_asset_service import compute_atom_difficulty
from .source_parsers import clean_resource_excerpt

logger = logging.getLogger(__name__)

VALID_STYLES = ('balanced', 'intuition', 'exam', 'visual')
_DANGEROUS_HTML_RE = re.compile(r'</?[A-Za-z][^>]*>|<![^>]*>|\\(?:href|url|html\w*)\b|(?:javascript|data):', re.I)


def _safe_str(value, max_len: int = 400) -> str:
    text = str(value or '').strip()
    text = _DANGEROUS_HTML_RE.sub('', text)
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + '…'
    return text


def _sanitize_visual(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None
    vtype = str(raw.get('type') or '').strip()
    payload = raw.get('payload')
    if not isinstance(payload, dict):
        return None

    if vtype == 'concept_diagram':
        raw_nodes = payload.get('nodes') or []
        if not isinstance(raw_nodes, list) or len(raw_nodes) < 2:
            return None
        nodes = []
        valid_ids = set()
        for idx, node in enumerate(raw_nodes[:8], 1):
            if not isinstance(node, dict):
                continue
            nid = _safe_str(node.get('id') or f'n{idx}', 40)
            label = _safe_str(node.get('label'), 80)
            if not label:
                continue
            valid_ids.add(nid)
            nodes.append({
                'id': nid,
                'label': label,
                'detail': _safe_str(node.get('detail'), 220),
                'badge': _safe_str(node.get('badge'), 36),
                'highlight': bool(node.get('highlight', False)),
            })
        if len(nodes) < 2:
            return None
        edges = []
        for edge in (payload.get('edges') or [])[:10]:
            if not isinstance(edge, dict):
                continue
            src = _safe_str(edge.get('from'), 40)
            dst = _safe_str(edge.get('to'), 40)
            if src in valid_ids and dst in valid_ids and src != dst:
                edges.append({'from': src, 'to': dst, 'label': _safe_str(edge.get('label'), 60)})
        layout = payload.get('layout') if payload.get('layout') in ('flow', 'hierarchy', 'cycle', 'compare') else 'flow'
        return {
            'type': 'concept_diagram',
            'payload': {
                'title': _safe_str(payload.get('title') or '核心概念结构图', 120),
                'subtitle': _safe_str(payload.get('subtitle'), 200),
                'layout': layout,
                'nodes': nodes,
                'edges': edges,
            },
        }

    if vtype == 'comparison_table':
        raw_cols = payload.get('columns') or []
        raw_rows = payload.get('rows') or []
        if not isinstance(raw_cols, list) or len(raw_cols) < 2 or not isinstance(raw_rows, list) or not raw_rows:
            return None
        columns = [_safe_str(c, 60) for c in raw_cols[:5] if _safe_str(c, 60)]
        if len(columns) < 2:
            return None
        rows = []
        for row in raw_rows[:8]:
            if not isinstance(row, dict):
                continue
            dim = _safe_str(row.get('dimension'), 80)
            cells = [_safe_str(c, 220) for c in (row.get('cells') or [])[: len(columns)]]
            while len(cells) < len(columns):
                cells.append('—')
            if dim:
                rows.append({
                    'dimension': dim,
                    'cells': cells,
                    'pitfall': _safe_str(row.get('pitfall'), 180),
                })
        if not rows:
            return None
        return {
            'type': 'comparison_table',
            'payload': {
                'title': _safe_str(payload.get('title') or '易混机制对比矩阵', 120),
                'subtitle': _safe_str(payload.get('subtitle'), 200),
                'columns': columns,
                'rows': rows,
            },
        }

    if vtype == 'storyboard':
        raw_frames = payload.get('frames') or []
        if not isinstance(raw_frames, list) or len(raw_frames) < 2:
            return None
        frames = []
        for idx, frame in enumerate(raw_frames[:6], 1):
            if not isinstance(frame, dict):
                continue
            heading = _safe_str(frame.get('heading'), 100)
            board = _safe_str(frame.get('board'), 480)
            if not heading or not board:
                continue
            frames.append({
                'step': idx,
                'heading': heading,
                'board': board,
                'formula': _safe_str(frame.get('formula'), 500),
                'takeaway': _safe_str(frame.get('takeaway'), 220),
                'pitfall': _safe_str(frame.get('pitfall'), 220),
            })
        if len(frames) < 2:
            return None
        return {
            'type': 'storyboard',
            'payload': {
                'title': _safe_str(payload.get('title') or '分步板书推演', 120),
                'subtitle': _safe_str(payload.get('subtitle'), 200),
                'frames': frames,
            },
        }

    if vtype == 'latex_derivation':
        raw_steps = payload.get('steps') or []
        steps = [
            {'latex': _safe_str(s.get('latex'), 1200), 'note': _safe_str(s.get('note'), 300)}
            for s in raw_steps[:8]
            if isinstance(s, dict) and _safe_str(s.get('latex'), 1200)
        ]
        if not steps:
            return None
        return {'type': 'latex_derivation', 'payload': {'title': _safe_str(payload.get('title') or '公式推导', 120), 'steps': steps}}

    if vtype == 'step_solution':
        raw_steps = payload.get('steps') or []
        steps = [
            {'text': _safe_str(s.get('text'), 600), 'latex': _safe_str(s.get('latex'), 1000)}
            for s in raw_steps[:8]
            if isinstance(s, dict) and _safe_str(s.get('text'), 600)
        ]
        if not steps:
            return None
        return {'type': 'step_solution', 'payload': {'title': _safe_str(payload.get('title') or '分步解题', 120), 'steps': steps}}

    return None


def _sanitize_quick_check(raw: dict, atom: TreeAtomPoint) -> dict:
    if isinstance(raw, dict):
        question = _safe_str(raw.get('question'), 320)
        options = []
        valid_keys = []
        for idx, opt in enumerate((raw.get('options') or [])[:4]):
            if not isinstance(opt, dict):
                continue
            key = _safe_str(opt.get('key') or chr(65 + idx), 4).upper()
            label = _safe_str(opt.get('label'), 200)
            if key and label and key not in valid_keys:
                valid_keys.append(key)
                options.append({'key': key, 'label': label})
        answer = _safe_str(raw.get('answer'), 4).upper()
        explanation = _safe_str(raw.get('explanation'), 320)
        if question and len(options) >= 2 and answer in valid_keys and explanation:
            return {
                'question': question,
                'options': options,
                'answer': answer,
                'explanation': explanation,
            }
    # Deterministic safe fallback
    key_elem = (atom.key_elements or [atom.name])[0]
    misconception = (atom.common_misconceptions or ['忽略前提条件直接套用结论'])[0]
    return {
        'question': f'关于「{atom.name}」，以下说法最准确的是？',
        'options': [
            {'key': 'A', 'label': f'核心在于把握：{key_elem}'},
            {'key': 'B', 'label': f'可以直接按“{misconception}”处理，无需区分边界'},
        ],
        'answer': 'A',
        'explanation': f'学习「{atom.name}」必须紧扣「{key_elem}」，避免陷入「{misconception}」误区。',
    }


def _build_fallback_lesson(atom: TreeAtomPoint, tier: str, citations: list[dict]) -> dict:
    elements = [str(e).strip() for e in (atom.key_elements or []) if str(e).strip()]
    misconceptions = [str(m).strip() for m in (atom.common_misconceptions or []) if str(m).strip()]
    hook = clean_resource_excerpt(atom.goal_statement or f'{atom.name}是本阶段的关键核心概念。', max_len=140)
    pitfalls = misconceptions[:3] or [f'容易混淆「{atom.name}」的适用边界与前提条件。']

    if tier == 'L2':
        rows = []
        for idx, el in enumerate(elements[:4] or [atom.name, '适用边界'], 1):
            rows.append({
                'dimension': f'要点 {idx}',
                'cells': [el, f'需结合「{atom.name}」场景验证'],
                'pitfall': pitfalls[min(idx - 1, len(pitfalls) - 1)] if pitfalls else '',
            })
        visual = {
            'type': 'comparison_table',
            'payload': {
                'title': f'{atom.name} · 核心机制辨析表',
                'subtitle': '对照关键要素与考场常见误区',
                'columns': ['核心要素', '实战判别要点'],
                'rows': rows,
            },
        }
    elif tier == 'L3':
        frames = [
            {
                'step': 1,
                'heading': '明确问题与前提条件',
                'board': hook,
                'formula': '',
                'takeaway': f'先锁定核心要素：{"、".join(elements[:3]) or atom.name}',
                'pitfall': '',
            },
            {
                'step': 2,
                'heading': '核心机制与推演路径',
                'board': f'围绕「{atom.name}」拆解因果链条，将已知条件逐项代入验证。',
                'formula': '',
                'takeaway': '每一步推导都要回查前提假设是否成立。',
                'pitfall': pitfalls[0],
            },
            {
                'step': 3,
                'heading': '边界核验与防坑复盘',
                'board': f'核查是否触发常见误区：{"；".join(pitfalls[:2])}',
                'formula': '',
                'takeaway': '做完计算或推导后，用反例快速交叉检验结论。',
                'pitfall': '',
            },
        ]
        visual = {
            'type': 'storyboard',
            'payload': {
                'title': f'{atom.name} · 3 步硬核板书',
                'subtitle': '按步骤推进推导与验证',
                'frames': frames,
            },
        }
    else:
        node_labels = elements[:4] if len(elements) >= 2 else [f'{atom.name} 定义', '核心条件', '典型应用']
        nodes = [
            {
                'id': f'n{i}',
                'label': lbl[:40],
                'detail': hook if i == 1 else f'构成「{atom.name}」的关键环节',
                'badge': '核心' if i == 1 else f'要素{i}',
                'highlight': i == 1,
            }
            for i, lbl in enumerate(node_labels, 1)
        ]
        edges = [{'from': f'n{i}', 'to': f'n{i + 1}', 'label': '支撑'} for i in range(1, len(nodes))]
        visual = {
            'type': 'concept_diagram',
            'payload': {
                'title': f'{atom.name} · 概念速通图解',
                'subtitle': '2 分钟理清定义与核心要素关系',
                'layout': 'flow',
                'nodes': nodes,
                'edges': edges,
            },
        }

    narration_parts = [f'我们用一分钟快速拿下「{atom.name}」。', hook]
    if elements:
        narration_parts.append(f'记住这几个关键抓手：{"、".join(elements[:4])}。')
    if pitfalls:
        narration_parts.append(f'最容易掉坑的地方是：{pitfalls[0]}。')
    if citations:
        narration_parts.append(f'对应主线资料可查阅「{citations[0]["title"]}」的 {citations[0]["locator"]}。')
    narration_parts.append('听完可以马上做一下下面的三十秒快检题。')

    return {
        'hook_summary': hook,
        'pitfalls': pitfalls,
        'narration_script': ''.join(narration_parts),
        'visuals': [visual],
        'quick_check': _sanitize_quick_check({}, atom),
    }


def collect_atom_alignments(build: KnowledgeTreeBuild, atom: TreeAtomPoint) -> list[SourceAlignment]:
    """Return atom-level alignments first, falling back to block-level alignments if none exist."""
    atom_rows = list(
        SourceAlignment.objects.filter(source_document__build=build, atom=atom)
        .select_related('source_document', 'block', 'atom')
        .order_by('-is_verified', '-source_document__is_primary', '-confidence', 'id')
    )
    if atom_rows:
        return atom_rows
    assignment = BlockStepAtom.objects.filter(atom=atom, step__block__build=build).select_related('step__block').first()
    if not assignment:
        return []
    return list(
        SourceAlignment.objects.filter(source_document__build=build, block=assignment.step.block, atom__isnull=True)
        .select_related('source_document', 'block')
        .order_by('-is_verified', '-source_document__is_primary', '-confidence', 'id')[:3]
    )


def _citations_and_excerpts(alignments: list[SourceAlignment]) -> tuple[list[dict], list[dict]]:
    citations = []
    excerpts = []
    for row in alignments[:4]:
        doc = row.source_document
        raw_sections = doc.raw_sections if isinstance(doc.raw_sections, dict) else {}
        full_excerpt = clean_resource_excerpt(raw_sections.get(row.source_node_id) or row.excerpt_quote, max_len=1200)
        quote = clean_resource_excerpt(row.excerpt_quote or full_excerpt, max_len=300)
        citations.append({
            'alignment_id': row.pk,
            'source_id': doc.pk,
            'title': doc.title,
            'source_kind': doc.source_kind,
            'section_title': row.section_title,
            'locator': row.locator,
            'quote': quote,
            'full_excerpt': full_excerpt,
            'url': row.source_url or doc.url or '',
            'alignment_role': row.alignment_role,
            'match_reason': row.match_reason,
            'is_verified': row.is_verified,
        })
        if full_excerpt:
            excerpts.append({
                'source_title': doc.title,
                'locator': row.locator,
                'section_title': row.section_title,
                'excerpt': full_excerpt,
            })
    return citations, excerpts


def get_or_generate_micro_lesson(
    build: KnowledgeTreeBuild,
    atom: TreeAtomPoint,
    *,
    generate: bool = False,
    regenerate: bool = False,
    style: str = 'balanced',
) -> tuple[AtomMicroLesson | None, list[dict]]:
    """Read cached AtomMicroLesson or lazily generate a source-grounded multimodal micro-lesson."""
    style = style if style in VALID_STYLES else 'balanced'
    tier, tier_label = compute_atom_difficulty(atom)
    alignments = collect_atom_alignments(build, atom)
    citations, excerpts = _citations_and_excerpts(alignments)
    existing = AtomMicroLesson.objects.filter(build=build, atom=atom).first()

    if not generate:
        return existing, citations

    if existing and existing.status == AtomMicroLesson.Status.READY and not regenerate and existing.style == style:
        # Refresh citations if new source alignments were added since generation without regenerating LLM text unless requested.
        if not existing.citations and citations:
            existing.citations = citations
            existing.grounded_source_ids = [c['alignment_id'] for c in citations]
            existing.is_source_grounded = True
            existing.save(update_fields=('citations', 'grounded_source_ids', 'is_source_grounded', 'updated_at'))
        return existing, citations

    target_modality = {'L1': 'concept_diagram', 'L2': 'comparison_table', 'L3': 'storyboard'}.get(tier, 'concept_diagram')
    if style == 'exam':
        target_modality = 'comparison_table'
    elif style == 'visual':
        target_modality = 'storyboard' if tier == 'L3' else 'concept_diagram'

    generated = None
    if config._get_api_key():
        context = {
            'subject': build.subject,
            'atom': {
                'code': atom.code,
                'name': atom.name,
                'goal_statement': atom.goal_statement,
                'goal_type': atom.goal_type,
                'cognitive_level': atom.cognitive_level,
                'difficulty_tier': tier,
                'difficulty_label': tier_label,
                'key_elements': list(atom.key_elements or []),
                'common_misconceptions': list(atom.common_misconceptions or []),
            },
            'preferred_visual_type': target_modality,
            'style': style,
            'source_excerpts': excerpts[:3],
        }
        try:
            raw = prompts.ask('atom_micro_lesson', context, operation='knowledge_builder_micro_lesson')
            valid_visuals = [v for v in (_sanitize_visual(item) for item in (raw.get('visuals') or [])) if v]
            if valid_visuals:
                generated = {
                    'hook_summary': _safe_str(raw.get('hook_summary'), 260),
                    'pitfalls': [_safe_str(p, 140) for p in (raw.get('pitfalls') or [])[:4] if _safe_str(p, 140)],
                    'narration_script': _safe_str(raw.get('narration_script'), 800),
                    'visuals': valid_visuals[:2],
                    'quick_check': _sanitize_quick_check(raw.get('quick_check') or {}, atom),
                }
        except Exception as exc:
            logger.warning('AtomMicroLesson LLM generation failed for atom %s, using fallback: %s', atom.pk, exc)

    if generated is None:
        generated = _build_fallback_lesson(atom, tier, citations)

    with transaction.atomic():
        next_version = (existing.version + 1) if existing else 1
        lesson, _ = AtomMicroLesson.objects.update_or_create(
            atom=atom,
            defaults={
                'build': build,
                'version': next_version,
                'difficulty_tier': tier,
                'style': style,
                'is_source_grounded': bool(citations),
                'grounded_source_ids': [c['alignment_id'] for c in citations],
                'hook_summary': generated['hook_summary'],
                'pitfalls': generated['pitfalls'],
                'narration_script': generated['narration_script'],
                'visuals': generated['visuals'],
                'quick_check': generated['quick_check'],
                'citations': citations,
                'status': AtomMicroLesson.Status.READY,
                'error_message': '',
            },
        )
    return lesson, citations
