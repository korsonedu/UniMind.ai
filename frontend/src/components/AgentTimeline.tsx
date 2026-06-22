/**
 * Agent 时间线组件 — 替代聊天 UI，渲染 Agent 的时间线式消息流。
 *
 * 三种消息类型：
 * - Agent 消息（AI 主动推送/响应）：全宽卡片
 * - 用户消息：紧凑的时间线条目
 * - 结构化卡片：AgentStepCard（工具步骤）、DataCard（数据）、DecisionCard（决策）
 */
import React, { useRef, useEffect } from 'react';
import { MarkdownContent } from '@/components/MarkdownContent';
import { cn } from '@/lib/utils';
import { AgentStepCard } from '@/components/AgentStepCard';
import { InlineVisualCard } from '@/components/InlineVisualCard';
import type { VisualData } from '@/pages/xiaoyu/visuals';

export interface TimelineMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  /** 工具调用步骤（来自 Agent） */
  toolStep?: {
    call_id: string;
    step: number;
    status: 'calling' | 'done';
    name: string;
    label: string;
    args_summary?: string;
    result_summary?: string;
    visual?: { type: string; payload: any };
  };
  /** 是否为 Agent 主动推送 */
  isPush?: boolean;
  /** 消息 metadata */
  metadata?: Record<string, unknown>;
}

interface Props {
  messages: TimelineMessage[];
  streamingText?: string;
  isStreaming?: boolean;
  /** 用户头像 URL */
  userAvatar?: string;
  /** 用户姓名首字母 */
  userInitial?: string;
  className?: string;
}

export function AgentTimeline({
  messages,
  streamingText,
  isStreaming,
  userAvatar,
  userInitial,
  className,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingText]);

  const formatTime = (ts: string) => {
    try {
      const d = new Date(ts);
      return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    } catch {
      return '';
    }
  };

  return (
    <div className={cn("flex-1 overflow-y-auto px-4 py-6 space-y-4", className)}>
      {messages.filter(m => m.role === 'user' || m.content || m.toolStep).map((msg, i) => {
        const prevTime = i > 0 ? messages[i - 1]?.timestamp : null;
        const showTimestamp = !prevTime || (() => {
          try {
            return new Date(msg.timestamp).getTime() - new Date(prevTime).getTime() > 300_000;
          } catch { return true; }
        })();

        if (msg.role === 'user') {
          // 用户消息：紧凑条目
          return (
            <div key={msg.id}>
              {showTimestamp && (
                <div className="flex items-center gap-3 mb-3">
                  <div className="flex-1 h-px bg-border" />
                  <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">
                    {formatTime(msg.timestamp)}
                  </span>
                  <div className="flex-1 h-px bg-border" />
                </div>
              )}
              <div className="flex items-start gap-3 pl-12">
                <div className="w-6 h-6 rounded-full bg-muted flex items-center justify-center shrink-0 mt-0.5">
                  <span className="text-[10px] font-bold text-muted-foreground">
                    {userInitial || '我'}
                  </span>
                </div>
                <div className="text-sm text-muted-foreground pt-0.5">{msg.content}</div>
              </div>
            </div>
          );
        }

        // Agent 消息：全宽卡片
        return (
          <div key={msg.id}>
            {showTimestamp && (
              <div className="flex items-center gap-3 mb-3">
                <div className="flex-1 h-px bg-border" />
                <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">
                  {formatTime(msg.timestamp)}
                </span>
                <div className="flex-1 h-px bg-border" />
              </div>
            )}
            {/* 工具步骤卡片 */}
            {msg.toolStep && (
              <AgentStepCard step={msg.toolStep} />
            )}
            {/* render_visual 可视化 */}
            {msg.toolStep?.status === 'done' && msg.toolStep.visual && (
              <InlineVisualCard visual={msg.toolStep.visual as VisualData} />
            )}
            {/* 文本内容（Agent 说的文字） */}
            {msg.content && (
              <div className={cn(
                "bg-card/50 border border-border rounded-xl p-4 prose prose-sm dark:prose-invert max-w-none",
                msg.isPush && "border-primary/30 bg-primary/5",
              )}>
                <div className="text-sm leading-relaxed prose-code:bg-muted prose-pre:bg-muted">
                  <MarkdownContent content={msg.content
                      .replace(/\\\(/g, '$')
                      .replace(/\\\)/g, '$')
                    } />
                </div>
              </div>
            )}
          </div>
        );
      })}

      {/* 流式文本 */}
      {streamingText && isStreaming && (
        <div className="bg-card/50 border border-border rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
            <span className="text-[11px] font-bold text-muted-foreground uppercase">AI 思考中</span>
          </div>
          <div className="text-sm leading-relaxed text-muted-foreground">{streamingText}</div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
