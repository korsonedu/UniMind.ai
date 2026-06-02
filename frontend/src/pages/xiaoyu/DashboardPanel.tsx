import React from 'react';
import { getVisualRenderer, type VisualData } from './visuals';
import { cn } from '@/lib/utils';

interface VisualCanvasProps {
  visual: VisualData | VisualData[] | null;
}

const SingleVisual: React.FC<{ visual: VisualData }> = ({ visual }) => {
  const Renderer = getVisualRenderer(visual.type);
  if (!Renderer) {
    return (
      <div className="flex items-center justify-center py-8">
        <p className="text-[12px] text-foreground/25">不支持的可视化类型: {visual.type}</p>
      </div>
    );
  }
  return <Renderer payload={visual.payload} />;
};

const PRIORITY_ORDER: Record<string, number> = { high: 0, normal: 1, low: 2 };

export const VisualCanvas: React.FC<VisualCanvasProps> = ({ visual }) => {
  if (!visual) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center space-y-1">
          <p className="text-[13px] text-foreground/40 font-medium">在右侧对话，内容在此呈现</p>
          <p className="text-[11px] text-foreground/20">公式推导 · 函数图像 · 知识图谱 · 学习数据</p>
        </div>
      </div>
    );
  }

  const visuals = Array.isArray(visual) ? visual : [visual];
  const sorted = [...visuals].sort((a, b) => (PRIORITY_ORDER[a.priority || 'normal'] ?? 1) - (PRIORITY_ORDER[b.priority || 'normal'] ?? 1));

  if (sorted.length === 1) {
    return (
      <div className="h-full overflow-y-auto">
        <SingleVisual visual={sorted[0]} />
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="grid grid-cols-2 gap-4">
        {sorted.map((v, i) => (
          <div key={`${v.type}-${i}`} className={cn(v.priority === 'high' && 'col-span-2')}>
            <SingleVisual visual={v} />
          </div>
        ))}
      </div>
    </div>
  );
};

// Backward-compatible alias
export { VisualCanvas as DashboardPanel };
export type { VisualData as DashboardData };
export type { VisualData };
