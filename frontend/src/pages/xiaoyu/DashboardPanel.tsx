import React from 'react';
import { getVisualRenderer, type VisualData } from './visuals';

interface VisualCanvasProps {
  visual: VisualData | null;
}

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

  const Renderer = getVisualRenderer(visual.type);
  if (!Renderer) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-sm text-muted-foreground/40">不支持的可视化类型: {visual.type}</p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <Renderer payload={visual.payload} />
    </div>
  );
};

// Backward-compatible alias
export { VisualCanvas as DashboardPanel };
export type { VisualData as DashboardData };
