import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { PlayCircle, Pen, ArrowCounterClockwise, BookOpen, TrendUp, Calendar, FileText, ArrowRight, CheckCircle } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';
import api from '@/lib/api';

/** Context for reply-type action cards to trigger a chat message send */
export const AgentReplyContext = createContext<{ onReply?: (value: string) => void }>({});
export const useAgentReply = () => useContext(AgentReplyContext);

type ReplyMode = 'single' | 'multi' | 'acknowledge' | 'input' | 'rating';

interface ActionCard {
  title: string;
  description: string;
  icon: string;
  priority?: 'high' | 'normal' | 'low';
  action: {
    type: string;
    url: string;
    label: string;
    reply_mode?: ReplyMode;
  };
}

interface ActionCardsPayload {
  title?: string;
  cards: ActionCard[];
  multi_separator?: string;  // 多选拼接分隔符，默认 '、'
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

/** 记录卡片点击（导航类型） */
async function trackCardClick(card: ActionCard) {
  if (!card.action.url) return;
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

/** 持久化 reply 卡片选择（复用 card-interactions API，completed=true 表示已选） */
async function persistReplyChoice(card: ActionCard) {
  if (!card.action.url) return;
  try {
    await api.post('/ai/card-interactions/', {
      card_title: card.title,
      card_action_type: 'reply',
      card_action_url: card.action.url,
      card_icon: card.icon,
      card_description: card.description,
      completed: true,
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
  const cards = (payload.cards || []).filter(c => c.title);
  const [completedMap, setCompletedMap] = useState<Record<string, boolean>>({});
  const [chosenUrl, setChosenUrl] = useState<string | null>(null);
  const [multiSelected, setMultiSelected] = useState<Set<string>>(new Set());
  const [inputValue, setInputValue] = useState('');
  const [ratingSent, setRatingSent] = useState(false);
  const [ratingValue, setRatingValue] = useState<number | null>(null);

  useEffect(() => {
    loadCompletionStatus().then(map => {
      setCompletedMap(map);
      const replyCards = cards.filter(c => c.action.type === 'reply');
      const mode = replyCards[0]?.action.reply_mode || 'single';
      if (mode === 'multi') {
        // 多选：恢复所有已选中的 URL
        const selected = new Set(replyCards.filter(c => map[c.action.url]).map(c => c.action.url));
        if (selected.size > 0) setMultiSelected(selected);
      } else if (mode === 'single' || mode === 'acknowledge') {
        // 单选/确认：恢复选中态
        const chosen = replyCards.find(c => map[c.action.url]);
        if (chosen) setChosenUrl(chosen.action.url);
      }
      // input/rating 不需恢复
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleClick = useCallback(async (card: ActionCard) => {
    const url = card.action.url;
    if (!url && card.action.reply_mode !== 'input') return;

    // reply 类型：按 reply_mode 分发
    if (card.action.type === 'reply') {
      const mode = card.action.reply_mode || 'single';

      if (mode === 'multi') {
        setMultiSelected(prev => {
          const next = new Set(prev);
          if (next.has(url)) next.delete(url); else next.add(url);
          return next;
        });
        return;
      }

      if (mode === 'acknowledge') {
        if (!chosenUrl) {
          setChosenUrl(url);
          persistReplyChoice(card);
        }
        return;
      }

      if (mode === 'rating') {
        if (onReply && !ratingSent) {
          setRatingSent(true);
          // 从 url 中提取实际分值（url 已被 onClick 替换了 {rating}）
          const match = url.match(/(\d+)/);
          if (match) setRatingValue(parseInt(match[1], 10));
          setChosenUrl(url);
          persistReplyChoice(card);
          onReply(url);
        }
        return;
      }

      // input 模式：由输入框+发送按钮处理，不应走到这里
      if (mode === 'input') return;

      // single（默认）：点一个全锁
      if (onReply && !chosenUrl && url) {
        setChosenUrl(url);
        persistReplyChoice(card);
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
  }, [navigate, onReply, chosenUrl, ratingSent]);

  // ── 多选确认 ──
  const handleMultiConfirm = useCallback(() => {
    if (!onReply || multiSelected.size === 0) return;
    const replyCards = cards.filter(c => c.action.type === 'reply');
    const sep = payload.multi_separator || '、';
    const text = replyCards
      .filter(c => multiSelected.has(c.action.url))
      .map(c => c.action.url)
      .join(sep);
    // 持久化每个选中项
    replyCards.filter(c => multiSelected.has(c.action.url)).forEach(persistReplyChoice);
    setChosenUrl('__multi__');
    onReply(text);
  }, [onReply, multiSelected, cards, payload.multi_separator]);

  // ── input 发送 ──
  const handleInputSend = useCallback((card: ActionCard) => {
    if (!onReply || !inputValue.trim()) return;
    const trimmed = inputValue.trim();
    setChosenUrl(trimmed);
    // input 模式以用户实际输入作为交互标识
    persistReplyChoice({ ...card, action: { ...card.action, url: trimmed } });
    onReply(trimmed);
  }, [onReply, inputValue]);

  const replyCards = cards.filter(c => c.action.type === 'reply');
  // 自动推断模式：url 为空且未显式指定 reply_mode → 视为 input（让用户自定义输入）
  const replyMode: ReplyMode = (() => {
    const explicit = replyCards[0]?.action.reply_mode;
    if (explicit) return explicit;
    if (!replyCards[0]?.action.url) return 'input';
    return 'single';
  })();

  if (!cards.length) return null;

  return (
    <div className="p-5 space-y-3">
      {payload.title && (
        <h3 className="text-[15px] font-semibold tracking-tight text-foreground">{payload.title}</h3>
      )}

      {/* ── rating 模式：1-5 数字评分 ── */}
      {replyMode === 'rating' && (() => {
        const card = replyCards[0];
        const maxStars = 5;
        return (
          <div className="flex items-center gap-2">
            {Array.from({ length: maxStars }, (_, n) => {
              const star = n + 1;
              const isActive = !ratingSent;
              const isSelected = ratingSent && ratingValue === star;
              return (
                <button
                  key={star}
                  onClick={() => {
                    if (!ratingSent && card) {
                      const url = card.action.url.replace('{rating}', String(star));
                      // 临时修改 url 以便 handleClick 使用
                      handleClick({ ...card, action: { ...card.action, url } });
                    }
                  }}
                  disabled={ratingSent}
                  className={cn(
                    'w-9 h-9 rounded-lg text-sm font-bold transition-colors border',
                    isActive && 'border-border/60 hover:border-foreground/20 hover:bg-muted/30',
                    isSelected && 'border-foreground/20 bg-muted/50',
                    ratingSent && !isSelected && 'opacity-40',
                  )}
                >
                  {star}
                </button>
              );
            })}
          </div>
        );
      })()}

      {/* ── 选项列表（single / multi / acknowledge）── */}
      {(replyMode === 'single' || replyMode === 'multi' || replyMode === 'acknowledge') && (
        <div className="space-y-1.5">
          {cards.map((card, i) => {
            const Icon = ICON_MAP[card.icon] || TrendUp;
            const isCompleted = completedMap[card.action.url] || false;
            const isReply = card.action.type === 'reply';
            const isChosen = chosenUrl === card.action.url;
            const isLocked = chosenUrl !== null;
            const isMultiChecked = multiSelected.has(card.action.url);
            const url = card.action.url;

            // reply 类型：选择题样式（single/multi/acknowledge 共用）
            if (isReply) {
              const replyIndex = cards.slice(0, i).filter(c => c.action.type === 'reply').length;
              const letter = String.fromCharCode(65 + (replyIndex % 26));

              if (replyMode === 'acknowledge') {
                return (
                  <button
                    key={i}
                    onClick={() => handleClick(card)}
                    disabled={isLocked}
                    className={cn(
                      'w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left',
                      'border transition-colors duration-150',
                      isChosen && 'border-foreground/20 bg-muted/50',
                      isLocked && 'opacity-50 pointer-events-none',
                      !isLocked && 'border-border/60 hover:border-foreground/20 hover:bg-muted/30',
                    )}
                  >
                    <span className={cn(
                      'text-sm font-bold',
                      isChosen ? 'text-foreground/60' : 'text-foreground/85',
                    )}>
                      {card.title}
                    </span>
                    {isChosen && <CheckCircle className="h-3.5 w-3.5 text-foreground/30 ml-auto" />}
                  </button>
                );
              }

              // multi 模式：勾选样式
              if (replyMode === 'multi') {
                return (
                  <button
                    key={i}
                    onClick={() => handleClick(card)}
                    className={cn(
                      'w-full flex items-start gap-2 px-3 py-2 rounded-lg text-left',
                      'border transition-colors duration-150',
                      isLocked && 'opacity-50 pointer-events-none',
                      isMultiChecked && !isLocked && 'border-foreground/20 bg-muted/50',
                      !isMultiChecked && !isLocked && 'border-border/60 hover:border-foreground/20 hover:bg-muted/30',
                    )}
                  >
                    <span className={cn(
                      'text-sm font-bold shrink-0 mt-px',
                      isMultiChecked ? 'text-foreground/70' : 'text-foreground/50',
                    )}>
                      {letter}.
                    </span>
                    <span className={cn(
                      'text-sm font-bold flex-1',
                      isMultiChecked ? 'text-foreground/85' : 'text-foreground/85',
                    )}>
                      {card.title}
                    </span>
                    {isMultiChecked && <CheckCircle className="h-3.5 w-3.5 text-foreground/30 shrink-0 mt-px" />}
                  </button>
                );
              }

              // single（默认）
              return (
                <button
                  key={i}
                  onClick={() => handleClick(card)}
                  disabled={isLocked}
                  className={cn(
                    'w-full flex items-start gap-2 px-3 py-2 rounded-lg text-left',
                    'border transition-colors duration-150',
                    isChosen && 'border-foreground/20 bg-muted/50',
                    isLocked && !isChosen && 'opacity-40 pointer-events-none border-border/30',
                    !isLocked && 'border-border/60 hover:border-foreground/20 hover:bg-muted/30',
                  )}
                >
                  <span className={cn(
                    'text-sm font-bold shrink-0 mt-px',
                    isChosen ? 'text-foreground/70' : isLocked ? 'text-foreground/30' : 'text-foreground/50',
                  )}>
                    {letter}.
                  </span>
                  <span className={cn(
                    'text-sm font-bold flex-1',
                    isChosen ? 'text-foreground/85' : isLocked ? 'text-foreground/30' : 'text-foreground/85',
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
      )}

      {/* ── input 模式：输入框 ── */}
      {replyMode === 'input' && (
        <div className="flex gap-2">
          <input
            type="text"
            value={inputValue}
            onChange={e => setInputValue(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && inputValue.trim()) handleInputSend(replyCards[0]); }}
            placeholder={replyCards[0]?.action.label || '输入内容...'}
            disabled={chosenUrl !== null}
            className={cn(
              'flex-1 px-3 py-2 rounded-lg border text-sm bg-transparent',
              'border-border/60 focus:border-foreground/20 focus:outline-none',
              'placeholder:text-muted-foreground/40',
              chosenUrl && 'opacity-50 pointer-events-none',
            )}
          />
          <button
            onClick={() => handleInputSend(replyCards[0])}
            disabled={!inputValue.trim() || chosenUrl !== null}
            className="px-4 py-2 rounded-lg border border-border/60 text-sm font-bold hover:border-foreground/20 hover:bg-muted/30 transition-colors disabled:opacity-30 disabled:pointer-events-none"
          >
            发送
          </button>
        </div>
      )}

      {/* ── 多选确认按钮 ── */}
      {replyMode === 'multi' && !chosenUrl && multiSelected.size > 0 && (
        <button
          onClick={handleMultiConfirm}
          className="w-full py-2 rounded-lg border border-foreground/20 text-sm font-bold hover:bg-muted/30 transition-colors"
        >
          确认 ({multiSelected.size})
        </button>
      )}
    </div>
  );
};
