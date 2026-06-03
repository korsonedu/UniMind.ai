import React from 'react';
import { getVisualRenderer, type VisualData } from '@/pages/xiaoyu/visuals';
import { cn } from '@/lib/utils';

interface InlineVisualCardProps {
  visual: VisualData;
  index?: number;
}

const PRIORITY_STYLES: Record<string, string> = {
  high: 'col-span-full',
  normal: '',
  low: 'opacity-80',
};

export const InlineVisualCard: React.FC<InlineVisualCardProps> = React.memo(({ visual, index = 0 }) => {
  const Renderer = getVisualRenderer(visual.type);
  if (!Renderer) {
    return (
      <div className="flex w-full">
        <div className="max-w-[85%] rounded-lg border border-border/40 bg-muted/30 px-3 py-2">
          <p className="text-[11px] text-foreground/30">不支持的可视化类型: {visual.type}</p>
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        'flex w-full animate-in fade-in slide-in-from-bottom-1 duration-300',
        PRIORITY_STYLES[visual.priority || 'normal'],
      )}
      style={{ animationDelay: `${Math.min(index * 40, 200)}ms` }}
    >
      <div className="w-full max-w-[90%] rounded-xl border border-border/50 bg-card overflow-hidden">
        <div className="p-3">
          <Renderer payload={visual.payload} />
        </div>
      </div>
    </div>
  );
});

InlineVisualCard.displayName = 'InlineVisualCard';
