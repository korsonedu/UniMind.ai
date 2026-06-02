import React, { useState, useEffect, useRef } from 'react';
import { Maximize2, ZoomIn, ZoomOut } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTranslation } from 'react-i18next';
import type { KPNode } from './types';
import { buildStableLayout } from './useKnowledgeGraph';

const MASTERY_COLORS: Record<string, string> = {
  mastered: '#34C759',
  stable: '#0071E3',
  learning: '#FF9500',
  weak: '#FF3B30',
  unknown: '#AEAEB2',
};

export const KnowledgeGraph = ({
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
