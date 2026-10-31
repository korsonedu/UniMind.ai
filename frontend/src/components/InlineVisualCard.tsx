import React from 'react';
import { getVisualRenderer, type VisualData } from '@/pages/xiaoyu/visuals';
import '@/styles/visual-cards.css';

interface InlineVisualCardProps {
  visual: VisualData;
  index?: number;
}

export const InlineVisualCard: React.FC<InlineVisualCardProps> = React.memo(({ visual }) => {
  const Renderer = getVisualRenderer(visual.type);
  if (!Renderer) return <p className="um-visual-unavailable">暂时无法展示此内容。</p>;
  const payload = visual.payload as Record<string, unknown> | undefined;
  if (visual.type === 'action_cards' && (!payload || !(payload.cards as unknown[])?.length)) return null;

  return <section className="um-visual-card" data-visual-type={visual.type} aria-label={typeof payload?.title === 'string' ? payload.title : undefined}>
    <div className="um-visual-body"><Renderer payload={visual.payload} /></div>
  </section>;
});

InlineVisualCard.displayName = 'InlineVisualCard';
