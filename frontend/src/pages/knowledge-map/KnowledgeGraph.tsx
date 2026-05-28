import React, { useState, useEffect, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { ZoomIn, ZoomOut, Maximize2 } from 'lucide-react';
import type { KPNode } from './types';

export const KnowledgeGraph = ({ nodes, onNodeClick }: { nodes: KPNode[], onNodeClick: (node: KPNode) => void }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [transform, setTransform] = useState({ x: 0, y: 0, k: 1 });
  const nodesRef = useRef<KPNode[]>([]);
  const requestRef = useRef<number>(null);

  // Initialize nodes with random positions
  useEffect(() => {
    nodesRef.current = nodes.map(n => ({
      ...n,
      x: (Math.random() - 0.5) * 800,
      y: (Math.random() - 0.5) * 600,
      vx: 0,
      vy: 0
    }));
  }, [nodes]);

  const animate = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // --- Physics Simulation ---
    const nodes = nodesRef.current;
    const repulsion = 1500;
    const centerForce = 0.01;

    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];

      // Repulsion between all nodes
      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j];
        const dx = b.x! - a.x!;
        const dy = b.y! - a.y!;
        const distance = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = repulsion / (distance * distance);
        const fx = (dx / distance) * force;
        const fy = (dy / distance) * force;
        a.vx! -= fx;
        a.vy! -= fy;
        b.vx! += fx;
        b.vy! += fy;
      }

      // Attraction to center
      a.vx! -= a.x! * centerForce;
      a.vy! -= a.y! * centerForce;

      // Damping
      a.vx! *= 0.9;
      a.vy! *= 0.9;
    }

    // Update positions
    for (const node of nodes) {
      node.x! += node.vx!;
      node.y! += node.vy!;
    }

    // --- Rendering ---
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.save();
    ctx.translate(canvas.width / 2 + transform.x, canvas.height / 2 + transform.y);
    ctx.scale(transform.k, transform.k);

    // Draw Edges
    const parentNode = nodes.find(n => n.name === "金融理论");
    if (parentNode) {
      ctx.beginPath();
      ctx.strokeStyle = 'rgba(0,0,0,0.05)';
      ctx.lineWidth = 1;
      for (const node of nodes) {
        if (node === parentNode) continue;
        ctx.moveTo(parentNode.x!, parentNode.y!);
        ctx.lineTo(node.x!, node.y!);
      }
      ctx.stroke();
    }

    // Draw Nodes
    for (const node of nodes) {
      const radius = 5 + Math.sqrt(node.questions_count || 0) * 2;
      ctx.beginPath();
      ctx.arc(node.x!, node.y!, radius, 0, Math.PI * 2);
      ctx.fillStyle = node.name === "金融理论" ? "#4f46e5" : "white";
      ctx.fill();
      ctx.strokeStyle = "#e2e8f0";
      ctx.lineWidth = 2;
      ctx.stroke();

      // Text
      if (transform.k > 0.6) {
        ctx.fillStyle = "#1e293b";
        ctx.font = `bold ${11 / transform.k}px sans-serif`;
        ctx.textAlign = "center";
        ctx.fillText(node.name, node.x!, node.y! + radius + 12 / transform.k);
      }
    }

    ctx.restore();
    requestRef.current = requestAnimationFrame(animate);
  };

  useEffect(() => {
    requestRef.current = requestAnimationFrame(animate);
    return () => { if (requestRef.current) cancelAnimationFrame(requestRef.current); };
  }, [transform]);

  const handleWheel = (e: React.WheelEvent) => {
    const delta = e.deltaY > 0 ? 0.98 : 1.02;
    setTransform(prev => ({ ...prev, k: Math.max(0.1, Math.min(5, prev.k * delta)) }));
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    const startX = e.clientX - transform.x;
    const startY = e.clientY - transform.y;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      setTransform(prev => ({
        ...prev,
        x: moveEvent.clientX - startX,
        y: moveEvent.clientY - startY
      }));
    };

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

    const mouseX = (e.clientX - rect.left - canvas.width / 2 - transform.x) / transform.k;
    const mouseY = (e.clientY - rect.top - canvas.height / 2 - transform.y) / transform.k;

    for (const node of nodesRef.current) {
      const dx = node.x! - mouseX;
      const dy = node.y! - mouseY;
      const radius = (5 + Math.sqrt(node.questions_count || 0) * 2);
      if (Math.sqrt(dx * dx + dy * dy) < radius + 15) {
        onNodeClick(node);
        break;
      }
    }
  };

  return (
    <div className="relative w-full h-[600px] bg-slate-50/50 rounded-[3rem] border border-border/50 overflow-hidden cursor-move shadow-inner">
      <canvas
        ref={canvasRef}
        width={1200}
        height={600}
        className="w-full h-full"
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onClick={handleClick}
      />
      <div className="absolute bottom-8 left-8 flex flex-col gap-2">
        <Button variant="secondary" size="icon" className="rounded-xl shadow-lg" onClick={() => setTransform(p => ({ ...p, k: p.k * 1.2 }))} aria-label="Zoom in"><ZoomIn className="h-4 w-4" /></Button>
        <Button variant="secondary" size="icon" className="rounded-xl shadow-lg" onClick={() => setTransform(p => ({ ...p, k: p.k * 0.8 }))} aria-label="Zoom out"><ZoomOut className="h-4 w-4" /></Button>
        <Button variant="secondary" size="icon" className="rounded-xl shadow-lg" onClick={() => setTransform({ x: 0, y: 0, k: 1 })} aria-label="Reset zoom"><Maximize2 className="h-4 w-4" /></Button>
      </div>
      <div className="absolute top-8 right-8">
        <div className="flex items-center gap-2 px-4 py-2 bg-white/80 backdrop-blur-md rounded-2xl border border-border/50 shadow-sm">
          <div className="h-2 w-2 rounded-full bg-stone-400" />
          <span className="text-[11px] font-medium text-stone-500 leading-none">Graph View</span>
        </div>
      </div>
    </div>
  );
};
