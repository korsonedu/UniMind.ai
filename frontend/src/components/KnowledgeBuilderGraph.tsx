import { t, useLocale } from '@/i18n';
import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { CSSProperties, MouseEvent as ReactMouseEvent, ReactNode } from 'react';
import type { BaselineSummary, KnowledgeTreeBuildDetail } from '@/types/knowledgeBuilder';
import { resolvePublicAssetLink } from '@/lib/knowledgeBuilderApi';
import {
  adaptKnowledgeTree,
  computeColumnLayout,
  computeOuterWireRoutes,
  roundedOrthoPath,
  type AdaptedBlock,
  type AdaptedEdge,
  type AdaptedStep,
  type BoxRect,
  type ComputedOuterWire,
  type EdgeFilterMode,
} from '@/lib/knowledgeBuilderLayout';

interface KnowledgeBuilderGraphProps {
  tree: KnowledgeTreeBuildDetail;
  headerLeftSlot?: ReactNode;
  headerRightSlot?: ReactNode;
  selectedBlockIds?: ReadonlySet<number>;
  onToggleBlockSelection?: (id: number) => void;
  onStudyBlock?: (id: number) => void;
}

interface TooltipState {
  title: string;
  body: string;
  x: number;
  y: number;
}

interface ComputedInnerWire {
  key: string;
  d: string;
  kind: 'progression' | 'contrast';
  fromName: string;
  toName: string;
  reason: string;
}

interface InnerWireResult {
  width: number;
  height: number;
  wires: ComputedInnerWire[];
}

function normalizeTopicName(name: string): string {
  return name.replace(/\s+/g, '').toLowerCase();
}

function readInitialOpenIds(buildId: string, entryBlockId: number | null, validIds: Set<number>): Set<number> {
  try {
    const raw = window.localStorage.getItem(`kb:v3:open:${buildId}`);
    if (raw !== null) {
      const parsed: unknown = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        return new Set(parsed.filter((id): id is number => typeof id === 'number' && validIds.has(id)));
      }
    }
  } catch {
    // Ignore localStorage parse or quota failures.
  }
  return entryBlockId !== null && validIds.has(entryBlockId) ? new Set([entryBlockId]) : new Set();
}

