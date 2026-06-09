import React, { useState, useEffect, useRef, useCallback } from 'react';
import { PageWrapper } from '@/components/PageWrapper';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { toast } from 'sonner';
import {
  ArrowLeft, GitMerge, Sparkles, X, ZoomIn, ZoomOut, Maximize2,
  ChevronRight, ChevronDown, Search, Plus, Trash2, Pencil,
} from 'lucide-react';
import api from '@/lib/api';
import type { KPNode, KEdge, EdgeType, EdgeSource } from './types';
import { EDGE_COLORS, EDGE_LABELS, SOURCE_LABELS } from './types';
import { EdgeCreateModal } from './EdgeCreateModal';

/* ═══════════════════════════════════════════
   SEC 树节点
   ═══════════════════════════════════════════ */
interface TreeNode { id: number; name: string; level: string; children: TreeNode[]; }

function TreeView({
  nodes, selectedSec, onSelectSec, kpEdgeCount,
}: {
  nodes: TreeNode[]; selectedSec: number | null; onSelectSec: (id: number) => void;
  kpEdgeCount: Map<number, number>;
}) {
  return (
    <div className="space-y-0.5">
      {nodes.map(n => (
        <TreeNodeView key={n.id} node={n} depth={0} selectedSec={selectedSec}
          onSelectSec={onSelectSec} kpEdgeCount={kpEdgeCount} />
      ))}
    </div>
  );
}

