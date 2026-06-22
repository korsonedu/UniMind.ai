import { useState, useRef, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Chat, X, PaperPlaneTilt, Bug, Lightbulb, Question, ChatCircleDots, Clock } from '@phosphor-icons/react';
import { toast } from 'sonner';
import api from '@/lib/api';
import { cn } from '@/lib/utils';

const CATEGORIES = [
  { key: 'bug', icon: Bug, label: 'Bug 反馈', color: 'bg-red-50 text-red-600 border-red-100 dark:bg-red-950/30 dark:text-red-400 dark:border-red-800/30' },
  { key: 'feature', icon: Lightbulb, label: '功能建议', color: 'bg-amber-50 text-amber-600 border-amber-100 dark:bg-amber-950/30 dark:text-amber-400 dark:border-amber-800/30' },
  { key: 'other', icon: Question, label: '其他', color: 'bg-blue-50 text-blue-600 border-blue-100 dark:bg-blue-950/30 dark:text-blue-400 dark:border-blue-800/30' },
] as const;

interface FeedbackItem {
  id: number;
  category: string;
  content: string;
  contact: string;
  page_url: string;
  created_at: string;
}

const DEFAULT_POS = { x: 0, y: 0 }; // 右下角偏移量

export function FeedbackButton() {
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState<string>('bug');
  const [content, setContent] = useState('');
  const [contact, setContact] = useState('');
  const [sending, setSending] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState<FeedbackItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  // 拖动状态
  const [position, setPosition] = useState<{ x: number; y: number } | null>(null);
  const [hasMoved, setHasMoved] = useState(false);
  const dragging = useRef(false);
  const offset = useRef({ x: 0, y: 0 });
  const btnRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    if (!btnRef.current) return;
    dragging.current = true;
    const rect = btnRef.current.getBoundingClientRect();
    offset.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    setHasMoved(false);
  }, []);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragging.current) return;
    const x = e.clientX - offset.current.x;
    const y = e.clientY - offset.current.y;
    setPosition({ x, y });
    if (Math.abs(x - (position?.x ?? DEFAULT_POS.x)) > 3 || Math.abs(y - (position?.y ?? DEFAULT_POS.y)) > 3) {
      setHasMoved(true);
    }
  }, [position]);

  const onPointerUp = useCallback((e: React.PointerEvent) => {
    dragging.current = false;
    (e.target as HTMLElement).releasePointerCapture(e.pointerId);
  }, []);

  const handleButtonClick = useCallback(() => {
    if (!hasMoved) {
      setOpen(true);
    }
    setHasMoved(false);
  }, [hasMoved]);

  const handleSubmit = async () => {
    if (!content.trim()) {
      toast.error('请输入反馈内容');
      return;
    }
    setSending(true);
    try {
      await api.post('/users/feedback/', {
        category,
        content: content.trim(),
        contact: contact.trim(),
        page_url: window.location.pathname,
      });
      toast.success('感谢您的反馈！');
      setContent('');
      setContact('');
      setOpen(false);
      setShowHistory(false);
    } catch {
      toast.error('提交失败，请稍后重试');
    } finally {
      setSending(false);
    }
  };

  const loadHistory = async () => {
    setHistoryLoading(true);
    setShowHistory(true);
    try {
      const res = await api.get('/users/feedback/');
      setHistory(res.data || []);
    } catch {
      toast.error('加载反馈历史失败');
    } finally {
      setHistoryLoading(false);
    }
  };

  const categoryLabel = (cat: string) => {
    const found = CATEGORIES.find(c => c.key === cat);
    return found ? found.label : cat;
  };

  const floatingStyle: React.CSSProperties = position
    ? { position: 'fixed', left: position.x, top: position.y, zIndex: 50 }
    : { position: 'fixed', bottom: '1.5rem', right: '1.5rem', zIndex: 50 };

  if (!open) {
    return (
      <button
        ref={btnRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onClick={handleButtonClick}
        style={floatingStyle}
        className={cn(
          "h-12 w-12 rounded-full bg-black dark:bg-white text-white dark:text-black shadow-lg flex items-center justify-center transition-[box-shadow,transform] duration-200 active:scale-95 select-none",
          dragging.current ? "shadow-2xl scale-105 cursor-grabbing" : "hover:shadow-xl hover:scale-110 cursor-grab",
        )}
        aria-label="反馈"
        title="拖拽可移动位置"
      >
        <Chat className="h-5 w-5" />
      </button>
    );
  }

  const panelStyle: React.CSSProperties = position
    ? { position: 'fixed', left: Math.max(0, position.x - 320), top: Math.min(window.innerHeight - 500, position.y - 10), zIndex: 50 }
    : { position: 'fixed', bottom: '1.5rem', right: '1.5rem', zIndex: 50 };

  return (
    <div
      ref={panelRef}
      style={panelStyle}
      className="w-80 bg-white dark:bg-zinc-900 rounded-2xl shadow-2xl border border-black/5 dark:border-white/10 overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-black/5 dark:border-white/5">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowHistory(false)}
            className={cn(
              "text-xs font-bold px-2 py-0.5 rounded-lg transition-colors",
              !showHistory ? "bg-black text-white dark:bg-white dark:text-black" : "text-muted-foreground hover:text-foreground"
            )}
          >
            反馈
          </button>
          <button
            onClick={() => { if (history.length === 0) loadHistory(); else setShowHistory(true); }}
            className={cn(
              "text-xs font-bold px-2 py-0.5 rounded-lg transition-colors",
              showHistory ? "bg-black text-white dark:bg-white dark:text-black" : "text-muted-foreground hover:text-foreground"
            )}
          >
            我的反馈
          </button>
        </div>
        <button onClick={() => { setOpen(false); setShowHistory(false); }} className="text-muted-foreground hover:text-foreground">
          <X className="h-4 w-4" />
        </button>
      </div>

      {showHistory ? (
        <div className="max-h-[360px] overflow-y-auto">
          {historyLoading ? (
            <div className="p-8 text-center text-xs text-muted-foreground">加载中...</div>
          ) : history.length === 0 ? (
            <div className="p-8 text-center space-y-2">
              <ChatCircleDots className="h-8 w-8 mx-auto text-muted-foreground/20" />
              <p className="text-xs text-muted-foreground">暂无反馈记录</p>
            </div>
          ) : (
            <div className="divide-y divide-border/30">
              {history.map(item => {
                const CatIcon = CATEGORIES.find(c => c.key === item.category)?.icon || Question;
                return (
                  <div key={item.id} className="p-3 space-y-1.5 hover:bg-muted/30 transition-colors">
                    <div className="flex items-center justify-between">
                      <span className="flex items-center gap-1 text-[10px] font-bold text-muted-foreground">
                        <CatIcon className="h-3 w-3" />
                        {categoryLabel(item.category)}
                      </span>
                      <span className="flex items-center gap-0.5 text-[9px] text-muted-foreground/50">
                        <Clock className="h-2.5 w-2.5" />
                        {new Date(item.created_at).toLocaleDateString('zh-CN')}
                      </span>
                    </div>
                    <p className="text-xs leading-relaxed text-foreground/80 line-clamp-3">{item.content}</p>
                    {item.contact && (
                      <p className="text-[10px] text-muted-foreground/50">{item.contact}</p>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ) : (
        <div className="p-4 space-y-4">
          <div className="flex gap-2">
            {CATEGORIES.map(cat => {
              const Icon = cat.icon;
              return (
                <button
                  key={cat.key}
                  onClick={() => setCategory(cat.key)}
                  className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-bold border transition-all ${
                    category === cat.key ? cat.color : 'bg-slate-50 dark:bg-zinc-800 text-muted-foreground border-transparent'
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {cat.label}
                </button>
              );
            })}
          </div>

          <textarea
            value={content}
            onChange={e => setContent(e.target.value)}
            placeholder="描述您遇到的问题或建议..."
            className="w-full bg-slate-50 dark:bg-zinc-800 border-none rounded-xl p-3 min-h-[100px] text-sm focus:outline-none focus:ring-1 focus:ring-black/10 dark:focus:ring-white/10 resize-none"
            maxLength={2000}
          />

          <Input
            value={contact}
            onChange={e => setContact(e.target.value)}
            placeholder="联系方式（选填）"
            className="bg-slate-50 dark:bg-zinc-800 border-none h-9 rounded-xl text-xs"
          />

          <Button
            onClick={handleSubmit}
            disabled={sending || !content.trim()}
            className="w-full h-10 bg-black dark:bg-white dark:text-black text-white rounded-xl text-xs font-bold"
          >
            <PaperPlaneTilt className="mr-2 h-3.5 w-3.5" />
            {sending ? '提交中...' : '提交反馈'}
          </Button>
        </div>
      )}
    </div>
  );
}
