import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { PageWrapper } from '@/components/PageWrapper';
import {
  Target, Maximize2, ZoomIn, ZoomOut, GitMerge,
  ChevronRight, ChevronDown, BookOpen, FileText, Video,
  Search, X, Layers, List,
} from 'lucide-react';
import api from '@/lib/api';
import { processMathContent, cn } from '@/lib/utils';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

// Modularized Components
import { KnowledgeTrainingDialog } from './knowledge-map/TrainingDialog';
import { useTranslation } from 'react-i18next';

/* ────────────────────────────────────────────
   Types & Constants
   ──────────────────────────────────────────── */

export interface KPNode {
  id: number;
  name: string;
  description: string;
  parent: number | null;
  level: string;
  order?: number;
  questions_count?: number;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
}

const LEVEL_ORDER: Record<string, number> = { sub: 0, ch: 1, sec: 2, kp: 3 };
const LEVEL_COLORS: Record<string, string> = {
  sub: 'text-indigo-700 bg-indigo-50 border-indigo-200',
  ch: 'text-blue-700 bg-blue-50 border-blue-200',
  sec: 'text-sky-700 bg-sky-50 border-sky-200',
  kp: 'text-emerald-700 bg-emerald-50 border-emerald-200',
};

const sortNodes = (a: KPNode, b: KPNode) =>
  (LEVEL_ORDER[a.level] ?? 99) - (LEVEL_ORDER[b.level] ?? 99) || a.name.localeCompare(b.name);

/* ────────────────────────────────────────────
   Stable Tree Layout (for graph viz)
   ──────────────────────────────────────────── */

const buildStableLayout = (nodes: KPNode[]) => {
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const childrenMap = new Map<number, KPNode[]>();
  const roots: KPNode[] = [];

  for (const node of nodes) {
    if (node.parent && nodeMap.has(node.parent)) {
      const bucket = childrenMap.get(node.parent) || [];
      bucket.push(node);
      childrenMap.set(node.parent, bucket);
    } else {
      roots.push(node);
    }
  }

  for (const children of childrenMap.values()) children.sort(sortNodes);
  roots.sort(sortNodes);

  const rootCount = Math.max(roots.length, 1);
  const sectorWidth = (Math.PI * 2) / rootCount;
  const rootRadius = rootCount > 1 ? 260 : 0;
  const depthSpacing = 140;
  const positions = new Map<number, { x: number; y: number }>();

  const collectDescendants = (nodeId: number, acc: KPNode[]) => {
    const children = childrenMap.get(nodeId) || [];
    for (const child of children) {
      acc.push(child);
      collectDescendants(child.id, acc);
    }
  };

  const getDepthFromRoot = (node: KPNode, rootId: number) => {
    let depth = 0;
    let current: KPNode | undefined = node;
    while (current && current.id !== rootId) {
      depth += 1;
      current = current.parent ? nodeMap.get(current.parent) : undefined;
      if (!current) break;
    }
    return depth;
  };

  roots.forEach((root, idx) => {
    const sectorStart = -Math.PI / 2 + idx * sectorWidth;
    const sectorEnd = sectorStart + sectorWidth;
    const sectorCenter = (sectorStart + sectorEnd) / 2;

    positions.set(root.id, {
      x: Math.cos(sectorCenter) * rootRadius,
      y: Math.sin(sectorCenter) * rootRadius,
    });

    const descendants: KPNode[] = [];
    collectDescendants(root.id, descendants);
    if (!descendants.length) return;

    descendants.forEach((node, order) => {
      const t = (order + 1) / (descendants.length + 1);
      const angle = sectorStart + t * (sectorEnd - sectorStart);
      const depth = getDepthFromRoot(node, root.id);
      const radius = rootRadius + depth * depthSpacing;
      positions.set(node.id, {
        x: Math.cos(angle) * radius,
        y: Math.sin(angle) * radius,
      });
    });
  });

  return positions;
};

/* ────────────────────────────────────────────
   Knowledge Graph Canvas
   ──────────────────────────────────────────── */

