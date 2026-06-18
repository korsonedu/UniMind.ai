/**
 * 工作台 — AI 助手对话面板。
 * SSE 流式对话，bot_type=exam_generator。
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import { Spinner, PaperPlaneTilt, Brain, User } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { AgentStepCard } from '@/components/AgentStepCard';
import { InlineVisualCard } from '@/components/InlineVisualCard';
import { AgentReplyContext } from '@/pages/xiaoyu/visuals/ActionCardsRenderer';
import type { AgentStep } from '@/hooks/useAgentChat';
import type { VisualData } from '@/pages/xiaoyu/visuals';
import api from '@/lib/api';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export function CopilotPanel() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const upsertStep = useCallback((prev: AgentStep[], event: AgentStep): AgentStep[] => {
    const idx = prev.findIndex(s => s.call_id === event.call_id);
    if (idx >= 0) {
      const updated = [...prev];
      updated[idx] = { ...updated[idx], ...event };
      return updated;
    }
    return [...prev, event];
  }, []);

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      if (scrollRef.current) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      }
    });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingText, scrollToBottom]);

  const doSend = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || streaming) return;

    const userMsg: ChatMessage = { role: 'user', content: trimmed };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setStreaming(true);
    setStreamingText('');
    setSteps([]);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const response = await fetch('/api/ai/chat/stream/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
          'X-CSRFToken': getCsrfToken(),
        },
        credentials: 'include',
        body: JSON.stringify({
          message: trimmed,
          bot_type: 'exam_generator',
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let fullContent = '';
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data === '[DONE]') continue;
            try {
              const parsed = JSON.parse(data);
              if (parsed.type === 'text_delta' && parsed.delta) {
                fullContent += parsed.delta;
                setStreamingText(fullContent);
              } else if (parsed.type === 'step') {
                setSteps(prev => upsertStep(prev, parsed as AgentStep));
              } else if (parsed.type === 'message' && parsed.content) {
                fullContent = parsed.content;
                setStreamingText(fullContent);
              } else if (parsed.type === 'done') {
                fullContent = parsed.full_content || fullContent;
                setStreamingText(fullContent);
              } else if (parsed.type === 'error') {
                toast.error(parsed.message || 'AI 响应错误');
              }
            } catch {
              // Non-JSON line, treat as raw delta
              if (data) {
                fullContent += data;
                setStreamingText(fullContent);
              }
            }
          }
        }
      }

      // Flush remaining buffer
      if (buffer.startsWith('data: ')) {
        const data = buffer.slice(6);
        if (data && data !== '[DONE]') {
          try {
            const parsed = JSON.parse(data);
            if (parsed.type === 'done') {
              fullContent = parsed.full_content || fullContent;
            } else if (parsed.delta) {
              fullContent += parsed.delta;
            }
          } catch {
            fullContent += data;
          }
        }
      }

      setMessages((prev) => [...prev, { role: 'assistant', content: fullContent }]);
      setStreamingText('');
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        // User cancelled — keep partial streaming text if any
        if (streamingText) {
          setMessages((prev) => [...prev, { role: 'assistant', content: streamingText }]);
          setStreamingText('');
        }
      } else {
        toast.error('对话请求失败，请稍后重试');
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }, [streaming, streamingText]);

  const handleSend = () => doSend(input);

  const onReply = useCallback((value: string) => {
    doSend(value);
  }, [doSend]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleCancel = () => {
    abortRef.current?.abort();
  };

  return (
    <div className="flex flex-col h-full max-w-3xl mx-auto">
      {/* Messages area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-4 min-h-0">
        {messages.length === 0 && !streaming && (
          <div className="flex flex-col items-center justify-center py-16 space-y-3 text-muted-foreground">
            <Brain className="h-10 w-10 text-muted-foreground/30" />
            <p className="text-sm">工作台 AI 助手</p>
            <p className="text-xs text-muted-foreground/60">可以帮你出题、查数据、管理作业</p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={cn('flex gap-3', msg.role === 'user' ? 'justify-end' : 'justify-start')}
          >
            {msg.role === 'assistant' && (
              <div className="h-7 w-7 rounded-full bg-primary/10 flex items-center justify-center shrink-0 mt-0.5">
                <Brain className="h-3.5 w-3.5 text-primary" />
              </div>
            )}
            <div
              className={cn(
                'max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap',
                msg.role === 'user'
                  ? 'bg-primary text-primary-foreground rounded-br-md'
                  : 'bg-muted rounded-bl-md'
              )}
            >
              {msg.content}
            </div>
            {msg.role === 'user' && (
              <div className="h-7 w-7 rounded-full bg-muted flex items-center justify-center shrink-0 mt-0.5">
                <User className="h-3.5 w-3.5 text-muted-foreground" />
              </div>
            )}
          </div>
        ))}

        {/* Tool call steps */}
        <AgentReplyContext.Provider value={{ onReply }}>
          {steps.length > 0 && (
            <div className="flex flex-col items-start gap-1.5 px-1">
              {steps.map((step, i) => (
                <div key={step.call_id} className="flex flex-col gap-1.5 w-full animate-in fade-in slide-in-from-bottom-1 duration-300">
                  <div className="flex gap-3 w-full">
                    <div className="h-7 w-7 rounded-full bg-primary/10 flex items-center justify-center shrink-0 mt-1">
                      <Brain className="h-3.5 w-3.5 text-primary" />
                    </div>
                    <div className="max-w-[80%]">
                      <AgentStepCard step={step} compact />
                    </div>
                  </div>
                  {step.status === 'done' && step.visual && (
                    <InlineVisualCard visual={step.visual as VisualData} index={i} />
                  )}
                </div>
              ))}
            </div>
          )}
        </AgentReplyContext.Provider>

        {/* Streaming message */}
        {streaming && streamingText && (
          <div className="flex gap-3 justify-start">
            <div className="h-7 w-7 rounded-full bg-primary/10 flex items-center justify-center shrink-0 mt-0.5">
              <Brain className="h-3.5 w-3.5 text-primary" />
            </div>
            <div className="max-w-[80%] rounded-2xl rounded-bl-md px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap bg-muted">
              {streamingText}
              <span className="inline-block w-1.5 h-4 ml-0.5 bg-primary animate-pulse rounded-sm align-middle" />
            </div>
          </div>
        )}

        {streaming && !streamingText && (
          <div className="flex gap-3 justify-start">
            <div className="h-7 w-7 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
              <Brain className="h-3.5 w-3.5 text-primary" />
            </div>
            <div className="bg-muted rounded-2xl rounded-bl-md px-4 py-3">
              <Spinner className="h-4 w-4 animate-spin text-muted-foreground" />
            </div>
          </div>
        )}
      </div>

      {/* Input area */}
      <div className="border-t border-border px-4 py-3 bg-card">
        <div className="flex items-end gap-2">
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入消息..."
            rows={2}
            disabled={streaming}
            className="min-h-[44px] resize-none"
          />
          {streaming ? (
            <Button variant="outline" size="icon" onClick={handleCancel} className="shrink-0">
              <Spinner className="h-4 w-4 animate-spin" />
            </Button>
          ) : (
            <Button
              size="icon"
              onClick={handleSend}
              disabled={!input.trim()}
              className="shrink-0"
            >
              <PaperPlaneTilt className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

/** Read CSRF token from cookie */
function getCsrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/);
  return match ? match[1] : '';
}
