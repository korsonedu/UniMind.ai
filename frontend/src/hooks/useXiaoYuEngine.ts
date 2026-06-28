import { useEffect, useRef, useCallback } from 'react';
import { streamFetch } from '@/lib/api';
import { toast } from 'sonner';
import { useXiaoYuStore } from '@/store/useXiaoYuStore';
import type { AgentStep } from '@/hooks/useAgentChat';

interface UseXiaoYuEngineOptions {
  enabled: boolean;
}

/**
 * App 层 SSE 引擎 — 挂载在 App.tsx，路由切换不中断。
 * XiaoYu.tsx 和 CoachPanel.tsx 共享同一个 conversation。
 */
export function useXiaoYuEngine({ enabled }: UseXiaoYuEngineOptions) {
  const botId = useXiaoYuStore((s) => s.botId);
  const conversationId = useXiaoYuStore((s) => s.conversationId);
  const setMessages = useXiaoYuStore((s) => s.setMessages);
  const setLoading = useXiaoYuStore((s) => s.setLoading);
  const setBotId = useXiaoYuStore((s) => s.setBotId);
  const setSendMessage = useXiaoYuStore((s) => s.setSendMessage);
  const abortRef = useRef<AbortController | null>(null);
  const timersRef = useRef<number[]>([]);
  const sendCountRef = useRef(0);
  const conversationIdRef = useRef(conversationId);
  conversationIdRef.current = conversationId;
  const botIdRef = useRef(botId);
  botIdRef.current = botId;

  // ── Fetch 小宇 bot on mount ──
  useEffect(() => {
    if (!enabled) return;
    import('@/lib/api').then(({ default: api }) => {
      api.get('/ai/bots/')
        .then((r) => {
          const bots = Array.isArray(r.data) ? r.data : (r.data?.results || []);
          const xiaoyu = bots.find((b: any) => b.bot_type === 'planner');
          if (xiaoyu) setBotId(xiaoyu.id);
        })
        .catch(() => {});
    });
  }, [enabled, setBotId]);

  // ── Send ──
  const send = useCallback(async (text: string) => {
    const bid = botIdRef.current;
    if (!bid) return;

    if (abortRef.current) abortRef.current.abort();
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];

    const controller = new AbortController();
    abortRef.current = controller;
    const currentSend = ++sendCountRef.current;

    setLoading(true);

    let msgId = 0;
    const nextId = () => `msg_${++msgId}_${Date.now()}`;

    // Add user message
    const userMsg = {
      _id: nextId(),
      role: 'user' as const,
      content: text,
      visible: true,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev: any) => [...prev, userMsg]);

    try {
      const { url, init } = streamFetch(
        '/api/ai/chat/stream/',
        {
          message: text,
          bot_id: bid,
          conversation_id: conversationIdRef.current,
        },
        controller.signal,
      );
      const res = await fetch(url, init);

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader = res.body?.getReader();
      if (!reader) throw new Error('Stream not available');

      const decoder = new TextDecoder();
      let leftover = '';
      const shownCount = { current: 0 };
      const STEP_DELAY_MS = 600;

      function scheduleShow(id: string, pos: number) {
        const delay = Math.max(0, pos - shownCount.current) * STEP_DELAY_MS;
        const timerId = window.setTimeout(() => {
          shownCount.current = Math.max(shownCount.current, pos + 1);
          setMessages((prev: any) =>
            prev.map((m: any) => (m._id === id ? { ...m, visible: true } : m)),
          );
        }, delay);
        timersRef.current.push(timerId);
      }

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        leftover += decoder.decode(value, { stream: true });
        const lines = leftover.split('\n');
        leftover = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const payload = JSON.parse(line.slice(6));

            if (payload.type === 'message' && payload.content) {
              const id = nextId();
              setMessages((prev: any) => [
                ...prev,
                {
                  _id: id,
                  role: 'assistant' as const,
                  content: payload.content,
                  visible: false,
                  timestamp: new Date().toISOString(),
                },
              ]);
              requestAnimationFrame(() => {
                setMessages((prev: any) => {
                  const pos = prev.findIndex((m: any) => m._id === id);
                  if (pos >= 0) scheduleShow(id, pos);
                  return prev;
                });
              });
            } else if (payload.type === 'step') {
              const step = payload as AgentStep;

              if (step.status === 'calling') {
                setMessages((prev: any) => {
                  const existingIdx = prev.findIndex(
                    (m: any) => m.toolStep?.call_id === step.call_id,
                  );
                  if (existingIdx >= 0) {
                    const updated = [...prev];
                    updated[existingIdx] = {
                      ...updated[existingIdx],
                      toolStep: step,
                    };
                    return updated;
                  }
                  const id = nextId();
                  scheduleShow(id, prev.length);
                  return [
                    ...prev,
                    {
                      _id: id,
                      role: 'assistant' as const,
                      content: '',
                      toolStep: step,
                      visible: false,
                      timestamp: new Date().toISOString(),
                    },
                  ];
                });
              } else if (step.status === 'done') {
                setMessages((prev: any) =>
                  prev.map((m: any) =>
                    m.toolStep?.call_id === step.call_id
                      ? { ...m, toolStep: step }
                      : m,
                  ),
                );
              }
            } else if (payload.type === 'error') {
              toast.error(payload.message || 'AI 调用失败');
            } else if (payload.done) {
              const finalContent = payload.full_content || '';
              if (payload.is_error) {
                toast.error(finalContent || 'AI 调用失败');
              } else if (finalContent) {
                const id = nextId();
                setMessages((prev: any) => [
                  ...prev,
                  {
                    _id: id,
                    id: payload.message_id,
                    role: 'assistant' as const,
                    content: finalContent,
                    conversation_title:
                      payload.conversation_title || undefined,
                    metadata: payload.metadata || undefined,
                    visible: false,
                    timestamp: new Date().toISOString(),
                  },
                ]);
                requestAnimationFrame(() => {
                  setMessages((prev: any) => {
                    const pos = prev.findIndex((m: any) => m._id === id);
                    if (pos >= 0) scheduleShow(id, pos);
                    return prev;
                  });
                });
              }
              if (currentSend === sendCountRef.current) {
                setLoading(false);
              }
            } else if (payload.error) {
              toast.error(payload.error);
            }
          } catch {
            /* skip malformed SSE lines */
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      const msg =
        err instanceof Error ? err.message : '发送失败，请重试';
      toast.error(
        msg.includes('HTTP')
          ? '服务暂时不可用，请稍后再试'
          : '发送失败，请重试',
      );
    } finally {
      timersRef.current.forEach(clearTimeout);
      timersRef.current = [];
      setMessages((prev: any) =>
        prev.map((m: any) =>
          m.visible === false ? { ...m, visible: true } : m,
        ),
      );
      if (currentSend === sendCountRef.current) {
        setLoading(false);
      }
    }
  }, [setMessages, setLoading]);

  // ── Register send in store for CoachPanel access ──
  useEffect(() => {
    setSendMessage(() => send);
    return () => setSendMessage(null);
  }, [send, setSendMessage]);

  // ── Cleanup on unmount ──
  useEffect(() => {
    return () => {
      if (abortRef.current) abortRef.current.abort();
      timersRef.current.forEach(clearTimeout);
    };
  }, []);

  return { send };
}