function TreeNodeView({
  node, depth, selectedSec, onSelectSec, kpEdgeCount,
}: {
  node: TreeNode; depth: number; selectedSec: number | null;
  onSelectSec: (id: number) => void; kpEdgeCount: Map<number, number>;
}) {
  const [open, setOpen] = useState(depth < 2);
  const hasChildren = node.children && node.children.length > 0;
  const isSec = node.level === 'sec';
  const isKp = node.level === 'kp';
  const isSelected = selectedSec === node.id;

  return (
    <div>
      <button
        onClick={() => {
          if (isSec) { onSelectSec(node.id); setOpen(true); }
          if (hasChildren && !isSec) setOpen(!open);
          if (isKp) onSelectSec(node.id);
        }}
        className={`w-full text-left flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-xs transition-colors hover:bg-gray-100
          ${isSelected ? 'bg-indigo-50 text-indigo-700 font-semibold' : 'text-gray-700'}
          ${depth === 0 ? 'font-bold text-sm' : ''}
          ${depth === 2 ? 'pl-8' : depth === 1 ? 'pl-5' : ''}`}
      >
        {hasChildren && (
          open ? <ChevronDown className="w-3 h-3 shrink-0 text-gray-300" /> : <ChevronRight className="w-3 h-3 shrink-0 text-gray-300" />
        )}
        {!hasChildren && <span className="w-3 shrink-0" />}
        <span className="truncate flex-1">{node.name}</span>
        {isKp && kpEdgeCount.has(node.id) && (
          <span className="text-[10px] text-gray-300 font-mono ml-1">{kpEdgeCount.get(node.id)}</span>
        )}
      </button>
      {open && hasChildren && (
        <div className="ml-1">
          {node.children.map(c => (
            <TreeNodeView key={c.id} node={c} depth={depth + 1}
              selectedSec={selectedSec} onSelectSec={onSelectSec} kpEdgeCount={kpEdgeCount} />
          ))}
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════
   局部图画布
   ═══════════════════════════════════════════ */
function LocalGraphCanvas({
  homeKps, neighborKps, edges, selectedKp, onSelectKp,
  onConnectStart, transform, setTransform, connecting,
}: {
  homeKps: KPNode[]; neighborKps: KPNode[]; edges: KEdge[];
  selectedKp: number | null; onSelectKp: (id: number | null) => void;
  onConnectStart: (id: number) => void; transform: { x: number; y: number; k: number };
  setTransform: React.Dispatch<React.SetStateAction<{ x: number; y: number; k: number }>>;
  connecting: boolean;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [dragging, setDragging] = useState<{ sx: number; sy: number; tx: number; ty: number } | null>(null);
  const [hoverNode, setHoverNode] = useState<number | null>(null);

  // 布局：home KPs 在左边，neighbor KPs 在右边
  const kpPos = useRef(new Map<number, { x: number; y: number; isHome: boolean }>());

  const layout = useCallback(() => {
    const map = new Map<number, { x: number; y: number; isHome: boolean }>();
    const GAP = 48;
    // home KPs 左边
    homeKps.forEach((kp, i) => {
      const col = i % 3; const row = Math.floor(i / 3);
      map.set(kp.id, { x: 120 + col * 90, y: 80 + row * GAP, isHome: true });
    });
    // neighbor KPs 右边
    neighborKps.forEach((kp, i) => {
      const col = i % 3; const row = Math.floor(i / 3);
      map.set(kp.id, { x: 420 + col * 90, y: 80 + row * GAP, isHome: false });
    });
    kpPos.current = map;
  }, [homeKps, neighborKps]);

  useEffect(() => { layout(); }, [layout]);

  const getNodeAt = (mx: number, my: number): number | null => {
    const R = 14;
    const { x: tx, y: ty, k } = transform;
    for (const [id, p] of kpPos.current) {
      const sx = p.x * k + tx, sy = p.y * k + ty;
      if ((mx - sx) ** 2 + (my - sy) ** 2 < R * R) return id;
    }
    return null;
  };

  const draw = useCallback(() => {
    const cvs = canvasRef.current; const ctr = containerRef.current;
    if (!cvs || !ctr) return;
    const ctx = cvs.getContext('2d'); if (!ctx) return;
    const { width: W, height: H } = ctr.getBoundingClientRect();
    if (W === 0 || H === 0) return;
    const dpr = window.devicePixelRatio || 1;
    cvs.width = W * dpr; cvs.height = H * dpr;
    cvs.style.width = W + 'px'; cvs.style.height = H + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    ctx.fillStyle = '#FAFBFC'; ctx.fillRect(0, 0, W, H);
    const { x: tx, y: ty, k } = transform;

    // 边（贝塞尔曲线，避免穿过中间节点）
    for (const e of edges) {
      const sp = kpPos.current.get(e.source), tp = kpPos.current.get(e.target);
      if (!sp || !tp) continue;
      const isHighlighted = selectedKp && (e.source === selectedKp || e.target === selectedKp);
      ctx.strokeStyle = EDGE_COLORS[e.edge_type] || '#94A3B8';
      ctx.lineWidth = isHighlighted ? 3 : 1.5;
      ctx.globalAlpha = isHighlighted ? 1 : (selectedKp ? 0.08 : 0.45);
      ctx.beginPath();
      const sx = sp.x * k + tx, sy = sp.y * k + ty;
      const ex = tp.x * k + tx, ey = tp.y * k + ty;
      const midX = (sx + ex) / 2;
      const midY = (sy + ey) / 2;
      // 弯曲偏移量，同侧节点弯少、跨侧节点弯多
      const sameSide = sp.isHome === tp.isHome;
      const curveOffset = sameSide ? -25 * k : (sp.isHome ? -40 * k : 40 * k);
      ctx.moveTo(sx, sy);
      ctx.quadraticCurveTo(midX, midY + curveOffset, ex, ey);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;

    // "本 SEC" 标签
    ctx.fillStyle = '#64748B';
    ctx.font = '11px system-ui';
    ctx.textAlign = 'center';
    ctx.fillText('本 SEC', 160 * k + tx, 40 * k + ty);
    ctx.fillText('关联知识点', 460 * k + tx, 40 * k + ty);

    // 分隔线
    ctx.strokeStyle = '#E2E8F0'; ctx.lineWidth = 1; ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(350 * k + tx, 20 * k + ty);
    ctx.lineTo(350 * k + tx, (80 + Math.max(homeKps.length, neighborKps.length) * 48) * k + ty);
    ctx.stroke();
    ctx.setLineDash([]);

    // 节点
    for (const [id, p] of kpPos.current) {
      const cx = p.x * k + tx, cy = p.y * k + ty;
      const R = 13 * k;
      const isSelected = selectedKp === id;
      const isHover = hoverNode === id;

      ctx.beginPath();
      ctx.arc(cx, cy, R, 0, Math.PI * 2);
      ctx.fillStyle = isSelected ? '#4F46E5' : isHover ? '#6366F1' : p.isHome ? '#818CF8' : '#A5B4FC';
      ctx.fill();
      if (isSelected) { ctx.strokeStyle = '#FFF'; ctx.lineWidth = 2.5; ctx.stroke(); }

      // 名称
      const allKps = [...homeKps, ...neighborKps];
      const kp = allKps.find(k => k.id === id);
      if (kp) {
        ctx.fillStyle = '#1E293B';
        ctx.font = `${Math.max(9, 11 * k)}px system-ui`;
        ctx.textAlign = 'center';
        const label = kp.name.length > 8 ? kp.name.slice(0, 7) + '…' : kp.name;
        ctx.fillText(label, cx, cy + R + 14);
      }
    }
  }, [homeKps, neighborKps, edges, transform, selectedKp, hoverNode]);

  useEffect(() => { draw(); }, [draw]);
  useEffect(() => { const h = () => draw(); window.addEventListener('resize', h); return () => window.removeEventListener('resize', h); }, [draw]);

  const handleDown = (e: React.MouseEvent) => {
    const r = containerRef.current?.getBoundingClientRect(); if (!r) return;
    const mx = e.clientX - r.left, my = e.clientY - r.top;
    const nid = getNodeAt(mx, my);
    if (nid) {
      if (connecting) { onConnectStart(nid); return; }
      onSelectKp(nid === selectedKp ? null : nid);
      return;
    }
    setDragging({ sx: e.clientX, sy: e.clientY, tx: transform.x, ty: transform.y });
  };
  const handleMove = (e: React.MouseEvent) => {
    const r = containerRef.current?.getBoundingClientRect(); if (!r) return;
    if (dragging) {
      setTransform(p => ({ ...p, x: dragging.tx + (e.clientX - dragging.sx) / p.k, y: dragging.ty + (e.clientY - dragging.sy) / p.k }));
      return;
    }
    setHoverNode(getNodeAt(e.clientX - r.left, e.clientY - r.top));
  };
  const handleUp = () => setDragging(null);
  const handleWheel = (e: React.WheelEvent) => { e.preventDefault(); setTransform(p => ({ ...p, k: Math.max(0.3, Math.min(3, p.k * (e.deltaY > 0 ? 0.9 : 1.1))) })); };

  return (
    <div ref={containerRef} className="flex-1 relative cursor-grab active:cursor-grabbing min-h-0"
      onMouseDown={handleDown} onMouseMove={handleMove} onMouseUp={handleUp} onWheel={handleWheel}>
      <canvas ref={canvasRef} className="w-full h-full" />
    </div>
  );
}

/* ═══════════════════════════════════════════
   边详情面板
   ═══════════════════════════════════════════ */
function EdgeDetailPanel({
  kp, edges, onDeleteEdge, onUpdateEdge, onCreateEdge,
}: {
  kp: KPNode | null; edges: KEdge[];
  onDeleteEdge: (id: number) => void; onUpdateEdge: (id: number, w: number) => void; onCreateEdge: () => void;
}) {
  if (!kp) {
    return (
      <div className="w-72 border-l bg-white p-6 flex items-center justify-center text-gray-300 text-sm">
        选择知识点查看关联
      </div>
    );
  }

  const kpEdges = edges.filter(e => e.source === kp.id || e.target === kp.id);

  return (
    <div className="w-72 border-l bg-white flex flex-col shrink-0">
      <div className="px-4 py-3 border-b bg-gray-50/50">
        <div className="text-sm font-bold text-gray-800 truncate">{kp.name}</div>
        <div className="text-[10px] text-gray-400 mt-0.5">{kp.code || kp.subject}</div>
      </div>
      <ScrollArea className="flex-1">
        <div className="p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-gray-400 uppercase">关联 ({kpEdges.length})</span>
            <Button variant="ghost" size="sm" className="h-6 text-xs" onClick={onCreateEdge}>
              <Plus className="w-3 h-3 mr-1" />添加
            </Button>
          </div>
          {kpEdges.length === 0 ? (
            <div className="text-xs text-gray-300 py-4 text-center">暂无关联边</div>
          ) : (
            kpEdges.map(e => {
              const isSource = e.source === kp.id;
              const otherName = isSource ? e.target_name : e.source_name;
              return (
                <div key={e.id} className="bg-gray-50 rounded-lg p-2.5 text-xs space-y-1">
                  <div className="flex items-center gap-1.5">
                    <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: EDGE_COLORS[e.edge_type] || '#999' }} />
                    <span className="font-semibold">{EDGE_LABELS[e.edge_type]}</span>
                    <span className="text-gray-300">→</span>
                    <span className="truncate">{otherName}</span>
                  </div>
                  <div className="flex items-center gap-2 text-[10px] text-gray-400">
                    <span>权重 {e.weight.toFixed(2)}</span>
                    <span>·</span>
                    <span>{SOURCE_LABELS[e.source_type]}</span>
                  </div>
                  <div className="flex gap-1 pt-1">
                    {e.source_type !== 'tree' && (
                      <Button variant="ghost" size="sm" className="h-5 text-[10px] text-red-400 hover:text-red-600 px-1.5"
                        onClick={() => onDeleteEdge(e.id)}>
                        <Trash2 className="w-2.5 h-2.5 mr-0.5" />删除
                      </Button>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

/* ═══════════════════════════════════════════
   主页面
   ═══════════════════════════════════════════ */
export const KnowledgeGraphEditor: React.FC = () => {
  const [subject] = useState('CFA');
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [nodes, setNodes] = useState<KPNode[]>([]);
  const [edges, setEdges] = useState<KEdge[]>([]);
  const [loading, setLoading] = useState(true);

  const [selectedSec, setSelectedSec] = useState<number | null>(null);
  const [selectedKp, setSelectedKp] = useState<number | null>(null);
  const [kpEdgeCount, setKpEdgeCount] = useState<Map<number, number>>(new Map());

  const [connecting, setConnecting] = useState<{ source: number } | null>(null);
  const [connectSource, setConnectSource] = useState<number | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [pendingTarget, setPendingTarget] = useState<number | null>(null);
  const [transform, setTransform] = useState({ x: 0, y: 0, k: 1 });

  // ── 数据 ──
  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [kpRes, edgeRes] = await Promise.all([
        api.get('/quizzes/knowledge-points/', { params: { subject } }).catch(() => ({ data: [] })),
        api.get('/quizzes/knowledge-edges/', { params: { subject } }).catch(() => ({ data: [] })),
      ]);
      setTree(kpRes.data || []);
      const flat: KPNode[] = [];
      const walk = (items: any[]) => { for (const i of items) { if (i.level === 'kp') flat.push(i); if (i.children) walk(i.children); } };
      walk(kpRes.data || []);
      setNodes(flat);
      const edgeList = edgeRes.data || [];
      setEdges(edgeList);

      // 统计各 KP 边数
      const counts = new Map<number, number>();
      for (const e of edgeList) {
        counts.set(e.source, (counts.get(e.source) || 0) + 1);
        counts.set(e.target, (counts.get(e.target) || 0) + 1);
      }
      setKpEdgeCount(counts);

      // 默认选中第一个 SEC
      const firstSec = (kpRes.data || [])[0]?.children?.[0]?.id || null;
      if (!selectedSec) setSelectedSec(firstSec);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, [subject]);

  useEffect(() => { loadData(); }, []);

  // ── 计算当前视图节点 ──
  const homeKps = nodes.filter(n => n.parent === selectedSec);
  const neighborIds = new Set<number>();
  for (const e of edges) {
    const isHomeSource = homeKps.some(k => k.id === e.source);
    const isHomeTarget = homeKps.some(k => k.id === e.target);
    if (isHomeSource && !isHomeTarget) neighborIds.add(e.target);
    if (isHomeTarget && !isHomeSource) neighborIds.add(e.source);
  }
  const neighborKps = nodes.filter(n => neighborIds.has(n.id) && n.parent !== selectedSec);

  // 画布上要显示的边：home KPs 之间的所有边 + home KPs 与 neighbor KPs 之间的边
  const homeIds = new Set(homeKps.map(k => k.id));
  const allRelevantIds = new Set([...homeIds, ...neighborIds]);
  const graphEdges = edges.filter(e => allRelevantIds.has(e.source) && allRelevantIds.has(e.target));

  // ── 边操作 ──
  const createEdge = async (source: number, target: number, type: EdgeType, weight: number) => {
    const tempId = -Date.now();
    const tempEdge: KEdge = {
      id: tempId, source, target, edge_type: type, weight, source_type: 'manual', is_active: true,
      source_name: nodes.find(n => n.id === source)?.name || '',
      source_code: nodes.find(n => n.id === source)?.code || '',
      target_name: nodes.find(n => n.id === target)?.name || '',
      target_code: nodes.find(n => n.id === target)?.code || '',
      institution: null, created_at: new Date().toISOString(),
    };
    setEdges(prev => [...prev, tempEdge]);

    try {
      const res = await api.post('/quizzes/knowledge-edges/bulk/', { edges: [{ source, target, edge_type: type, weight }] });
      toast.success(`边已创建 · ${res.data.created || 1} 条`);
      // 等 DB commit 后再同步，避免覆盖乐观更新
      setTimeout(() => loadData(), 500);
    } catch (e: any) {
      setEdges(prev => prev.filter(e => e.id !== tempId));
      const msg = e?.response?.data?.detail || e?.response?.statusText || e?.message || '未知错误';
      toast.error(`创建失败: ${msg}`);
    }
  };

  const deleteEdge = async (id: number) => {
    // 乐观删除
    const removed = edges.find(e => e.id === id);
    setEdges(prev => prev.filter(e => e.id !== id));
    try {
      await api.delete(`/quizzes/knowledge-edges/${id}/`);
      toast.success('边已删除');
      loadData();  // 后台同步
    } catch {
      // 回滚
      if (removed) setEdges(prev => [...prev, removed]);
      toast.error('删除失败');
    }
  };

  const updateEdge = async (id: number, weight: number) => {
    try { await api.patch(`/quizzes/knowledge-edges/${id}/`, { weight }); loadData(); } catch { toast.error('更新失败'); }
  };

  const handleConnectStart = (kpId: number) => {
    if (connecting) {
      // 连线模式：这是目标节点
      setConnectSource(connecting.source);
      setPendingTarget(kpId);
      setShowCreateModal(true);
      setConnecting(null);
    } else {
      // 进入连线模式：这是源节点
      setConnecting({ source: kpId });
      setSelectedKp(kpId);
      toast.info('点击目标节点完成连线');
    }
  };

  const selectedNode = nodes.find(n => n.id === selectedKp) || null;

  return (
    <PageWrapper>
      <div className="flex flex-col h-[calc(100vh-4rem)]">
        {/* 工具栏 */}
        <div className="flex items-center gap-3 px-4 py-3 border-b bg-white/80 shrink-0">
          <Button variant="ghost" size="sm" onClick={() => window.history.back()}><ArrowLeft className="w-4 h-4 mr-1" />返回</Button>
          <div className="h-5 w-px bg-gray-200" />
          <GitMerge className="w-4 h-4 text-indigo-400" />
          <span className="font-semibold text-sm">知识图谱编辑器</span>
          <Badge variant="secondary" className="ml-2">{subject}</Badge>
          <div className="flex-1" />
          <span className="text-xs text-gray-400">{nodes.length} 节点 · {edges.length} 边</span>
          {connecting && (
            <Badge className="bg-amber-50 text-amber-700 border-amber-200 text-xs">
              连线中 — 点击目标
              <Button variant="ghost" size="icon" className="h-4 w-4 ml-1" onClick={() => setConnecting(null)}><X className="w-2.5 h-2.5" /></Button>
            </Badge>
          )}
          <Button variant="outline" size="sm" onClick={() => {}}>
            <Sparkles className="w-3.5 h-3.5 mr-1.5" />LLM 分析
          </Button>
          <div className="flex items-center gap-0.5 bg-gray-100 rounded-lg p-0.5">
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setTransform(p => ({ ...p, k: Math.max(0.15, p.k / 1.3) }))}><ZoomOut className="w-3.5 h-3.5" /></Button>
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setTransform(p => ({ ...p, k: Math.min(3, p.k * 1.3) }))}><ZoomIn className="w-3.5 h-3.5" /></Button>
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setTransform({ x: 0, y: 0, k: 1 })}><Maximize2 className="w-3.5 h-3.5" /></Button>
          </div>
        </div>

        {/* 三栏主体 */}
        <div className="flex flex-1 overflow-hidden min-h-0">
          {/* 左：SEC 树 */}
          <div className="w-56 border-r bg-white flex flex-col shrink-0">
            <div className="px-3 py-2 border-b">
              <div className="relative">
                <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-gray-300" />
                <input className="w-full pl-7 pr-2 py-1.5 text-xs border rounded-lg bg-gray-50 outline-none focus:ring-1 focus:ring-indigo-200"
                  placeholder="搜索知识点..." />
              </div>
            </div>
            <ScrollArea className="flex-1 p-2">
              {loading ? (
                <div className="p-4 text-xs text-gray-400 animate-pulse">加载中...</div>
              ) : (
                <TreeView nodes={tree} selectedSec={selectedSec} onSelectSec={setSelectedSec} kpEdgeCount={kpEdgeCount} />
              )}
            </ScrollArea>
          </div>

          {/* 中：局部图 */}
          <div className="flex-1 min-w-0">
            {homeKps.length === 0 ? (
              <div className="flex items-center justify-center h-full text-gray-300 text-sm">
                点击左侧 SEC 查看局部知识图谱
              </div>
            ) : (
              <LocalGraphCanvas
                homeKps={homeKps} neighborKps={neighborKps} edges={graphEdges}
                selectedKp={selectedKp} onSelectKp={setSelectedKp}
                onConnectStart={handleConnectStart}
                transform={transform} setTransform={setTransform}
                connecting={connecting !== null}
              />
            )}
          </div>

          {/* 右：边详情 */}
          <EdgeDetailPanel
            kp={selectedNode} edges={edges}
            onDeleteEdge={deleteEdge} onUpdateEdge={updateEdge}
            onCreateEdge={() => { if (selectedKp) { setConnecting({ source: selectedKp }); toast.info('在画布上点击目标节点'); } }}
          />
        </div>
      </div>

      {showCreateModal && pendingTarget !== null && connectSource !== null && (
        <EdgeCreateModal
          sourceName={nodes.find(n => n.id === connectSource)?.name || ''}
          targetName={nodes.find(n => n.id === pendingTarget)?.name || ''}
          onCreate={(type, weight) => { createEdge(connectSource, pendingTarget, type, weight); setShowCreateModal(false); setPendingTarget(null); setConnectSource(null); }}
          onClose={() => { setShowCreateModal(false); setPendingTarget(null); setConnectSource(null); }}
        />
      )}
    </PageWrapper>
  );
};

export default KnowledgeGraphEditor;
