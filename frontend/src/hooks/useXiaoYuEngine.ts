import { useEffect, useRef, useCallback } from 'react';
import api from '@/lib/api';
import { upsertChatMessage } from '@/lib/chatMessages';
import { readChatStream } from '@/lib/chatStream';
import { createRevealQueue } from '@/lib/chatReveal';
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
  const revealRef = useRef<ReturnType<typeof createRevealQueue> | null>(null);
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
    revealRef.current?.dispose();
    revealRef.current = null;

    const controller = new AbortController();
    abortRef.current = controller;
    const currentSend = ++sendCountRef.current;
    const requestConversationId = conversationIdRef.current;
    const isCurrent = () => !controller.signal.aborted
      && currentSend === sendCountRef.current
      && requestConversationId === conversationIdRef.current;

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

    const reveal = createRevealQueue({
      isActive: isCurrent,
      onReveal: (id) => {
        setMessages((prev: XiaoYuMessage[]) =>
          prev.map((m: XiaoYuMessage) => (m._id === id ? { ...m, visible: true } : m)),
        );
      },
    });
    revealRef.current = reveal;

    try {
      for await (const payload of readChatStream({
        body: {
          request_id: crypto.randomUUID(),
          message: text,
          bot_id: bid,
          conversation_id: requestConversationId,
        },
        signal: controller.signal,
        isCurrent,
      })) {
        if (!isCurrent()) return;
        try {
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
                if (!isCurrent()) return;
                setMessages((prev: XiaoYuMessage[]) => {
                  const pos = prev.findIndex((m: XiaoYuMessage) => m._id === id);
                  if (pos >= 0) reveal.schedule(id, pos);
                  return prev;
                });
              });
            } else if (payload.type === 'step') {
              const step = payload as AgentStep;
              setMessages((prev: XiaoYuMessage[]) => upsertToolStepMessage(
                prev,
                step,
                currentStep => ({
                  _id: nextId(),
                  role: 'assistant' as const,
                  content: '',
                  toolStep: currentStep,
                  visible: false,
                  timestamp: new Date().toISOString(),
                }),
              ));
              requestAnimationFrame(() => {
                if (!isCurrent()) return;
                setMessages((prev: XiaoYuMessage[]) => {
                  const pos = prev.findIndex((m: XiaoYuMessage) => m.toolStep?.call_id === step.call_id);
                  const targetId = pos >= 0 ? prev[pos]._id : undefined;
                  if (targetId) reveal.schedule(targetId, pos);
                  return prev;
                });
              });
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
                  if (!isCurrent()) return;
                  setMessages((prev: XiaoYuMessage[]) => {
                    const pos = prev.findIndex((m: XiaoYuMessage) => m._id === id);
                    if (pos >= 0) reveal.schedule(id, pos);
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
          /* skip malformed SSE events */
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      const msg =
        err instanceof Error ? err.message : '发送失败，请重试';
      toast.error(
        msg.includes('HTTP') || err instanceof TypeError
          ? '服务暂时不可用，请稍后再试'
          : msg,
      );
    } finally {
      reveal.dispose();
      if (revealRef.current === reveal) revealRef.current = null;
      if (isCurrent()) {
        setMessages((prev: XiaoYuMessage[]) =>
          prev.map((m: XiaoYuMessage) =>
            m.visible === false ? { ...m, visible: true } : m,
          ),
        );
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
      revealRef.current?.dispose();
    };
  }, []);

  return { send };
}
