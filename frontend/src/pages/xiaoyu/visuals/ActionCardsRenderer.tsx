import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  PlayCircle, PenLine, RotateCcw, BookOpen,
  TrendingUp, Calendar, FileText, ArrowRight, CheckCircle2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import api from '@/lib/api';

interface ActionCard {
  title: string;
  description: string;
  icon: string;
  priority?: 'high' | 'normal' | 'low';
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

/** 记录卡片点击 */
async function trackCardClick(card: ActionCard) {
  try {
    await api.post('/ai/card-interactions/', {
      card_title: card.title,
      card_action_type: card.action.type,
      card_action_url: card.action.url,
      card_icon: card.icon,
      card_description: card.description,
      completed: false,
    });
  } catch { /* 静默失败 */ }
}

/** 记录卡片完成 */
export async function trackCardComplete(actionUrl: string) {
  try {
    await api.post('/ai/card-interactions/', {
      card_action_url: actionUrl,
      card_action_type: 'quiz',
      card_title: '',
      completed: true,
    });
  } catch { /* 静默失败 */ }
}

/** 加载用户卡片完成状态 */
async function loadCompletionStatus(): Promise<Record<string, boolean>> {
  try {
    const { data } = await api.get('/ai/card-interactions/');
    const map: Record<string, boolean> = {};
    for (const item of data.interactions || []) {
      if (item.completed) {
        map[item.card_action_url] = true;
      }
    }
    return map;
  } catch {
    return {};
  }
}

export const ActionCardsRenderer: React.FC<{ payload: ActionCardsPayload }> = ({ payload }) => {
  const navigate = useNavigate();
  const cards = payload.cards || [];
  const [completedMap, setCompletedMap] = useState<Record<string, boolean>>({});

  useEffect(() => {
    loadCompletionStatus().then(setCompletedMap);
  }, []);

  const handleClick = useCallback((card: ActionCard) => {
    const url = card.action.url;
    if (!url) return;

    // 记录点击
    trackCardClick(card);

    // 跳转
    if (url.startsWith('/')) navigate(url);
    else if (url.startsWith('http')) window.open(url, '_blank', 'noopener,noreferrer');
  }, [navigate]);

  if (!cards.length) return null;

  return (
    <div className="p-5 space-y-3">
      {payload.title && (
        <h3 className="text-[15px] font-semibold tracking-tight text-foreground">{payload.title}</h3>
      )}
      <div className="space-y-2">
        {cards.map((card, i) => {
          const Icon = ICON_MAP[card.icon] || TrendingUp;
          const isCompleted = completedMap[card.action.url] || false;

          return (
            <button
              key={i}
              onClick={() => handleClick(card)}
              className={cn(
                'group w-full flex items-start gap-3 py-3 text-left',
                'border-b border-border/40 last:border-0',
                isCompleted && 'opacity-70',
              )}
            >
              <div className="relative shrink-0 mt-0.5">
                <Icon className={cn(
                  'h-4 w-4',
                  isCompleted ? 'text-emerald-500/70' : 'text-foreground/30',
                )} />
                {isCompleted && (
                  <CheckCircle2 className="h-3 w-3 text-emerald-500 absolute -top-1 -right-1.5 fill-emerald-500/20" />
                )}
              </div>
              <div className="flex-1 min-w-0 space-y-0.5">
                <div className="flex items-center gap-1.5">
                  <span className={cn(
                    'text-[13px] font-medium',
                    isCompleted ? 'text-foreground/50 line-through' : 'text-foreground/80',
                  )}>
                    {card.title}
                  </span>
                  {isCompleted && (
                    <span className="text-[10px] font-medium text-emerald-600 bg-emerald-500/10 px-1.5 py-0.5 rounded-full">
                      已完成
                    </span>
                  )}
                </div>
                <p className="text-[12px] text-foreground/40 leading-relaxed line-clamp-2">
                  {card.description}
                </p>
                <div className={cn(
                  'flex items-center gap-1 text-[11px] font-medium pt-0.5 transition-colors',
                  isCompleted
                    ? 'text-emerald-600/50'
                    : 'text-foreground/30 group-hover:text-foreground/50',
                )}>
                  {isCompleted ? '再次练习' : card.action.label}
                  <ArrowRight className="h-2.5 w-2.5 transition-transform group-hover:translate-x-0.5" />
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};