function computeInnerWiresForCard(stepsEl: HTMLElement, block: AdaptedBlock): InnerWireResult {
  const groups = stepsEl.querySelectorAll<HTMLElement>('.kb-pointgroup');
  groups.forEach(group => {
    group.style.paddingTop = '';
  });

  const measureBoxes = () => {
    const stepsRect = stepsEl.getBoundingClientRect();
    const pointMap = new Map<string, BoxRect & { col: number; name: string }>();
    const groupTopMap = new Map<number, number>();

    const stepCols = stepsEl.querySelectorAll<HTMLElement>('.kb-step');
    stepCols.forEach((stepEl, colIdx) => {
      const pg = stepEl.querySelector<HTMLElement>('.kb-pointgroup');
      if (pg) {
        const points = pg.querySelectorAll<HTMLElement>('[data-point]');
        if (points.length > 0) {
          const firstRect = points[0].getBoundingClientRect();
          groupTopMap.set(colIdx, firstRect.top - stepsRect.top + stepsEl.scrollTop);
        }
      }
    });

    const stepByCol = new Map<number, AdaptedStep>();
    block.steps.forEach((s, idx) => stepByCol.set(idx, s));

    stepCols.forEach((stepEl, colIdx) => {
      const stepData = stepByCol.get(colIdx);
      const nameByCode = new Map<string, string>();
      stepData?.atoms.forEach(a => nameByCode.set(a.atom.code, a.atom.name));

      const points = stepEl.querySelectorAll<HTMLElement>('[data-point]');
      points.forEach(el => {
        const code = el.dataset.point;
        if (!code) return;
        const r = el.getBoundingClientRect();
        pointMap.set(code, {
          x: r.left - stepsRect.left + stepsEl.scrollLeft,
          y: r.top - stepsRect.top + stepsEl.scrollTop,
          w: r.width,
          h: r.height,
          col: colIdx,
          name: nameByCode.get(code) ?? code,
        });
      });
    });

    return { pointMap, groupTopMap };
  };

  const allLines = block.steps.flatMap(step =>
    step.intraLines.map((line, idx) => ({
      ...line,
      key: `${step.id}:${line.from_atom_code}->${line.to_atom_code}:${idx}`,
    }))
  );

  // First pass: check multi-step horizontal wires that would pass across intermediate step point groups.
  const firstMeasure = measureBoxes();
  const extraPadByCol = new Map<number, number>();
  for (const line of allLines) {
    const a = firstMeasure.pointMap.get(line.from_atom_code);
    const b = firstMeasure.pointMap.get(line.to_atom_code);
    if (!a || !b || Math.abs(b.col - a.col) <= 1) continue;
    const minCol = Math.min(a.col, b.col);
    const maxCol = Math.max(a.col, b.col);
    const corridorTop = Math.min(a.y + a.h / 2, b.y + b.h / 2);
    const targetTop = Math.max(corridorTop - 16, 48);
    for (let c = minCol + 1; c < maxCol; c++) {
      const currentTop = firstMeasure.groupTopMap.get(c);
      if (currentTop !== undefined && currentTop < targetTop + 26) {
        const need = Math.ceil(targetTop + 26 - currentTop);
        extraPadByCol.set(c, Math.max(extraPadByCol.get(c) ?? 0, need));
      }
    }
  }

  if (extraPadByCol.size > 0) {
    const stepCols = stepsEl.querySelectorAll<HTMLElement>('.kb-step');
    extraPadByCol.forEach((padPx, colIdx) => {
      const pg = stepCols[colIdx]?.querySelector<HTMLElement>('.kb-pointgroup');
      if (pg) {
        pg.style.paddingTop = `${Math.min(padPx, 160)}px`;
      }
    });
  }

  const { pointMap, groupTopMap } = extraPadByCol.size > 0 ? measureBoxes() : firstMeasure;
  const wires: ComputedInnerWire[] = [];
  const sameStepLaneByCol = new Map<number, number>();
  let multiStepLane = 0;

  for (const line of allLines) {
    const a = pointMap.get(line.from_atom_code);
    const b = pointMap.get(line.to_atom_code);
    if (!a || !b) continue;

    let d = '';
    if (a.col === b.col) {
      const lane = sameStepLaneByCol.get(a.col) ?? 0;
      sameStepLaneByCol.set(a.col, lane + 1);
      const rightEdge = Math.max(a.x + a.w, b.x + b.w);
      const bend = rightEdge + 8 + lane * 6;
      const y1 = a.y + a.h / 2;
      const y2 = b.y + b.h / 2;
      d = roundedOrthoPath(
        [
          [a.x + a.w, y1],
          [bend, y1],
          [bend, y2],
          [b.x + b.w, y2],
        ],
        6
      );
    } else if (Math.abs(b.col - a.col) === 1) {
      const goRight = b.col > a.col;
      const x1 = goRight ? a.x + a.w : a.x;
      const y1 = a.y + a.h / 2;
      const x2 = goRight ? b.x : b.x + b.w;
      const y2 = b.y + b.h / 2;
      const midX = (x1 + x2) / 2;
      d = `M ${x1.toFixed(1)} ${y1.toFixed(1)} C ${midX.toFixed(1)} ${y1.toFixed(1)}, ${midX.toFixed(1)} ${y2.toFixed(1)}, ${x2.toFixed(1)} ${y2.toFixed(1)}`;
    } else {
      const goRight = b.col > a.col;
      const x1 = goRight ? a.x + a.w : a.x;
      const y1 = a.y + a.h / 2;
      const x2 = goRight ? b.x : b.x + b.w;
      const y2 = b.y + b.h / 2;
      const minCol = Math.min(a.col, b.col);
      const maxCol = Math.max(a.col, b.col);
      let safeTop = Math.min(y1, y2) - 14;
      for (let c = minCol + 1; c < maxCol; c++) {
        const gTop = groupTopMap.get(c);
        if (gTop !== undefined) {
          safeTop = Math.min(safeTop, gTop - 10);
        }
      }
      const laneY = Math.max(12, safeTop - (multiStepLane % 4) * 7);
      multiStepLane++;
      const stub = goRight ? 10 : -10;
      d = roundedOrthoPath(
        [
          [x1, y1],
          [x1 + stub, y1],
          [x1 + stub, laneY],
          [x2 - stub, laneY],
          [x2 - stub, y2],
          [x2, y2],
        ],
        8
      );
    }

    if (d) {
      wires.push({
        key: line.key,
        d,
        kind: line.kind,
        fromName: a.name,
        toName: b.name,
        reason: line.reason,
      });
    }
  }

  return {
    width: Math.max(stepsEl.scrollWidth, stepsEl.clientWidth),
    height: Math.max(stepsEl.scrollHeight, stepsEl.clientHeight),
    wires,
  };
}

