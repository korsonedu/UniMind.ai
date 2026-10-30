import React, { useCallback } from 'react';
import { ArrowRight, ArrowUpRight, TrendDown, TrendUp } from '@phosphor-icons/react';
import { useNavigate } from 'react-router-dom';

const useSafeNavigate = () => {
  const navigate = useNavigate();
  return useCallback((link: string) => {
    if (!link) return;
    if (link.startsWith('/')) navigate(link);
    else if (link.startsWith('http')) window.open(link, '_blank', 'noopener,noreferrer');
  }, [navigate]);
};

interface DataCardPayload {
  title: string;
  subtitle?: string;
  items: Array<{
    label: string;
    value: string;
    trend?: 'up' | 'down' | 'neutral';
    progress?: number;
    emphasis?: boolean;
    action_link?: string;
  }>;
  cta?: { label: string; link: string };
  note?: string;
}

export const DataCardRenderer: React.FC<{ payload: DataCardPayload }> = ({ payload }) => {
  const safeNavigate = useSafeNavigate();
  return <div className="um-visual-data">
    <header className="um-visual-heading"><h3>{payload.title}</h3>{payload.subtitle && <p>{payload.subtitle}</p>}</header>
    <div className="um-visual-data-rows">
      {payload.items?.map((item, index) => {
        const Wrapper = item.action_link ? 'button' : 'div';
        return <Wrapper key={index} className="um-visual-data-row" data-link={!!item.action_link || undefined}
          {...(item.action_link ? { type: 'button' as const, onClick: () => safeNavigate(item.action_link!) } : {})}>
          <span className="um-visual-data-label">{item.label}</span>
          <span className="um-visual-data-value" data-emphasis={item.emphasis || undefined} data-trend={item.trend}>
            {item.trend === 'up' && <TrendUp size={14} aria-label="上升" />}{item.trend === 'down' && <TrendDown size={14} aria-label="下降" />}
            {item.value}{item.action_link && <ArrowUpRight size={14} className="um-visual-data-arrow" />}
          </span>
        </Wrapper>;
      })}
    </div>
    {payload.note && <p className="um-visual-note">{payload.note}</p>}
    {payload.cta && <button type="button" onClick={() => safeNavigate(payload.cta!.link)} className="um-visual-link">{payload.cta.label}<ArrowRight size={14} /></button>}
  </div>;
};
