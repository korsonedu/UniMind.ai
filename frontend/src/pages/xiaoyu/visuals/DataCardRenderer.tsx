import React, { useCallback } from 'react';
import { ArrowRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { cn } from '@/lib/utils';

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
}

export const DataCardRenderer: React.FC<{ payload: DataCardPayload }> = ({ payload }) => {
  const safeNavigate = useSafeNavigate();

  return (
    <div className="p-5 space-y-4">
      <div className="flex items-baseline gap-2">
        <h3 className="text-[15px] font-semibold tracking-tight text-foreground">{payload.title}</h3>
        {payload.subtitle && (
          <span className="text-[11px] text-foreground/30">{payload.subtitle}</span>
        )}
      </div>

      <div className="divide-y divide-border/60">
        {payload.items?.map((item, i) => {
          const clickable = !!item.action_link;
          const Wrapper = clickable ? 'button' : 'div';
          return (
            <Wrapper
              key={i}
              className={cn(
                "w-full flex items-center justify-between py-2.5 text-left",
                clickable && "hover:bg-foreground/[0.02] transition-colors cursor-pointer"
              )}
              {...(clickable ? { onClick: () => safeNavigate(item.action_link!) } : {})}
            >
              <span className="text-[13px] text-foreground/60">{item.label}</span>
              <span className={cn(
                "text-[13px] font-semibold tabular-nums",
                item.trend === 'up' && "text-emerald-600",
                item.trend === 'down' && "text-red-500",
                item.emphasis && "text-foreground",
              )}>
                {item.value}
              </span>
            </Wrapper>
          )
        })}
      </div>

      {payload.cta && (
        <button
          onClick={() => safeNavigate(payload.cta!.link)}
          className="flex items-center gap-1 text-[12px] font-medium text-foreground/50 hover:text-foreground/80 transition-colors"
        >
          {payload.cta.label}
          <ArrowRight className="h-3 w-3" />
        </button>
      )}
    </div>
  );
};