export function KnowledgeBuilderGraph({
  tree,
  headerLeftSlot,
  headerRightSlot,
  selectedBlockIds,
  onToggleBlockSelection,
  onStudyBlock,
}: KnowledgeBuilderGraphProps) {
  const locale = useLocale();
  const uid = useId().replace(/:/g, '');
  const adapted = useMemo(() => adaptKnowledgeTree(tree, locale === 'en' ? t : undefined), [tree, locale]);
  const topicGroups = useMemo(() => {
    const baseline = tree.requirements?.baseline_summary as Partial<BaselineSummary> | undefined;
    return [
      { kind: 'gap', label: '重点强化', topics: baseline?.gap_topics },
      { kind: 'entry', label: '推荐切入', topics: tree.requirements?.suggested_entry_topics },
      { kind: 'known', label: '已有基础', topics: baseline?.known_topics },
    ].map(group => ({ ...group, topics: Array.isArray(group.topics)
      ? group.topics.filter((topic): topic is string => typeof topic === 'string')
        .map(name => ({ name, normalized: normalizeTopicName(name) })).filter(topic => topic.normalized)
      : [] }));
  }, [tree.requirements]);
  const renderTopicBadges = (names: string[]) => {
    const normalizedNames = names.map(normalizeTopicName).filter(Boolean);
    return topicGroups.map(group => {
      const matched = group.topics.filter(topic => normalizedNames.some(name =>
        name.includes(topic.normalized) || topic.normalized.includes(name)));
      return matched.length ? <span key={group.kind} className={`kb-badge kb-badge--${group.kind}`}
        title={t('匹配主题：{0}', { 0: matched.map(topic => topic.name).join('、') })}>{t(group.label)}</span> : null;
    });
  };

  const [edgeMode, setEdgeMode] = useState<EdgeFilterMode>('retained');
  const [openByBuild, setOpenByBuild] = useState<Record<string, Set<number>>>({});
  const openIds = useMemo(() => {
    const existing = openByBuild[adapted.buildId];
    if (existing) return existing;
    const valid = new Set(adapted.blocks.map(b => b.id));
    return readInitialOpenIds(adapted.buildId, adapted.entryBlockId, valid);
  }, [adapted.blocks, adapted.buildId, adapted.entryBlockId, openByBuild]);

  const updateOpenIds = useCallback(
    (updater: (prev: Set<number>) => Set<number>) => {
      setOpenByBuild(prevMap => {
        const curr =
          prevMap[adapted.buildId] ??
          readInitialOpenIds(
            adapted.buildId,
            adapted.entryBlockId,
            new Set(adapted.blocks.map(b => b.id))
          );
        return { ...prevMap, [adapted.buildId]: updater(curr) };
      });
    },
    [adapted.blocks, adapted.buildId, adapted.entryBlockId]
  );

  useEffect(() => {
    try {
      window.localStorage.setItem(`kb:v3:open:${adapted.buildId}`, JSON.stringify([...openIds]));
    } catch {
      // Ignore storage quota errors.
    }
  }, [adapted.buildId, openIds]);

  const [hoveredBlockId, setHoveredBlockId] = useState<number | null>(null);
  const [hoveredEdge, setHoveredEdge] = useState<AdaptedEdge | null>(null);
  const [flashBlockId, setFlashBlockId] = useState<number | null>(null);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  const activeEdges = useMemo(
    () => (edgeMode === 'retained' ? adapted.edges.filter(e => e.isRetained) : adapted.edges),
    [adapted.edges, edgeMode]
  );

  const layout = useMemo(
    () => computeColumnLayout(adapted.blocks, activeEdges, openIds),
    [adapted.blocks, activeEdges, openIds]
  );

  const columnIndexByBlockId = useMemo(() => {
    const map = new Map<number, number>();
    layout.columns.forEach((col, colIdx) => {
      col.blocks.forEach(b => map.set(b.id, colIdx));
    });
    return map;
  }, [layout.columns]);

  // Adjacency for hover highlight.
  const { highlightedBlockIds, highlightedEdgeIds } = useMemo(() => {
    const bIds = new Set<number>();
    const eIds = new Set<number>();
    if (hoveredEdge !== null) {
      bIds.add(hoveredEdge.from);
      bIds.add(hoveredEdge.to);
      eIds.add(hoveredEdge.id);
    } else if (hoveredBlockId !== null) {
      bIds.add(hoveredBlockId);
      for (const e of activeEdges) {
        if (e.from === hoveredBlockId || e.to === hoveredBlockId) {
          eIds.add(e.id);
          bIds.add(e.from);
          bIds.add(e.to);
        }
      }
    }
    return { highlightedBlockIds: bIds, highlightedEdgeIds: eIds };
  }, [activeEdges, hoveredBlockId, hoveredEdge]);

  const hasHoverFocus = hoveredBlockId !== null || hoveredEdge !== null;

  const viewportRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<HTMLDivElement | null>(null);
  const cardRefs = useRef<Map<number, HTMLElement>>(new Map());
  const stepsRefs = useRef<Map<number, HTMLElement>>(new Map());
  const dragRef = useRef<{
    active: boolean;
    moved: boolean;
    startX: number;
    startY: number;
    scrollLeft: number;
    scrollTop: number;
  }>({ active: false, moved: false, startX: 0, startY: 0, scrollLeft: 0, scrollTop: 0 });
  const [isDragging, setIsDragging] = useState(false);

  const [outerWires, setOuterWires] = useState<ComputedOuterWire[]>([]);
  const [outerSize, setOuterSize] = useState<{ w: number; h: number }>({ w: 0, h: 0 });
  const [innerWiresByBlock, setInnerWiresByBlock] = useState<Map<number, InnerWireResult>>(new Map());
  const [layoutTick, setLayoutTick] = useState(0);
  const measureSigRef = useRef<string>('');

  const scheduleMeasure = useCallback(() => {
    setLayoutTick(t => t + 1);
  }, []);

  useEffect(() => {
    const mapEl = mapRef.current;
    if (!mapEl || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => {
      scheduleMeasure();
    });
    ro.observe(mapEl);
    cardRefs.current.forEach(el => ro.observe(el));
    stepsRefs.current.forEach(el => ro.observe(el));
    return () => ro.disconnect();
  }, [openIds, layout, scheduleMeasure]);

  useLayoutEffect(() => {
    const mapEl = mapRef.current;
    if (!mapEl) return;

    // 1) Compute intrablock SVG wires & cross-step padding first (affects card heights!).
    const nextInner = new Map<number, InnerWireResult>();
    for (const block of adapted.blocks) {
      if (!openIds.has(block.id)) continue;
      const stepsEl = stepsRefs.current.get(block.id);
      if (!stepsEl) continue;
      nextInner.set(block.id, computeInnerWiresForCard(stepsEl, block));
    }

    // 2) Now measure card & header boxes for the outer SVG layer.
    const mapRect = mapEl.getBoundingClientRect();
    const blockBoxes = new Map<number, BoxRect>();
    const headerBoxes = new Map<number, BoxRect>();

    cardRefs.current.forEach((cardEl, blockId) => {
      const cRect = cardEl.getBoundingClientRect();
      blockBoxes.set(blockId, {
        x: cRect.left - mapRect.left,
        y: cRect.top - mapRect.top,
        w: cRect.width,
        h: cRect.height,
      });
      const toggleEl = cardEl.querySelector<HTMLElement>('.kb-toggle');
      const hRect = toggleEl ? toggleEl.getBoundingClientRect() : cRect;
      headerBoxes.set(blockId, {
        x: hRect.left - mapRect.left,
        y: hRect.top - mapRect.top,
        w: hRect.width,
        h: hRect.height,
      });
    });

    const computed = computeOuterWireRoutes({
      blockBoxes,
      headerBoxes,
      columnIndexByBlockId,
      activeEdges,
    });
    const nextSize = { w: mapEl.scrollWidth, h: mapEl.scrollHeight };

    const sig = [
      `${nextSize.w}x${nextSize.h}`,
      computed.map(c => `${c.edge.id}:${c.d}`).join('|'),
      [...nextInner.entries()]
        .map(([bid, res]) => `${bid}:${res.width}x${res.height}:${res.wires.map(w => `${w.key}:${w.d}`).join(',')}`)
        .join('|'),
    ].join('||');

    if (sig === measureSigRef.current) return;
    measureSigRef.current = sig;

    setInnerWiresByBlock(nextInner);
    setOuterWires(computed);
    setOuterSize(nextSize);
  }, [adapted.blocks, activeEdges, columnIndexByBlockId, layout, openIds, layoutTick]);

  const toggleBlock = useCallback((blockId: number) => {
    if (dragRef.current.moved) return;
    updateOpenIds(prev => {
      const next = new Set(prev);
      if (next.has(blockId)) next.delete(blockId);
      else next.add(blockId);
      return next;
    });
  }, [updateOpenIds]);

  const openEntryOnly = useCallback(() => {
    updateOpenIds(() => (adapted.entryBlockId !== null ? new Set([adapted.entryBlockId]) : new Set()));
  }, [adapted.entryBlockId, updateOpenIds]);

  const collapseAll = useCallback(() => {
    updateOpenIds(() => new Set());
  }, [updateOpenIds]);

  const jumpToBlock = useCallback((targetBlockId: number) => {
    updateOpenIds(prev => {
      if (prev.has(targetBlockId)) return prev;
      const next = new Set(prev);
      next.add(targetBlockId);
      return next;
    });
    setFlashBlockId(targetBlockId);
    window.setTimeout(() => {
      setFlashBlockId(curr => (curr === targetBlockId ? null : curr));
    }, 1600);

    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        const vp = viewportRef.current;
        const targetEl = cardRefs.current.get(targetBlockId);
        if (!vp || !targetEl) return;
        const vpRect = vp.getBoundingClientRect();
        const elRect = targetEl.getBoundingClientRect();
        const left = vp.scrollLeft + (elRect.left - vpRect.left) - (vp.clientWidth - elRect.width) / 2;
        const top = vp.scrollTop + (elRect.top - vpRect.top) - Math.max(48, (vp.clientHeight - elRect.height) / 3);
        vp.scrollTo({
          left: Math.max(0, left),
          top: Math.max(0, top),
          behavior: 'smooth',
        });
      });
    });
  }, [updateOpenIds]);

  const showTooltip = useCallback((e: ReactMouseEvent<SVGElement>, title: string, body: string) => {
    const pad = 16;
    const maxW = 360;
    const x = Math.min(e.clientX + 14, window.innerWidth - maxW - pad);
    const y = Math.min(e.clientY + 14, window.innerHeight - 120);
    setTooltip({ title, body, x: Math.max(pad, x), y: Math.max(pad, y) });
  }, []);

  const hideTooltip = useCallback(() => {
    setTooltip(null);
  }, []);

  const handleViewportMouseDown = (e: ReactMouseEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    const target = e.target as HTMLElement;
    if (target.closest('button, a, select, input, .kb-dependency, .kb-point, path.wire-hit')) {
      return;
    }
    const vp = viewportRef.current;
    if (!vp) return;
    dragRef.current = {
      active: true,
      moved: false,
      startX: e.clientX,
      startY: e.clientY,
      scrollLeft: vp.scrollLeft,
      scrollTop: vp.scrollTop,
    };
  };

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      const d = dragRef.current;
      if (!d.active) return;
      const dx = e.clientX - d.startX;
      const dy = e.clientY - d.startY;
      if (!d.moved && Math.hypot(dx, dy) > 5) {
        d.moved = true;
        setIsDragging(true);
      }
      if (d.moved && viewportRef.current) {
        viewportRef.current.scrollLeft = d.scrollLeft - dx;
        viewportRef.current.scrollTop = d.scrollTop - dy;
      }
    };
    const onUp = () => {
      if (!dragRef.current.active) return;
      dragRef.current.active = false;
      setIsDragging(false);
      window.setTimeout(() => {
        dragRef.current.moved = false;
      }, 0);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, []);

  const markerUni = `${uid}-arrow-uni`;
  const markerBi = `${uid}-arrow-bi`;
  const markerEx = `${uid}-arrow-ex`;
  const markerAct = `${uid}-arrow-act`;
  const markerInner = `${uid}-arrow-in`;
  const markerInnerBi = `${uid}-arrow-in-bi`;

  return (
    <div className="kb-workspace">
      <header className="kb-header">
        <div className="kb-brand">
          {headerLeftSlot}
          <p className="kb-status">
            {t('{0} 个知识块 · {1} 个原子 · {2} 条精选单向 + {3} 条双向（候选 {4}）', { 0: adapted.blocks.length, 1: adapted.atomCount, 2: adapted.retainedUniCount, 3: adapted.retainedBiCount, 4: adapted.totalEdgeCount })}
          </p>
        </div>

        <div className="kb-nav">
          <button
            type="button"
            className={edgeMode === 'retained' ? 'active' : undefined}
            onClick={() => setEdgeMode('retained')}
          >
            {t('主干精选 ({0})', { 0: adapted.retainedCount })}
          </button>
          <button
            type="button"
            className={edgeMode === 'all' ? 'active' : undefined}
            onClick={() => setEdgeMode('all')}
          >
            {t('全量候选 ({0})', { 0: adapted.totalEdgeCount })}
          </button>
          <button type="button" onClick={openEntryOnly} disabled={adapted.entryBlockId === null}>
            {t('展开入口块')}
          </button>
          <button type="button" onClick={collapseAll} disabled={openIds.size === 0}>
            {t('收起全部')}
          </button>
          {headerRightSlot}
        </div>
      </header>

      <div className="kb-legend">
        {adapted.domains.map(dom => (
          <span key={dom.id}>
            <i style={{ background: dom.color }} />
            {dom.title}
          </span>
        ))}
        <span>{t('—→ 主干单向依赖')}</span>
        <span>{t('- - ↔ 双向强关联')}</span>
        <span className="kb-tip">{t('拖动画布 · 悬停块或连线聚焦上下游 · 点击块卡片原地展开')}</span>
      </div>

      <div
        ref={viewportRef}
        className={`kb-viewport${isDragging ? ' dragging' : ''}`}
        onMouseDown={handleViewportMouseDown}
      >
        <div ref={mapRef} className="kb-map">
          <svg
            className="kb-wires"
            width={outerSize.w || undefined}
            height={outerSize.h || undefined}
            aria-hidden="true"
          >
            <defs>
              <marker id={markerUni} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 1 1 L 9 5 L 1 9 z" fill="#8fa89b" />
              </marker>
              <marker id={markerBi} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 1 1 L 9 5 L 1 9 z" fill="#6c87a8" />
              </marker>
              <marker id={markerEx} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
                <path d="M 1 1 L 9 5 L 1 9 z" fill="#b5c3bc" />
              </marker>
              <marker id={markerAct} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
                <path d="M 1 1 L 9 5 L 1 9 z" fill="#c47d2b" />
              </marker>
              <marker id={markerInner} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5.5" markerHeight="5.5" orient="auto-start-reverse">
                <path d="M 1 1 L 9 5 L 1 9 z" fill="#64967f" />
              </marker>
              <marker id={markerInnerBi} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5.5" markerHeight="5.5" orient="auto-start-reverse">
                <path d="M 1 1 L 9 5 L 1 9 z" fill="#6c87a8" />
              </marker>
            </defs>

            {outerWires.map(({ edge, d }) => {
              const isActive = highlightedEdgeIds.has(edge.id);
              const isDimmed = hasHoverFocus && !isActive;
              const isBi = edge.kind === 'bidirectional';
              const isEx = !edge.isRetained;
              const endMarker = isActive
                ? `url(#${markerAct})`
                : isBi
                  ? `url(#${markerBi})`
                  : isEx
                    ? `url(#${markerEx})`
                    : `url(#${markerUni})`;
              const startMarker = isBi
                ? isActive
                  ? `url(#${markerAct})`
                  : `url(#${markerBi})`
                : undefined;

              const cls = [
                'wire-main',
                isBi ? 'bi' : '',
                isEx ? 'excluded' : '',
                isActive ? 'active' : '',
                isDimmed ? 'dimmed' : '',
              ]
                .filter(Boolean)
                .join(' ');

              const ttTitle = `${edge.fromCode} ${isBi ? '↔' : '→'} ${edge.toCode}${isEx ? t('（候选未入主干）') : ''}`;
              const ttBody = edge.rationale || edge.exclusionReason || t('跨块先修推理连线');

              return (
                <g
                  key={edge.id}
                  className="edge-group"
                  onMouseEnter={e => {
                    setHoveredEdge(edge);
                    showTooltip(e, ttTitle, ttBody);
                  }}
                  onMouseMove={e => showTooltip(e, ttTitle, ttBody)}
                  onMouseLeave={() => {
                    setHoveredEdge(null);
                    hideTooltip();
                  }}
                >
                  <path className={cls} d={d} markerEnd={endMarker} markerStart={startMarker} />
                  <path className="wire-hit" d={d} />
                </g>
              );
            })}
          </svg>

          {layout.columns.map(col => {
            const colHasOpen = col.blocks.some(b => openIds.has(b.id));
            const colStyle = {
              '--kb-cw': colHasOpen ? '960px' : '188px',
              '--kb-col-pad': `${col.colPadPx}px`,
            } as CSSProperties;

            return (
              <div key={col.layer} className="kb-column" style={colStyle}>
                <div className="kb-level">{t('第 {0} 层', { 0: col.layer })}</div>

                {col.blocks.map(block => {
                  const progress = tree.block_progress?.find(item => item.block === block.id);
                  const resources = tree.blocks.find(item => item.id === block.id)?.resources ?? [];
                  const spine = resources.find(resource => resource.asset_track === 'spine');
                  const hasSpotlight = resources.some(resource => resource.asset_track === 'spotlight');
                  const hasWiki = resources.some(resource => resource.asset_track === 'wiki');
                  const isOpen = openIds.has(block.id);
                  const isHighlighted = highlightedBlockIds.has(block.id) || flashBlockId === block.id;
                  const isDimmed = hasHoverFocus && !isHighlighted;
                  const cardClass = [
                    'kb-card',
                    isOpen ? 'open' : '',
                    isHighlighted ? 'highlighted' : '',
                    isDimmed ? 'dimmed' : '',
                  ]
                    .filter(Boolean)
                    .join(' ');

                  const innerResult = innerWiresByBlock.get(block.id);

                  return (
                    <article
                      key={block.id}
                      data-block-id={block.id}
                      ref={el => {
                        if (el) cardRefs.current.set(block.id, el);
                        else cardRefs.current.delete(block.id);
                      }}
                      className={cardClass}
                      style={{ '--kb-color': block.color } as CSSProperties}
                      onMouseEnter={() => setHoveredBlockId(block.id)}
                      onMouseLeave={() => setHoveredBlockId(curr => (curr === block.id ? null : curr))}
                    >
                      {onToggleBlockSelection && <label className="kb-select-block"><input type="checkbox" checked={selectedBlockIds?.has(block.id) ?? false}
                        onChange={() => onToggleBlockSelection(block.id)} />{t('加入项目目标')}</label>}
                      <button
                        type="button"
                        className="kb-toggle"
                        aria-expanded={isOpen}
                        onClick={() => toggleBlock(block.id)}
                      >
                        <span className="kb-plus" aria-hidden="true">
                          {isOpen ? '−' : '+'}
                        </span>
                        <strong>{block.shortTitle}</strong>
                        <small>
                          {t('{0} · {1} 步 · {2} 必学', { 0: block.code, 1: block.steps.length, 2: block.coreCount })}
                          {block.extensionCount > 0 ? t(' + {0} 拓展', { 0: block.extensionCount }) : ''}
                        </small>
                        <span className="kb-badges">
                          <span className="kb-cardtype">{block.domainTitle}</span>
                          {progress?.status === 'COMPLETED' && <span className="kb-badge kb-badge--mastered">已完成 ✓</span>}
                          {progress?.status === 'NEEDS_REVIEW' && <span className="kb-badge kb-badge--weak">待强化 · {Math.round(progress.last_accuracy * 100)}%</span>}
                          <span className="kb-badge">📚 {resources.length}</span>
                          {spine && <span className="kb-badge kb-asset-badge--spine" title={`主线配套课${spine.locator ? ` · ${spine.locator}` : ''}`}>🎬 {spine.locator || '主线'}</span>}
                          {hasSpotlight && <span className="kb-badge kb-asset-badge--spotlight" title="单点神作">🌟 神作</span>}
                          {hasWiki && <span className="kb-badge kb-asset-badge--wiki" title={tree.region_pref === 'intl' ? 'Wikipedia 概念词条' : 'OI-Wiki / 开源学科词条'}>{tree.region_pref === 'intl' ? '📖 Wikipedia 词条' : '📖 专业开源 Wiki 词条'}</span>}
                          {renderTopicBadges([block.shortTitle, ...block.steps.flatMap(step => step.atoms.map(item => item.atom.name))])}
                        </span>
                      </button>
                      {onStudyBlock && <button type="button" className="kb-study-open" aria-label={`${block.shortTitle}：学习资源 & 闯关检测`} onClick={() => onStudyBlock(block.id)}>资源 & 闯关</button>}

                      {isOpen && (
                        <div className="kb-panel">
                          <div className="kb-question">
                            <span className="kb-type">{block.structureType}</span>
                            {block.shapeTags.map(tag => (
                              <span key={tag} className="kb-type">
                                {tag}
                              </span>
                            ))}
                          </div>
                          {resources.length > 0 && <nav className="kb-card-resources" aria-label={`${block.shortTitle}的学习资源`}>
                            {resources.map(resource => {
                              const href = resolvePublicAssetLink(resource.url, resource.locator);
                              if (!href) return null;
                              const trackLabel = resource.asset_track === 'spine' ? '🎬 主线' : resource.asset_track === 'spotlight' ? '🌟 神作' : resource.asset_track === 'wiki' ? (tree.region_pref === 'intl' ? '📖 Wikipedia 词条' : '📖 专业开源 Wiki 词条') : '📚 资源';
                              return <a key={resource.id} className="kb-card-resource-link" href={href} target="_blank" rel="noopener noreferrer"
                                onClick={event => event.stopPropagation()} title={`直接打开：${resource.title}${resource.locator ? ` · ${resource.locator}` : ''}`}>
                                {trackLabel} · {resource.title}{resource.locator ? ` · ${resource.locator}` : ''} ↗
                              </a>;
                            })}
                          </nav>}
                          <div className="kb-hint">
                            {t('悬停知识点可查看学习目标与易错点；实线框为必学原子，虚线框为拓展延伸；点击黄色先修接口可跳转定位')}
                          </div>

                          <div
                            className="kb-steps"
                            ref={el => {
                              if (el) stepsRefs.current.set(block.id, el);
                              else stepsRefs.current.delete(block.id);
                            }}
                          >
                            {innerResult && innerResult.wires.length > 0 && (
                              <svg
                                className="kb-wires innerwire"
                                width={innerResult.width}
                                height={innerResult.height}
                                aria-hidden="true"
                              >
                                <defs>
                                  <marker id={`${markerInner}-${block.id}`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5.5" markerHeight="5.5" orient="auto-start-reverse">
                                    <path d="M 1 1 L 9 5 L 1 9 z" fill="#64967f" />
                                  </marker>
                                  <marker id={`${markerInnerBi}-${block.id}`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5.5" markerHeight="5.5" orient="auto-start-reverse">
                                    <path d="M 1 1 L 9 5 L 1 9 z" fill="#6c87a8" />
                                  </marker>
                                </defs>
                                {innerResult.wires.map(wire => {
                                  const isContrast = wire.kind === 'contrast';
                                  const wireTitle = `${wire.fromName} ${isContrast ? '↔' : '→'} ${wire.toName} (${isContrast ? t('对比关联') : t('步骤推进')})`;
                                  const wireBody = wire.reason || t('同块知识原子逻辑串联');
                                  return (
                                    <g
                                      key={wire.key}
                                      className="edge-group"
                                      onMouseEnter={e => showTooltip(e, wireTitle, wireBody)}
                                      onMouseMove={e => showTooltip(e, wireTitle, wireBody)}
                                      onMouseLeave={hideTooltip}
                                    >
                                      <path
                                        className={`wire-main${isContrast ? ' bi' : ''}`}
                                        d={wire.d}
                                        markerEnd={`url(#${isContrast ? `${markerInnerBi}-${block.id}` : `${markerInner}-${block.id}`})`}
                                      />
                                      <path className="wire-hit" d={wire.d} />
                                    </g>
                                  );
                                })}
                              </svg>
                            )}

                            {block.steps.map((step, stepIdx) => (
                              <div key={step.id} className="kb-step" data-step-idx={step.stepIndex}>
                                <h3>
                                  <em>
                                    STEP {stepIdx + 1}
                                    {step.role ? ` · ${step.role}` : ''}
                                  </em>
                                  <br />
                                  {step.title}
                                </h3>

                                {step.branchCondition ? (
                                  <div className="kb-branch">{t('分支条件：{0}', { 0: step.branchCondition })}</div>
                                ) : null}

                                {step.dependencies.map(dep => (
                                  <button
                                    key={dep.key}
                                    type="button"
                                    className="kb-dependency"
                                    title={dep.explanation || undefined}
                                    onClick={() => jumpToBlock(dep.sourceBlockId)}
                                  >
                                    {t('🔗 需要先会：{0} · {1}', { 0: dep.sourceBlockCode, 1: dep.fromAtomName })}
                                    {dep.role ? `（${dep.role}）` : ''} →
                                  </button>
                                ))}

                                <div className="kb-pointgroup" data-step-group={step.stepIndex}>
                                  {step.atoms.map(item => (
                                    <div
                                      key={item.atom.id}
                                      data-point={item.atom.code}
                                      title={item.tooltip}
                                      className={`kb-point${item.membership === 'extension' ? ' ext' : ''}${progress?.weak_atom_ids.includes(item.atom.id) ? ' kb-point--weak' : ''}`}
                                    >
                                      <div>{item.atom.name}</div>
                                      <span className="kb-badges">{renderTopicBadges([item.atom.name])}</span>
                                      {progress?.weak_atom_ids.includes(item.atom.id) ? <span className="kb-badge kb-badge--weak">{t('待强化')}</span> : progress?.mastered_atom_ids.includes(item.atom.id) ? <span className="kb-badge kb-badge--mastered">{t('已掌握')}</span> : null}
                                      {item.isInterfacePoint ? <b>{t('◆ 跨块接口点')}</b> : null}
                                    </div>
                                  ))}
                                </div>
                              </div>
                            ))}
                          </div>

                          <div className="kb-summary">
                            <strong>{t('本块回答主线串联')}</strong>
                            <p>{block.narrativeSummary || t('暂无主线串联说明')}</p>
                            <p className="kb-orphan">
                              {t('原子覆盖检查：本块共 {0} 个知识原子（必学 {1} · 拓展 {2}），分 {3} 步展开。', { 0: block.totalAtoms, 1: block.coreCount, 2: block.extensionCount, 3: block.steps.length })}
                            </p>
                          </div>
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>

      <div
        className={`kb-edge-tooltip${tooltip ? ' show' : ''}`}
        style={tooltip ? { left: `${tooltip.x}px`, top: `${tooltip.y}px` } : undefined}
        role="status"
        aria-live="polite"
      >
        {tooltip && (
          <>
            <div className="kb-tt-head">{tooltip.title}</div>
            <div>{tooltip.body}</div>
          </>
        )}
      </div>
    </div>
  );
}
