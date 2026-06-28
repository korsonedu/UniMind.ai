import React, { useState, useEffect, useRef } from 'react';
import { Robot, PaperPlaneTilt, CaretDown, CaretUp } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useXiaoYuStore } from '@/store/useXiaoYuStore';
import type { XiaoYuMessage } from '@/store/useXiaoYuStore';

interface CoachPanelProps {
  className?: string;
}

export const CoachPanel: React.FC<CoachPanelProps> = ({ className }) => {
  const [collapsed, setCollapsed] = useState(true);
  const [input, setInput] = useState('');

  const storeMessages = useXiaoYuStore((s) => s.messages);
  const storeLoading = useXiaoYuStore((s) => s.loading);
  const sendMessage = useXiaoYuStore((s) => s.sendMessage);
  const botId = useXiaoYuStore((s) => s.botId);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Show only user messages and final assistant messages (no tool steps in compact view)
  const messages: XiaoYuMessage[] = storeMessages.filter(
    (m) => m.role === 'user' || (m.role === 'assistant' && m.content && !m.toolStep),
  );

  // ── Auto-scroll ──
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // ── Send message ──
  const handleSend = () => {
    const text = input.trim();
    if (!text || storeLoading || !sendMessage) return;

    setInput('');
    if (collapsed) setCollapsed(false);
    sendMessage(text);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const botReady = !!botId;

  return (
    <div className={cn('flex flex-col bg-card rounded-3xl shadow-sm border border-border overflow-hidden', className)}>
      {/* Header */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center justify-between px-5 py-3 hover:bg-muted/50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-xl bg-xiaoyu-500 flex items-center justify-center shadow">
            <Robot className="h-4 w-4 text-white" />
          </div>
          <div className="text-left">
            <p className="text-sm font-bold">小宇</p>
            <p className="text-[10px] text-muted-foreground">
              {botReady ? '学习中，我一直陪着你' : '加载中...'}
            </p>
          </div>
        </div>
        {collapsed ? <CaretUp className="h-4 w-4 text-muted-foreground" /> : <CaretDown className="h-4 w-4 text-muted-foreground" />}
      </button>

      {!collapsed && (
        <>
          {/* Messages */}
          <div className="px-4 py-2 space-y-3 overflow-y-auto max-h-48">
            {messages.length === 0 && (
              <p className="text-[11px] text-muted-foreground text-center py-4">
                我是小宇～专注学习时有什么想说的，随时找我聊聊。
              </p>
            )}
            {messages.map((msg, i) => (
              <div key={i} className={cn('flex gap-2', msg.role === 'user' && 'flex-row-reverse')}>
                {msg.role === 'assistant' && (
                  <div className="h-6 w-6 rounded-lg bg-xiaoyu-100 dark:bg-xiaoyu-500/20 flex items-center justify-center shrink-0 mt-0.5">
                    <Robot className="h-3 w-3 text-xiaoyu-500" />
                  </div>
                )}
                <div className={cn(
                  'text-xs leading-relaxed rounded-2xl px-3 py-2 max-w-[80%]',
                  msg.role === 'assistant'
                    ? 'bg-muted/50 text-foreground/80 rounded-tl-sm'
                    : 'bg-xiaoyu-100 dark:bg-xiaoyu-500/20 text-foreground rounded-tr-sm'
                )}>
                  {msg.content}
                </div>
              </div>
            ))}
            {storeLoading && (
              <div className="flex gap-2">
                <div className="h-6 w-6 rounded-lg bg-xiaoyu-100 dark:bg-xiaoyu-500/20 flex items-center justify-center shrink-0 mt-0.5">
                  <Robot className="h-3 w-3 text-xiaoyu-500 animate-pulse" />
                </div>
                <div className="text-xs text-muted-foreground bg-muted/50 rounded-2xl rounded-tl-sm px-3 py-2">
                  正在思考...
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="px-3 pb-3 pt-1">
            <div className="flex items-center gap-2 bg-muted/50 rounded-2xl px-3 py-1.5">
              <input
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="和小宇聊聊..."
                className="flex-1 bg-transparent text-xs border-0 outline-none placeholder:text-muted-foreground/50"
                disabled={storeLoading || !botReady}
              />
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 rounded-xl shrink-0"
                onClick={handleSend}
                disabled={storeLoading || !input.trim() || !botReady}
              >
                <PaperPlaneTilt className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default CoachPanel;
