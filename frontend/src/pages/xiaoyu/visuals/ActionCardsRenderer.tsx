import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { PlayCircle, Pen, ArrowCounterClockwise, BookOpen, TrendUp, Calendar, FileText, ArrowRight, CheckCircle } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';
import api from '@/lib/api';

/** Context for reply-type action cards to trigger a chat message send */
export const AgentReplyContext = createContext<{ onReply?: (value: string) => void }>({});
export const useAgentReply = () => useContext(AgentReplyContext);

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
  quiz: Pen,
  review: ArrowCounterClockwise,
  course: BookOpen,
  chart: TrendUp,
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
  const { onReply } = useAgentReply();
  const cards = payload.cards || [];
  const [completedMap, setCompletedMap] = useState<Record<string, boolean>>({});
  const [repliedMap, setRepliedMap] = useState<Record<string, boolean>>({});

  useEffect(() => {
    loadCompletionStatus().then(setCompletedMap);
  }, []);

  const handleClick = useCallback(async (card: ActionCard) => {
    const url = card.action.url;
    if (!url) return;

    // reply 类型：发送消息到对话
    if (card.action.type === 'reply') {
      if (onReply && !repliedMap[url]) {
        setRepliedMap(prev => ({ ...prev, [url]: true }));
        onReply(url);
      }
      return;
    }

    // 记录点击
    trackCardClick(card);

    // 练习卡片：先创建 session，再跳转
    if (url.startsWith('/xiaoyu/practice/new')) {
      try {
        const params = new URLSearchParams(url.split('?')[1] || '');
        const { data } = await api.post('/ai/practice/start/', {
          kp_name: params.get('kp_name') || '',
          subject: params.get('subject') || '',
          count: parseInt(params.get('count') || '5', 10),
        });
        if (data.session_id) {
          navigate(`/xiaoyu/practice/${data.session_id}`);
          return;
        }
      } catch { /* fall through to direct navigation */ }
    }

    // 跳转
    if (url.startsWith('/')) navigate(url);
    else if (url.startsWith('http')) window.open(url, '_blank', 'noopener,noreferrer');
  }, [navigate, onReply, repliedMap]);

  if (!cards.length) return null;

  return (
    <div className="p-5 space-y-3">
      {payload.title && (
        <h3 className="text-[15px] font-semibold tracking-tight text-foreground">{payload.title}</h3>
      )}
      <div className="space-y-1.5">
        {cards.map((card, i) => {
          const Icon = ICON_MAP[card.icon] || TrendUp;
          const isCompleted = completedMap[card.action.url] || false;
          const isReply = card.action.type === 'reply';
          const isReplied = repliedMap[card.action.url] || false;

          // reply 类型：选择题样式
          if (isReply) {
            const replyIndex = cards.slice(0, i).filter(c => c.action.type === 'reply').length;
            const letter = String.fromCharCode(65 + (replyIndex % 26));
            return (
              <button
                key={i}
                onClick={() => handleClick(card)}
                disabled={isReplied}
                className={cn(
                  'w-full flex items-start gap-2 px-3 py-2 rounded-lg text-left',
                  'border border-border/60 hover:border-primary/40 hover:bg-primary/[0.02]',
                  'transition-colors duration-150',
                  isReplied && 'opacity-50 pointer-events-none border-emerald-500/40 bg-emerald-50',
                )}
              >
                <span className={cn(
                  'text-sm font-bold shrink-0 mt-px',
                  isReplied ? 'text-emerald-600' : 'text-foreground/50',
                )}>
                  {letter}.
                </span>
                <span className={cn(
                  'text-sm font-bold flex-1',
                  isReplied ? 'text-emerald-700' : 'text-foreground/85',
                )}>
                  {card.title}
                </span>
              </button>
            );
          }

          // 导航类型：保持现有样式
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
                  <CheckCircle className="h-3 w-3 text-emerald-500 absolute -top-1 -right-1.5 fill-emerald-500/20" />
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
