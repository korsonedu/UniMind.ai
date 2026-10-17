import { useEffect, useRef, useCallback } from 'react';
import api, { streamFetch } from '@/lib/api';
import { upsertChatMessage } from '@/lib/chatMessages';
import { toast } from 'sonner';
import type { XiaoYuMessage } from '@/store/useXiaoYuStore';
import type { Bot } from '@/types/api';
import { useXiaoYuStore } from '@/store/useXiaoYuStore';
import { upsertToolStepMessage, type AgentStep } from '@/types/toolRun';

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
  const botIdRef = useRef(botId);

  useEffect(() => {
    conversationIdRef.current = conversationId;
    botIdRef.current = botId;
  }, [conversationId, botId]);

  // ── Fetch 小宇 bot on mount ──
  useEffect(() => {
    if (!enabled) return;
    api.get('/ai/bots/')
      .then((r) => {
        const bots = Array.isArray(r.data) ? r.data : (r.data?.results || []);
        const xiaoyu = bots.find((b: Bot) => b.bot_type === 'planner');
        if (xiaoyu) setBotId(xiaoyu.id);
      })
      .catch(() => {});
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
    let streamingId: string | null = null;
    let streamingContent = '';

    // Add user message
    const userMsg = {
      _id: nextId(),
      role: 'user' as const,
      content: text,
      visible: true,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev: XiaoYuMessage[]) => [...prev, userMsg]);

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
          setMessages((prev: XiaoYuMessage[]) =>
            prev.map((m: XiaoYuMessage) => (m._id === id ? { ...m, visible: true } : m)),
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
              if (streamingId) {
                const id = streamingId;
                setMessages((prev: XiaoYuMessage[]) => upsertChatMessage(prev, {
                  _id: id, role: 'assistant', content: payload.content,
                  visible: true, timestamp: new Date().toISOString(),
                }));
                streamingId = null;
                streamingContent = '';
                continue;
              }
              const id = nextId();
              setMessages((prev: XiaoYuMessage[]) => [
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
                setMessages((prev: XiaoYuMessage[]) => {
                  const pos = prev.findIndex((m: XiaoYuMessage) => m._id === id);
                  if (pos >= 0) scheduleShow(id, pos);
                  return prev;
                });
              });
            } else if (payload.type === 'step') {
              const step = payload as AgentStep;
              setMessages((prev: XiaoYuMessage[]) => upsertToolStepMessage(
                prev,
                step,
                currentStep => {
                  const id = nextId();
                  scheduleShow(id, prev.length);
                  return {
                    _id: id,
                    role: 'assistant' as const,
                    content: '',
                    toolStep: currentStep,
                    visible: false,
                    timestamp: new Date().toISOString(),
                  };
                },
              ));
            } else if (payload.type === 'text_delta') {
              if (!payload.delta) continue;
              streamingId ??= nextId();
              streamingContent += payload.delta;
              const message: XiaoYuMessage = {
                _id: streamingId, role: 'assistant', content: streamingContent,
                visible: true, timestamp: new Date().toISOString(),
              };
              setMessages((prev: XiaoYuMessage[]) => upsertChatMessage(prev, message));
            } else if (payload.type === 'error') {
              toast.error(payload.message || 'AI 调用失败');
            } else if (payload.done) {
              const finalContent = payload.full_content || '';
              if (payload.is_error) {
                toast.error(finalContent || 'AI 调用失败');
              } else if (finalContent && streamingId) {
                const id = streamingId;
                setMessages((prev: XiaoYuMessage[]) => upsertChatMessage(prev, {
                  _id: id, id: payload.message_id, role: 'assistant',
                  content: finalContent, visible: true, timestamp: new Date().toISOString(),
                  conversation_title: payload.conversation_title || undefined,
                  metadata: payload.metadata || undefined,
                }));
                streamingId = null;
                streamingContent = '';
              } else if (finalContent) {
                const id = nextId();
                setMessages((prev: XiaoYuMessage[]) => [
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
                  setMessages((prev: XiaoYuMessage[]) => {
                    const pos = prev.findIndex((m: XiaoYuMessage) => m._id === id);
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
      setMessages((prev: XiaoYuMessage[]) =>
        prev.map((m: XiaoYuMessage) =>
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
    setSendMessage((text: string) => { send(text); });
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
