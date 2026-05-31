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
        <p className="text-sm text-muted-foreground/40">不支持的可视化类型: {visual.type}</p>
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
        <div className="text-center space-y-2">
          <p className="text-sm text-muted-foreground/40">小宇会在对话中为你生成可视化内容</p>
          <p className="text-xs text-muted-foreground/25">数学推导、解题步骤、知识图谱、学习数据</p>
        </div>
      </div>
    );
  }

  const visuals = Array.isArray(visual) ? visual : [visual];
  const sorted = [...visuals].sort((a, b) => (PRIORITY_ORDER[a.priority || 'normal'] ?? 1) - (PRIORITY_ORDER[b.priority || 'normal'] ?? 1));

  // Single visual: render directly without grid
  if (sorted.length === 1) {
    return (
      <div className="h-full overflow-y-auto p-2">
        <SingleVisual visual={sorted[0]} />
      </div>
    );
  }

  // Multiple visuals: masonry grid
  return (
    <div className="h-full overflow-y-auto p-2">
      <div className="grid grid-cols-2 gap-3">
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