const KnowledgeGraph = ({
  nodes,
  selectedId,
  onNodeClick,
  masteryData = {},
}: {
  nodes: KPNode[];
  selectedId: number | null;
  onNodeClick: (node: KPNode) => void;
  masteryData?: Record<string, string>;
}) => {
  const { t } = useTranslation('knowledgeMap');

  const MASTERY_COLORS: Record<string, string> = {
    mastered: '#34C759',
    stable: '#0071E3',
    learning: '#FF9500',
    weak: '#FF3B30',
    unknown: '#AEAEB2',
  };
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [canvasSize, setCanvasSize] = useState({ w: 1000, h: 600 });
  const [transform, setTransform] = useState({ x: 0, y: 0, k: 1 });
  const [isDark, setIsDark] = useState(
    () => typeof document !== 'undefined' && document.documentElement.classList.contains('dark')
  );
  const nodesRef = useRef<KPNode[]>([]);
  const targetRef = useRef<Map<number, { x: number; y: number }>>(new Map());
  const requestRef = useRef<number | null>(null);

  useEffect(() => {
    const existingNodes = new Map(nodesRef.current.map(n => [n.id, n]));
    const layout = buildStableLayout(nodes);
    targetRef.current = layout;

    nodesRef.current = nodes.map(n => {
      const existing = existingNodes.get(n.id);
      const target = layout.get(n.id) || { x: 0, y: 0 };
      return {
        ...n,
        x: existing?.x ?? target.x,
        y: existing?.y ?? target.y,
        vx: 0,
        vy: 0,
      };
    });
    setTransform({ x: 0, y: 0, k: 1 });
  }, [nodes]);

  useEffect(() => {
    if (typeof document === 'undefined') return;
    const sync = () => setIsDark(document.documentElement.classList.contains('dark'));
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const dpr = window.devicePixelRatio || 1;
    const ro = new ResizeObserver(entries => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        setCanvasSize({ w: Math.round(width * dpr), h: Math.round(height * dpr) });
      }
    });
    ro.observe(container);
    return () => ro.disconnect();
  }, []);

  const animate = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const currentNodes = nodesRef.current;
    const nodeMap = new Map(currentNodes.map(n => [n.id, n]));
    let moving = false;
    for (const node of currentNodes) {
      const target = targetRef.current.get(node.id);
      if (!target) continue;
      const dx = target.x - (node.x || 0);
      const dy = target.y - (node.y || 0);
      node.x = (node.x || 0) + dx * 0.15;
      node.y = (node.y || 0) + dy * 0.15;
      if (Math.abs(dx) > 0.4 || Math.abs(dy) > 0.4) moving = true;
    }

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.save();
    ctx.translate(canvas.width / 2 + transform.x, canvas.height / 2 + transform.y);
    ctx.scale(transform.k, transform.k);

    // Edges
    ctx.beginPath();
    ctx.strokeStyle = isDark ? 'rgba(148, 163, 184, 0.45)' : 'rgba(148, 163, 184, 0.28)';
    ctx.lineWidth = 1.2 / transform.k;
    const hideDenseKpEdges = currentNodes.length > 180 && transform.k < 1.05;
    for (const node of currentNodes) {
      if (node.parent) {
        if (hideDenseKpEdges && node.level === 'kp') continue;
        const parentNode = nodeMap.get(node.parent);
        if (parentNode) {
          ctx.moveTo(parentNode.x!, parentNode.y!);
          ctx.lineTo(node.x!, node.y!);
        }
      }
    }
    ctx.stroke();

    // Nodes
    for (const node of currentNodes) {
      const isSelected = node.id === selectedId;
      const radius =
        node.level === 'sub' ? 20
        : node.level === 'ch' ? 14
        : node.level === 'sec' ? 10
        : 6 + Math.sqrt(node.questions_count || 0) * 1.5;

      ctx.beginPath();
      ctx.arc(node.x!, node.y!, radius, 0, Math.PI * 2);

      const kpMastery = node.level === 'kp' ? masteryData[String(node.id)] : undefined;

      if (isSelected) {
        ctx.fillStyle = '#f59e0b';
      } else if (kpMastery && MASTERY_COLORS[kpMastery]) {
        ctx.fillStyle = MASTERY_COLORS[kpMastery];
      } else {
        ctx.fillStyle =
          node.level === 'sub' ? (isDark ? '#6366f1' : '#1e1b4b')
          : node.level === 'ch' ? (isDark ? '#818cf8' : '#4338ca')
          : node.level === 'sec' ? (isDark ? '#a5b4fc' : '#818cf8')
          : (isDark ? '#1f2937' : '#ffffff');
      }
      ctx.fill();

      if (node.level === 'kp') {
        const mc = kpMastery ? MASTERY_COLORS[kpMastery] : undefined;
        ctx.strokeStyle = isSelected ? '#f59e0b' : mc || (isDark ? '#64748b' : '#94a3b8');
        ctx.lineWidth = isSelected ? 3 / transform.k : 1.2 / transform.k;
        ctx.stroke();
      }

      if (node.level !== 'kp' || transform.k > 1.15) {
        ctx.fillStyle =
          node.level === 'kp' ? (isDark ? '#cbd5e1' : '#475569')
          : (isDark ? '#e2e8f0' : '#1e293b');
        const fontSize = node.level === 'kp' ? 11 : node.level === 'sub' ? 15 : 14;
        ctx.font = `${node.level === 'kp' ? 'normal' : 'bold'} ${fontSize}px sans-serif`;
        ctx.textAlign = "center";
        ctx.fillText(node.name, node.x!, node.y! + radius + fontSize);
      }
    }
    ctx.restore();
    if (moving) requestRef.current = requestAnimationFrame(animate);
    else requestRef.current = null;
  };

  useEffect(() => {
    requestRef.current = requestAnimationFrame(animate);
    return () => {
      if (requestRef.current) cancelAnimationFrame(requestRef.current);
    };
  }, [nodes, transform, isDark, selectedId, canvasSize]);

  const handleWheel = (e: React.WheelEvent) => {
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    setTransform(prev => ({ ...prev, k: Math.max(0.1, Math.min(5, prev.k * delta)) }));
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    const startX = e.clientX - transform.x;
    const startY = e.clientY - transform.y;
    const handleMouseMove = (mv: MouseEvent) =>
      setTransform(prev => ({ ...prev, x: mv.clientX - startX, y: mv.clientY - startY }));
    const handleMouseUp = () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  };

  const handleClick = (e: React.MouseEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = (e.clientX - rect.left - canvas.width / 2 - transform.x) / transform.k;
    const my = (e.clientY - rect.top - canvas.height / 2 - transform.y) / transform.k;
    for (const n of nodesRef.current) {
      if (Math.sqrt((n.x! - mx) ** 2 + (n.y! - my) ** 2) < (n.level === 'kp' ? 12 : 20)) {
        onNodeClick(n);
        break;
      }
    }
  };

  return (
    <div ref={containerRef} className="relative w-full h-full bg-muted/30 rounded-2xl border border-border/50 overflow-hidden cursor-move shadow-inner">
      <canvas
        ref={canvasRef}
        width={canvasSize.w}
        height={canvasSize.h}
        className="w-full h-full"
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onClick={handleClick}
      />
      <div className="absolute bottom-4 left-4 flex flex-col gap-1.5">
        <Button variant="secondary" size="icon" className="h-8 w-8 rounded-xl shadow-lg" onClick={() => setTransform(p => ({ ...p, k: p.k * 1.2 }))}>
          <ZoomIn className="h-3.5 w-3.5" />
        </Button>
        <Button variant="secondary" size="icon" className="h-8 w-8 rounded-xl shadow-lg" onClick={() => setTransform(p => ({ ...p, k: p.k * 0.8 }))}>
          <ZoomOut className="h-3.5 w-3.5" />
        </Button>
        <Button variant="secondary" size="icon" className="h-8 w-8 rounded-xl shadow-lg" onClick={() => setTransform({ x: 0, y: 0, k: 1 })}>
          <Maximize2 className="h-3.5 w-3.5" />
        </Button>
      </div>

      {/* Mastery legend */}
      {Object.keys(masteryData).length > 0 && (
        <div className="absolute bottom-4 right-4 flex items-center gap-1.5 px-3 py-1.5 bg-white/90 backdrop-blur-md rounded-xl border border-border/50 shadow-sm">
          {Object.entries(MASTERY_COLORS).map(([level, color]) => (
            <div key={level} className="flex items-center gap-1" title={level}>
              <span className="h-2.5 w-2.5 rounded-full border border-white/50" style={{ backgroundColor: color }} />
              <span className="text-[9px] font-bold text-muted-foreground uppercase">{level === 'mastered' ? t('graph.legendMastered') : level === 'stable' ? t('graph.legendStable') : level === 'learning' ? t('graph.legendLearning') : level === 'weak' ? t('graph.legendWeak') : t('graph.legendUnknown')}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

/* ────────────────────────────────────────────
   Tree Panel (Left Sidebar)
   ──────────────────────────────────────────── */

interface TreeNodeData extends KPNode {
  children: TreeNodeData[];
}

const MASTERY_DOT_COLORS: Record<string, string> = {
  mastered: '#34C759',
  stable: '#0071E3',
  learning: '#FF9500',
  weak: '#FF3B30',
  unknown: '#AEAEB2',
};

const KnowledgeTreePanel: React.FC<{
  nodes: KPNode[];
  selectedId: number | null;
  onSelect: (node: KPNode) => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  masteryData?: Record<string, string>;
}> = ({ nodes, selectedId, onSelect, searchQuery, onSearchChange, masteryData = {} }) => {
  const { t } = useTranslation('knowledgeMap');
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  const tree = useMemo(() => {
    const nodeMap = new Map<number, TreeNodeData>();
    const roots: TreeNodeData[] = [];

    for (const n of nodes) {
      nodeMap.set(n.id, { ...n, children: [] });
    }
    for (const n of nodes) {
      const tn = nodeMap.get(n.id)!;
      if (n.parent && nodeMap.has(n.parent)) {
        nodeMap.get(n.parent)!.children.push(tn);
      } else {
        roots.push(tn);
      }
    }
    const sortTree = (list: TreeNodeData[]) => {
      list.sort((a, b) => (LEVEL_ORDER[a.level ?? ''] ?? 99) - (LEVEL_ORDER[b.level ?? ''] ?? 99) || (a.order ?? 0) - (b.order ?? 0) || a.name.localeCompare(b.name));
      list.forEach(t => sortTree(t.children));
    };
    sortTree(roots);
    return roots;
  }, [nodes]);

  // Auto-expand to show selected node (moved from useMemo to avoid setState during render)
  useEffect(() => {
    if (!selectedId) return;
    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    if (!nodeMap.has(selectedId)) return;
    const path: number[] = [];
    let cur: KPNode | undefined = nodeMap.get(selectedId);
    while (cur) {
      path.push(cur.id);
      cur = cur.parent ? nodeMap.get(cur.parent) : undefined;
    }
    setExpandedIds(prev => {
      const next = new Set(prev);
      path.forEach(id => next.add(id));
      return next;
    });
  }, [selectedId, nodes]);

  const toggleExpand = (id: number) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const filteredTree = useMemo(() => {
    if (!searchQuery.trim()) return tree;
    const q = searchQuery.toLowerCase();
    const matchSet = new Set<number>();
    // Mark all nodes that match
    for (const n of nodes) {
      if (n.name.toLowerCase().includes(q)) matchSet.add(n.id);
    }
    // Also keep ancestors of matches
    const keepSet = new Set<number>(matchSet);
    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    for (const id of matchSet) {
      let cur = nodeMap.get(id);
      while (cur?.parent) {
        keepSet.add(cur.parent);
        cur = nodeMap.get(cur.parent);
      }
    }
    const filterNodes = (list: TreeNodeData[]): TreeNodeData[] =>
      list.filter(t => keepSet.has(t.id)).map(t => ({ ...t, children: filterNodes(t.children) }));
    return filterNodes(tree);
  }, [tree, searchQuery, nodes]);

  const renderNode = (tn: TreeNodeData, depth: number) => {
    const hasChildren = tn.children.length > 0;
    const isExpanded = expandedIds.has(tn.id);
    const isSelected = tn.id === selectedId;
    const isKp = tn.level === 'kp';

    return (
      <div key={tn.id} style={{ contentVisibility: 'auto', containIntrinsicSize: 'auto 36px' }}>
        <button
          onClick={() => {
            if (hasChildren) toggleExpand(tn.id);
            if (isKp) onSelect(tn);
          }}
          className={cn(
            'w-full flex items-center gap-1.5 py-1.5 pr-2 rounded-lg text-left transition-colors group',
            isSelected && 'bg-amber-50 border border-amber-200',
            !isSelected && 'hover:bg-muted/50',
          )}
          style={{ paddingLeft: `${depth * 16 + 8}px` }}
        >
          {/* expand toggle for non-kp nodes */}
          {hasChildren ? (
            isExpanded ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
            : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
          ) : (
            <span className="w-3.5 shrink-0" />
          )}

          {/* mastery dot */}
          {isKp && (
            <span
              className="h-2.5 w-2.5 rounded-full shrink-0 border border-white/50 shadow-sm"
              style={{ backgroundColor: MASTERY_DOT_COLORS[masteryData[String(tn.id)]] || MASTERY_DOT_COLORS.unknown }}
            />
          )}

          {/* level badge */}
          <Badge
            variant="outline"
            className={cn(
              'text-[9px] py-0 h-4 px-1.5 font-bold uppercase shrink-0',
              LEVEL_COLORS[tn.level] || 'bg-muted',
            )}
          >
            {t(`levels.${tn.level}` as any) || tn.level}
          </Badge>

          {/* name */}
          <span
            className={cn(
              'text-xs font-bold truncate flex-1',
              isSelected && 'text-amber-700',
              isKp && 'cursor-pointer',
            )}
          >
            {tn.name}
          </span>

          {/* question count */}
          {tn.questions_count !== undefined && tn.questions_count > 0 && (
            <Badge variant="secondary" className="text-[9px] rounded-full px-1.5 py-0 h-4 bg-indigo-50 text-indigo-500 border-none font-bold shrink-0">
              {tn.questions_count}
            </Badge>
          )}
        </button>

        {/* children */}
        {hasChildren && isExpanded && (
          <div>{tn.children.map(child => renderNode(child, depth + 1))}</div>
        )}
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full bg-card rounded-2xl border border-border/50 overflow-hidden">
      <div className="p-3 border-b border-border/30">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            placeholder={t('treePanel.searchPlaceholder')}
            value={searchQuery}
            onChange={e => onSearchChange(e.target.value)}
            className="h-9 pl-9 pr-8 rounded-xl bg-muted/50 border-none text-xs font-medium"
          />
          {searchQuery && (
            <button
              onClick={() => onSearchChange('')}
              className="absolute right-2 top-1/2 -translate-y-1/2"
            >
              <X className="h-3 w-3 text-muted-foreground" />
            </button>
          )}
        </div>
      </div>
      {/* Mastery legend */}
      <div className="px-3 py-2 border-t border-border/30 flex items-center gap-3 flex-wrap">
        {[
          { level: 'mastered', label: t('treePanel.legendMastered'), color: MASTERY_DOT_COLORS.mastered },
          { level: 'stable', label: t('treePanel.legendStable'), color: MASTERY_DOT_COLORS.stable },
          { level: 'learning', label: t('treePanel.legendLearning'), color: MASTERY_DOT_COLORS.learning },
          { level: 'weak', label: t('treePanel.legendWeak'), color: MASTERY_DOT_COLORS.weak },
        ].map(item => (
          <div key={item.level} className="flex items-center gap-1.5">
            <span
              className="h-2.5 w-2.5 rounded-full shrink-0 border border-white/50 shadow-sm"
              style={{ backgroundColor: item.color }}
            />
            <span className="text-[10px] font-bold text-muted-foreground">{item.label}</span>
          </div>
        ))}
      </div>
      <ScrollArea className="flex-1 p-2" type="always">
        <div className="space-y-0.5 min-w-max">
          {filteredTree.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-8">{t('treePanel.noMatch')}</p>
          ) : (
            filteredTree.map(root => renderNode(root, 0))
          )}
        </div>
        <ScrollBar orientation="horizontal" />
      </ScrollArea>
    </div>
  );
};

/* ────────────────────────────────────────────
   Detail Panel (Right Sidebar)
   ──────────────────────────────────────────── */

const NodeDetailPanel: React.FC<{
  node: KPNode | null;
  details: { courses: any[]; articles: any[]; questions: any[] };
  loading: boolean;
  onQuestionClick: (q: any) => void;
  onClear: () => void;
  masteryData?: Record<string, string>;
}> = ({ node, details, loading, onQuestionClick, onClear, masteryData = {} }) => {
  const { t } = useTranslation('knowledgeMap');

  const MASTERY_LABELS: Record<string, string> = {
    mastered: t('masteryLevels.mastered'), stable: t('masteryLevels.stable'), learning: t('masteryLevels.learning'), weak: t('masteryLevels.weak'), unknown: t('masteryLevels.unknown'),
  };
  const MASTERY_BG: Record<string, string> = {
    mastered: 'bg-[#34C759]', stable: 'bg-[#0071E3]', learning: 'bg-[#FF9500]', weak: 'bg-[#FF3B30]', unknown: 'bg-[#AEAEB2]',
  };
  if (!node) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground bg-card rounded-2xl border border-border/50 p-6">
        <Layers className="h-8 w-8 mb-3 opacity-20" />
        <p className="text-xs font-bold uppercase tracking-widest">{t('detailPanel.selectTitle')}</p>
        <p className="text-[10px] mt-1 opacity-50">{t('detailPanel.selectHint')}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-card rounded-2xl border border-border/50 overflow-hidden">
      {/* header */}
      <div className="p-4 border-b border-border/30 flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <Badge className={cn('text-[9px] py-0 h-5 px-2 font-bold uppercase border', LEVEL_COLORS[node.level] || 'bg-muted')}>
            {t(`levels.${node.level}` as any) || node.level}
          </Badge>
          <h3 className="text-sm font-bold truncate">{node.name}</h3>
          {masteryData[String(node.id)] && (
            <Badge className={cn('text-[9px] text-white py-0 h-5 px-2 font-bold', MASTERY_BG[masteryData[String(node.id)]] || 'bg-muted')}>
              {MASTERY_LABELS[masteryData[String(node.id)]] || masteryData[String(node.id)]}
            </Badge>
          )}
        </div>
        <Button variant="ghost" size="icon" className="h-7 w-7 rounded-lg shrink-0" onClick={onClear}>
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>

      {/* content */}
      <ScrollArea className="flex-1">
        <div className="p-4 space-y-5">
          {/* description */}
          {node.description && (
            <div className="text-xs text-muted-foreground leading-relaxed">
              <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                {processMathContent(node.description)}
              </ReactMarkdown>
            </div>
          )}

          {loading ? (
            <p className="text-[10px] font-bold uppercase text-muted-foreground animate-pulse text-center py-8">Loading...</p>
          ) : (
            <>
              {/* questions */}
              <section>
                <h5 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2 flex items-center gap-1.5">
                  <Target className="w-3 h-3" /> {t('detailPanel.relatedQuestions')} ({details.questions.length})
                </h5>
                <div className="space-y-1.5">
                  {details.questions.length === 0 && (
                    <p className="text-[10px] text-muted-foreground/50">{t('detailPanel.noQuestions')}</p>
                  )}
                  {details.questions.map((q: any) => (
                    <button
                      key={q.id}
                      onClick={() => onQuestionClick(q)}
                      className="w-full p-3 bg-muted/50 hover:bg-muted rounded-xl flex items-center gap-2 text-left transition-colors group"
                    >
                      <Badge variant="outline" className="text-[8px] py-0 h-4 uppercase shrink-0">{q.subjective_type || q.q_type || 'Q'}</Badge>
                      <span className="text-[11px] font-medium truncate flex-1">
                        <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                          {processMathContent(q.text)}
                        </ReactMarkdown>
                      </span>
                      <Maximize2 className="w-3 h-3 text-muted-foreground/40 opacity-0 group-hover:opacity-100 transition-all shrink-0" />
                    </button>
                  ))}
                </div>
              </section>

              {/* courses */}
              <section>
                <h5 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2 flex items-center gap-1.5">
                  <Video className="w-3 h-3" /> {t('detailPanel.courseResources')} ({details.courses.length})
                </h5>
                <div className="space-y-1.5">
                  {details.courses.length === 0 && (
                    <p className="text-[10px] text-muted-foreground/50">{t('detailPanel.noCourses')}</p>
                  )}
                  {details.courses.map((c: any) => (
                    <div key={c.id} className="p-3 bg-emerald-50/50 rounded-xl flex items-center gap-2 border border-emerald-100">
                      <Video className="w-3 h-3 text-emerald-500 shrink-0" />
                      <p className="text-[11px] font-medium truncate">{c.title}</p>
                    </div>
                  ))}
                </div>
              </section>

              {/* articles */}
              <section>
                <h5 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2 flex items-center gap-1.5">
                  <FileText className="w-3 h-3" /> {t('detailPanel.referenceArticles')} ({details.articles.length})
                </h5>
                <div className="space-y-1.5">
                  {details.articles.length === 0 && (
                    <p className="text-[10px] text-muted-foreground/50">{t('detailPanel.noArticles')}</p>
                  )}
                  {details.articles.map((a: any) => (
                    <div key={a.id} className="p-3 bg-orange-50/50 rounded-xl flex items-center gap-2 border border-orange-100">
                      <FileText className="w-3 h-3 text-orange-500 shrink-0" />
                      <p className="text-[11px] font-medium truncate">{a.title}</p>
                    </div>
                  ))}
                </div>
              </section>
            </>
          )}
        </div>
      </ScrollArea>
    </div>
  );
};

/* ────────────────────────────────────────────
   Main KnowledgeMap Page
   ──────────────────────────────────────────── */

export const KnowledgeMap: React.FC = () => {
  const navigate = useNavigate();
  const { t } = useTranslation('knowledgeMap');
  const [allNodes, setAllNodes] = useState<KPNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedNode, setSelectedNode] = useState<KPNode | null>(null);
  const [nodeDetails, setNodeDetails] = useState<{ courses: any[]; articles: any[]; questions: any[] }>({
    courses: [],
    articles: [],
    questions: [],
  });
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [treeSearch, setTreeSearch] = useState('');
  const [isMobile, setIsMobile] = useState(false);
  const [selectedQuestion, setSelectedQuestion] = useState<any>(null);
  const [viewMode, setViewMode] = useState<'graph' | 'list'>('graph');
  const [graphRootId, setGraphRootId] = useState<string>('all');
  const [masteryData, setMasteryData] = useState<Record<string, string>>({});
  const [mobileTreeOpen, setMobileTreeOpen] = useState(false);
  const [mobileVisibleCount, setMobileVisibleCount] = useState(40);
  const mobileSentinelRef = useRef<HTMLDivElement>(null);

  // Reset visible count when search changes or toggling to tree
  useEffect(() => {
    setMobileVisibleCount(40);
  }, [treeSearch, mobileTreeOpen]);

  // IntersectionObserver: load more grid items as user scrolls
  useEffect(() => {
    if (!isMobile || mobileTreeOpen) return;
    const sentinel = mobileSentinelRef.current;
    if (!sentinel) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setMobileVisibleCount(prev => Math.min(prev + 40, allNodes.length));
        }
      },
      { rootMargin: '200px' },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [isMobile, mobileTreeOpen, allNodes.length]);

  useEffect(() => {
    fetchMap();
    fetchMastery();
  }, []);

  const fetchMastery = async () => {
    try {
      const { data } = await api.get('/users/me/knowledge-mastery/');
      setMasteryData(data || {});
    } catch { /* silently fail if no mastery data */ }
  };

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const media = window.matchMedia('(max-width: 1023px)');
    const sync = () => setIsMobile(media.matches);
    sync();
    media.addEventListener('change', sync);
    return () => media.removeEventListener('change', sync);
  }, []);

  const fetchMap = async () => {
    try {
      const res = await api.get('/quizzes/knowledge-points/');
      let rawData = res.data;
      const flatNodes: KPNode[] = [];
      const flatten = (items: any[]) => {
        for (const item of items) {
          flatNodes.push({
            id: item.id,
            name: item.name,
            description: item.description,
            parent: item.parent,
            level: item.level,
            order: item.order,
            questions_count: item.questions_count,
          });
          if (item.children && item.children.length > 0) flatten(item.children);
        }
      };
      if (rawData.length > 0 && rawData[0].children !== undefined) flatten(rawData);
      else flatNodes.push(...rawData);
      flatNodes.sort((a, b) => (b.questions_count || 0) - (a.questions_count || 0) || (a.order ?? 0) - (b.order ?? 0) || a.name.localeCompare(b.name));
      setAllNodes(flatNodes);
    } catch (e) {
    } finally {
      setLoading(false);
    }
  };

  /** Find the ancestor at `targetLevel` for a given node. */
  const findAncestorAtLevel = useCallback(
    (node: KPNode, targetLevel: string): KPNode | null => {
      const nodeMap = new Map(allNodes.map(n => [n.id, n]));
      let cur: KPNode | undefined = node;
      while (cur) {
        if (cur.level === targetLevel) return cur;
        cur = cur.parent ? nodeMap.get(cur.parent) : undefined;
      }
      return null;
    },
    [allNodes],
  );

  const handleNodeSelect = useCallback(async (node: KPNode) => {
    if (isMobile) {
      navigate(`/knowledge-map/node/${node.id}`);
      return;
    }

    // Auto-focus graph on the section (小节) containing this node
    if (node.level === 'kp') {
      const sec = findAncestorAtLevel(node, 'sec');
      if (sec) setGraphRootId(sec.id.toString());
      else {
        const ch = findAncestorAtLevel(node, 'ch');
        if (ch) setGraphRootId(ch.id.toString());
        else {
          const sub = findAncestorAtLevel(node, 'sub');
          if (sub) setGraphRootId(sub.id.toString());
        }
      }
    } else if (node.level === 'sec') {
      setGraphRootId(node.id.toString());
    } else if (node.level === 'ch') {
      setGraphRootId(node.id.toString());
    } else if (node.level === 'sub') {
      setGraphRootId(node.id.toString());
    }

    setSelectedNode(node);
    setDetailsLoading(true);
    try {
      const [cRes, aRes, qRes] = await Promise.all([
        api.get('/courses/', { params: { kp: node.id } }),
        api.get('/articles/', { params: { kp: node.id } }),
        api.get('/quizzes/questions/', { params: { kp: node.id } }),
      ]);
      setNodeDetails({
        courses: cRes.data || [],
        articles: aRes.data.articles || aRes.data || [],
        questions: qRes.data || [],
      });
    } catch (e) {
    } finally {
      setDetailsLoading(false);
    }
  }, [isMobile, navigate, findAncestorAtLevel]);

  const handleClearSelection = useCallback(() => {
    setSelectedNode(null);
    setNodeDetails({ courses: [], articles: [], questions: [] });
  }, []);

  // Branch filter: subjects for the toolbar dropdown
  const rootOptions = useMemo(() => allNodes.filter(n => n.level === 'sub'), [allNodes]);

  // Filter graph nodes by selected branch
  const displayNodes = useMemo(() => {
    if (graphRootId === 'all') return allNodes;
    const rootId = parseInt(graphRootId);
    const validIds = new Set<number>([rootId]);
    let added = true;
    while (added) {
      added = false;
      for (const node of allNodes) {
        if (node.parent && validIds.has(node.parent) && !validIds.has(node.id)) {
          validIds.add(node.id);
          added = true;
        }
      }
    }
    return allNodes.filter(n => validIds.has(n.id));
  }, [allNodes, graphRootId]);

  // List-view nodes (kps only, searchable)
  const listNodes = useMemo(
    () => displayNodes.filter(n => n.level === 'kp' && n.name.toLowerCase().includes(treeSearch.toLowerCase())),
    [displayNodes, treeSearch],
  );

  if (loading) {
    return (
      <PageWrapper title={t('pageTitle')} subtitle={t('pageLoadingSubtitle')}>
        <div className="text-center opacity-20 font-bold uppercase text-[10px] animate-pulse py-32">Mapping...</div>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper title={t('pageTitle')} subtitle={t('pageSubtitle')}>
      <div className="w-full text-left animate-in fade-in duration-700">
        {isMobile ? (
          /* ── Mobile: toggle between tree panel and grid list ── */
          <div className="space-y-3">
            {/* Toggle + Search */}
            <div className="flex items-center gap-2">
              <Button
                variant={mobileTreeOpen ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => setMobileTreeOpen(!mobileTreeOpen)}
                className="rounded-xl h-9 text-xs font-bold shrink-0"
              >
                {mobileTreeOpen ? <List className="h-3.5 w-3.5 mr-1" /> : <GitMerge className="h-3.5 w-3.5 mr-1" />}
                {mobileTreeOpen ? '网格' : '知识树'}
              </Button>
              {!mobileTreeOpen && (
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder={t('mobile.searchPlaceholder')}
                    value={treeSearch}
                    onChange={e => setTreeSearch(e.target.value)}
                    className="w-full rounded-2xl bg-card border-border shadow-sm h-11 pl-10 pr-4 font-bold"
                  />
                </div>
              )}
            </div>

            {mobileTreeOpen ? (
              <div className="h-[calc(100dvh-12rem)] overflow-hidden rounded-2xl">
                <KnowledgeTreePanel
                  nodes={allNodes}
                  selectedId={selectedNode?.id ?? null}
                  onSelect={handleNodeSelect}
                  searchQuery={treeSearch}
                  onSearchChange={setTreeSearch}
                  masteryData={masteryData}
                />
              </div>
            ) : (
              <div className="h-[calc(100dvh-12rem)] overflow-y-auto overscroll-contain rounded-2xl bg-muted/50 p-2">
                <div className="grid grid-cols-2 gap-2 content-start">
                  {(() => {
                    const filtered = allNodes.filter(n => n.name.toLowerCase().includes(treeSearch.toLowerCase()));
                    const visible = filtered.slice(0, mobileVisibleCount);
                    return (
                      <>
                        {visible.map(node => (
                          <button
                            key={node.id}
                            onClick={() => handleNodeSelect(node)}
                            className="flex items-center justify-between bg-card border border-border/50 hover:border-indigo-500/30 hover:shadow-md px-2.5 py-2 rounded-xl transition-all active:scale-[0.99] text-left min-h-[58px]"
                          >
                            <span className="text-[12px] font-bold truncate pr-2 leading-snug">{node.name}</span>
                          </button>
                        ))}
                        {visible.length < filtered.length && (
                          <div ref={mobileSentinelRef} className="col-span-2 h-4" />
                        )}
                      </>
                    );
                  })()}
                </div>
              </div>
            )}
          </div>
        ) : (
          /* ── Desktop: three-panel layout ── */
          <div className="flex gap-4" style={{ height: 'calc(100vh - 7rem)' }}>
            {/* ── Left: Tree Panel ── */}
            <div className="w-[300px] shrink-0 self-stretch">
              <KnowledgeTreePanel
                nodes={allNodes}
                selectedId={selectedNode?.id ?? null}
                onSelect={handleNodeSelect}
                searchQuery={treeSearch}
                onSearchChange={setTreeSearch}
                masteryData={masteryData}
              />
            </div>

            {/* ── Center: Graph / List ── */}
            <div className="flex-1 min-w-0 flex flex-col gap-3 self-stretch">
              {/* Toolbar */}
              <div className="flex items-center gap-3 shrink-0">
                <Select value={graphRootId} onValueChange={setGraphRootId}>
                  <SelectTrigger className="w-[200px] h-10 bg-card rounded-xl font-bold border-border shadow-sm text-xs">
                    <GitMerge className="w-3.5 h-3.5 mr-2 text-indigo-500" />
                    <SelectValue placeholder={t('toolbar.allBranches')} />
                  </SelectTrigger>
                  <SelectContent className="rounded-xl">
                    <SelectItem value="all" className="font-bold text-xs">{t('toolbar.allBranches')}</SelectItem>
                    {rootOptions.map(opt => (
                      <SelectItem key={opt.id} value={opt.id.toString()} className="text-xs">
                        {opt.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                {viewMode === 'list' && (
                  <Input
                    placeholder={t('toolbar.searchKp')}
                    value={treeSearch}
                    onChange={e => setTreeSearch(e.target.value)}
                    className="flex-1 rounded-xl bg-card border-border shadow-sm h-10 px-4 font-bold text-xs"
                  />
                )}

                <div className="flex bg-muted/30 p-1 rounded-xl border border-border/50 ml-auto shrink-0">
                  <Button
                    variant={viewMode === 'graph' ? 'secondary' : 'ghost'}
                    onClick={() => setViewMode('graph')}
                    className="rounded-lg h-8 text-xs font-bold px-4"
                  >
                    <GitMerge className="w-3.5 h-3.5 mr-1.5" /> {t('toolbar.graphView')}
                  </Button>
                  <Button
                    variant={viewMode === 'list' ? 'secondary' : 'ghost'}
                    onClick={() => setViewMode('list')}
                    className="rounded-lg h-8 text-xs font-bold px-3"
                  >
                    <List className="w-3.5 h-3.5 mr-1.5" /> {t('toolbar.listView')}
                  </Button>
                </div>
              </div>

              {/* Content */}
              <div className="flex-1 min-h-0">
                {viewMode === 'graph' ? (
                  <KnowledgeGraph
                    nodes={displayNodes}
                    selectedId={selectedNode?.id ?? null}
                    onNodeClick={handleNodeSelect}
                    masteryData={masteryData}
                  />
                ) : (
                  <div className="h-full bg-muted/30 rounded-2xl border border-border/50 p-4">
                    <ScrollArea className="h-full">
                      <div className="flex flex-wrap gap-2 content-start">
                        {listNodes.map(node => (
                          <button
                            key={node.id}
                            onClick={() => handleNodeSelect(node)}
                            className={cn(
                              'flex items-center gap-2 bg-card border hover:shadow-md px-3 py-2 rounded-xl transition-all active:scale-95 text-left',
                              selectedNode?.id === node.id
                                ? 'border-amber-300 bg-amber-50'
                                : 'border-border/50 hover:border-indigo-500/30',
                            )}
                          >
                            <span className="text-xs font-bold">{node.name}</span>
                            {node.questions_count !== undefined && node.questions_count > 0 && (
                              <Badge variant="secondary" className="text-[9px] rounded-full px-1.5 py-0 h-4 bg-indigo-50 text-indigo-500 border-none font-bold">
                                {node.questions_count}
                              </Badge>
                            )}
                          </button>
                        ))}
                        {listNodes.length === 0 && (
                          <div className="w-full text-center text-xs font-bold text-muted-foreground py-20">
                            {t('toolbar.noMatch')}
                          </div>
                        )}
                      </div>
                    </ScrollArea>
                  </div>
                )}
              </div>
            </div>

            {/* ── Right: Detail Panel ── */}
            <div className="w-[320px] shrink-0 self-stretch">
              <NodeDetailPanel
                node={selectedNode}
                details={nodeDetails}
                loading={detailsLoading}
                onQuestionClick={setSelectedQuestion}
                onClear={handleClearSelection}
                masteryData={masteryData}
              />
            </div>
          </div>
        )}
      </div>

      {/* Training Dialog */}
      <KnowledgeTrainingDialog
        question={selectedQuestion}
        onClose={() => setSelectedQuestion(null)}
      />
    </PageWrapper>
  );
};
