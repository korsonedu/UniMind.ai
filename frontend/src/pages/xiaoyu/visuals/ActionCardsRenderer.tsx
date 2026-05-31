import React, { useMemo } from 'react';
import {
  PlayCircle,
  PenLine,
  RotateCcw,
  BookOpen,
  TrendingUp,
  Calendar,
  FileText,
  ArrowRight,
} from 'lucide-react';
import { cn } from '@/lib/utils';

type Priority = 'high' | 'normal' | 'low';

interface ActionCard {
  title: string;
  description: string;
  priority: Priority;
  icon: string;
  action: { type: string; url: string; label: string };
}

interface ActionCardsPayload {
  title?: string;
  cards: ActionCard[];
}

const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  video: PlayCircle,
  quiz: PenLine,
  review: RotateCcw,
  course: BookOpen,
  chart: TrendingUp,
  plan: Calendar,
  exam: FileText,
};

const ICON_COLOR: Record<string, string> = {
  video: 'text-violet-500 bg-violet-50',
  quiz: 'text-amber-500 bg-amber-50',
  review: 'text-sky-500 bg-sky-50',
  course: 'text-emerald-500 bg-emerald-50',
  chart: 'text-rose-500 bg-rose-50',
  plan: 'text-blue-500 bg-blue-50',
  exam: 'text-orange-500 bg-orange-50',
};

const BORDER_COLOR: Record<string, string> = {
  video: 'border-l-violet-400',
  quiz: 'border-l-amber-400',
  review: 'border-l-sky-400',
  course: 'border-l-emerald-400',
  chart: 'border-l-rose-400',
  plan: 'border-l-blue-400',
  exam: 'border-l-orange-400',
};

const PRIORITY_ORDER: Record<Priority, number> = {
  high: 0,
  normal: 1,
  low: 2,
};

function navigateTo(url: string) {
  if (!url) return;
  if (url.startsWith('/')) window.location.href = url;
  else if (url.startsWith('http')) window.open(url, '_blank', 'noopener,noreferrer');
}

export const ActionCardsRenderer: React.FC<{ payload: ActionCardsPayload }> = ({ payload }) => {
  const sorted = useMemo(
    () => [...(payload.cards || [])].sort((a, b) => PRIORITY_ORDER[a.priority] - PRIORITY_ORDER[b.priority]),
    [payload.cards],
  );

  if (!sorted.length) return null;

  return (
    <div className="p-4 space-y-3 animate-in fade-in duration-300">
      {payload.title && <h3 className="text-sm font-semibold">{payload.title}</h3>}
      <div className="grid grid-cols-2 gap-3">
        {sorted.map((card, i) => {
          const Icon = ICON_MAP[card.icon] || TrendingUp;
          const span2 = card.priority === 'high';
          return (
            <button
              key={i}
              onClick={() => navigateTo(card.action.url)}
              className={cn(
                'group flex flex-col gap-2 rounded-lg border border-l-4 bg-card p-3 text-left transition-all',
                'hover:-translate-y-px hover:shadow-md',
                BORDER_COLOR[card.icon] || 'border-l-gray-400',
                span2 && 'col-span-2',
              )}
            >
              <div className="flex items-start gap-2.5">
                <span className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-md', ICON_COLOR[card.icon] || 'text-gray-500 bg-gray-50')}>
                  <Icon className="h-4 w-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium leading-tight">{card.title}</div>
                  <p className="mt-1 text-xs text-muted-foreground leading-relaxed line-clamp-2">
                    {card.description}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-1 text-xs font-medium text-primary/70 group-hover:text-primary transition-colors">
                {card.action.label}
                <ArrowRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5" />
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};
