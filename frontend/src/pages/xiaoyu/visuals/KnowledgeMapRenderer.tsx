import React, { useMemo, useState } from 'react';

interface KnowledgeNode {
  id: string;
  label: string;
  mastery?: number; // 0-1
}

interface KnowledgeEdge {
  from: string;
  to: string;
}

interface KnowledgeMapPayload {
  title?: string;
  nodes: KnowledgeNode[];
  edges: KnowledgeEdge[];
  highlights?: string[];
}

const NODE_RADIUS = 28;
const W = 560;
const H = 320;

/** Monochrome + single accent. Low mastery → darker fill. */
const nodeFill = (mastery?: number): string => {
  if (mastery === undefined) return '#f5f5f4'; // stone-100
  if (mastery >= 0.8) return '#f0fdf4'; // green-50
  if (mastery >= 0.6) return '#eff6ff'; // blue-50
  if (mastery >= 0.4) return '#fefce8'; // yellow-50
  return '#fef2f2'; // red-50
};

const nodeStroke = (mastery?: number): string => {
  if (mastery === undefined) return '#d6d3d1'; // stone-300
  if (mastery >= 0.8) return '#86efac';
  if (mastery >= 0.6) return '#93c5fd';
  if (mastery >= 0.4) return '#fde047';
  return '#fca5a5';
};

const nodeTextColor = (mastery?: number): string => {
  if (mastery === undefined) return '#78716c';
  if (mastery >= 0.8) return '#166534';
  if (mastery >= 0.6) return '#1e40af';
  if (mastery >= 0.4) return '#a16207';
  return '#991b1b';
};

interface PositionedNode extends KnowledgeNode {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

export const KnowledgeMapRenderer: React.FC<{ payload: KnowledgeMapPayload }> = ({ payload }) => {
  if (!Array.isArray(payload.nodes) || payload.nodes.length === 0) return null;

  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const positioned = useMemo(() => {
    const nodes: PositionedNode[] = payload.nodes.map((n, i) => {
      const angle = (2 * Math.PI * i) / payload.nodes.length;
      const r = Math.min(W, H) * 0.3;
      return {
        ...n,
        x: W / 2 + r * Math.cos(angle),
        y: H / 2 + r * Math.sin(angle),
        vx: 0,
        vy: 0,
      };
    });

    const edges = payload.edges || [];
    const idToIdx = new Map(nodes.map((n, i) => [n.id, i]));

    for (let iter = 0; iter < 120; iter++) {
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          let dx = nodes[j].x - nodes[i].x;
          let dy = nodes[j].y - nodes[i].y;
          const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
          const force = 600 / (dist * dist);
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          nodes[i].vx -= fx;
          nodes[i].vy -= fy;
          nodes[j].vx += fx;
          nodes[j].vy += fy;
        }
      }

      for (const edge of edges) {
        const si = idToIdx.get(edge.from);
        const ti = idToIdx.get(edge.to);
        if (si === undefined || ti === undefined) continue;
        const dx = nodes[ti].x - nodes[si].x;
        const dy = nodes[ti].y - nodes[si].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const force = 0.008 * (dist - 100);
        const fx = (dx / Math.max(dist, 1)) * force;
        const fy = (dy / Math.max(dist, 1)) * force;
        nodes[si].vx += fx;
        nodes[si].vy += fy;
        nodes[ti].vx -= fx;
        nodes[ti].vy -= fy;
      }

      for (const node of nodes) {
        node.vx += (W / 2 - node.x) * 0.0008;
        node.vy += (H / 2 - node.y) * 0.0008;
      }

      for (const node of nodes) {
        node.x += node.vx;
        node.y += node.vy;
        node.vx *= 0.8;
        node.vy *= 0.8;
        node.x = Math.max(NODE_RADIUS + 10, Math.min(W - NODE_RADIUS - 10, node.x));
        node.y = Math.max(NODE_RADIUS + 10, Math.min(H - NODE_RADIUS - 10, node.y));
      }
    }

    return nodes;
  }, [payload.nodes, payload.edges]);

  const idToPos = useMemo(() => {
    const m = new Map<string, PositionedNode>();
    positioned.forEach(n => m.set(n.id, n));
    return m;
  }, [positioned]);

  const edges = payload.edges || [];
  const highlights = payload.highlights || [];

  return (
    <div className="p-5 space-y-3">
      {payload.title && (
        <h3 className="text-[15px] font-semibold tracking-tight text-foreground">{payload.title}</h3>
      )}

      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ minHeight: 240 }}>
        {/* Edges */}
        {edges.map((edge, i) => {
          const s = idToPos.get(edge.from);
          const t = idToPos.get(edge.to);
          if (!s || !t) return null;
          const active = hoveredId === edge.from || hoveredId === edge.to;
          return (
            <line
              key={i}
              x1={s.x} y1={s.y} x2={t.x} y2={t.y}
              stroke={active ? '#a1a1aa' : '#e4e4e7'}
              strokeWidth={1}
              strokeDasharray="4 2"
            />
          );
        })}

        {/* Nodes */}
        {positioned.map(node => {
          const isHighlight = highlights.includes(node.id);
          const isHovered = hoveredId === node.id;
          return (
            <g
              key={node.id}
              onMouseEnter={() => setHoveredId(node.id)}
              onMouseLeave={() => setHoveredId(null)}
              style={{ cursor: 'default' }}
            >
              <circle
                cx={node.x} cy={node.y} r={NODE_RADIUS}
                fill={nodeFill(node.mastery)}
                stroke={isHovered || isHighlight ? '#a1a1aa' : nodeStroke(node.mastery)}
                strokeWidth={isHovered || isHighlight ? 1.5 : 1}
              />
              <text
                x={node.x} y={node.y - (node.mastery !== undefined ? 3 : 0)}
                textAnchor="middle"
                dominantBaseline="central"
                style={{ fontSize: 11, fontWeight: 500, fill: nodeTextColor(node.mastery) }}
                className="pointer-events-none select-none"
              >
                {node.label.length > 6 ? node.label.slice(0, 6) + '..' : node.label}
              </text>
              {node.mastery !== undefined && (
                <text
                  x={node.x} y={node.y + 11}
                  textAnchor="middle"
                  dominantBaseline="central"
                  style={{ fontSize: 9, fontWeight: 400, fill: nodeTextColor(node.mastery), opacity: 0.6 }}
                  className="pointer-events-none select-none"
                >
                  {Math.round(node.mastery * 100)}%
                </text>
              )}
            </g>
          );
        })}
      </svg>

      {/* Legend — minimal */}
      <div className="flex flex-wrap items-center gap-4 text-[11px] text-foreground/35">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-emerald-50 border border-emerald-200" /> ≥80%
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-blue-50 border border-blue-200" /> 60–79%
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-yellow-50 border border-yellow-200" /> 40–59%
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-red-50 border border-red-200" /> &lt;40%
        </span>
        <span className="ml-auto">{edges.length} 关联</span>
      </div>
    </div>
  );
};
