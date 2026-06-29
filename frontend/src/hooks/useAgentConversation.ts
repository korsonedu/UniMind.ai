import { useState, useRef, useEffect, useCallback } from 'react';
import api, { streamFetch } from '@/lib/api';
// processMathContent removed — LLM outputs LaTeX directly
import { toast } from 'sonner';
import type { AgentStep } from '@/hooks/useAgentChat';
import type { TaskListData } from '@/components/TaskList';

/** 24 hours in ms — used to decide if a session is "recent" for auto-restore */
export const RECENT_SESSION_MS = 24 * 60 * 60 * 1000;

// ── Shared interfaces ──

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
  toolStep?: AgentStep;
  visible?: boolean;
  _id?: string;
  id?: number;            // DB 主键，用于反馈等操作
  feedback?: boolean | null;  // 用户反馈：true=赞 false=踩 null=未评价
  conversation_id?: string;
  conversation_title?: string;
  metadata?: Record<string, unknown>;
}

export interface ConversationSession {
  id: number;
  label: string;
  title?: string;
  messages: Message[];
  lastTime: string;
  conversationId?: string;
}

export interface Bot {
  id: number;
  name: string;
  avatar: string | null;
  bot_type: string;
}

// ── Hook options ──

interface UseAgentConversationOptions {
  /** Find the target bot from the bots list */
  findBot: (bots: Bot[]) => Bot | undefined;
  /** Extra SSE payload fields (appended by doSend automatically) */
  getExtraPayload?: () => Record<string, unknown>;
  /** Called after SSE 'done' event (outside state updater) */
  onDone?: () => void;
  /** Pure message transform on step done (runs inside setMessages updater, no side effects) */
  onStepDone?: (step: AgentStep, prev: Message[]) => Message[] | null;
  /** Side effect after step done (runs outside setMessages updater) */
  onStepDoneEffect?: (step: AgentStep) => void;
  /** Called when a step carries question data (quick_generate) */
  onStepQuestions?: (questions: NonNullable<AgentStep['questions']>) => void;
  /** Called after done event when all_visuals metadata is present */
  onAllVisuals?: (visuals: unknown[]) => void;
  /** Success message for handleReset */
  resetMessage?: string;
  /** External conversation ID — when provided, the hook uses this instead of generating one */
  initialConversationId?: string;
}

// ── Hook ──

export function useAgentConversation(options: UseAgentConversationOptions) {
  const { findBot, resetMessage = '已开始新对话' } = options;

  // Stabilize callback refs to avoid dependency churn in doSend
  const onDoneRef = useRef(options.onDone);
  onDoneRef.current = options.onDone;
  const onStepDoneRef = useRef(options.onStepDone);
  onStepDoneRef.current = options.onStepDone;
  const onStepDoneEffectRef = useRef(options.onStepDoneEffect);
  onStepDoneEffectRef.current = options.onStepDoneEffect;
  const onStepQuestionsRef = useRef(options.onStepQuestions);
  onStepQuestionsRef.current = options.onStepQuestions;
  const onAllVisualsRef = useRef(options.onAllVisuals);
  onAllVisualsRef.current = options.onAllVisuals;
  const getExtraPayloadRef = useRef(options.getExtraPayload);
  getExtraPayloadRef.current = options.getExtraPayload;

  const [bot, setBot] = useState<Bot | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [isComposing, setIsComposition] = useState(false);
  const [initialized, setInitialized] = useState(false);
  const [skillOpen, setSkillOpen] = useState(false);
  const [sessions, setSessions] = useState<ConversationSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [sessionOpen, setSessionOpen] = useState(false);
  const [taskList, setTaskList] = useState<TaskListData | null>(null);
  const [chatWidth, setChatWidth] = useState(() => Math.min(Math.round(window.innerWidth * 0.36), 420));
  const [dragging, setDragging] = useState(false);
  const [conversationId, setConversationId] = useState<string>(
    () => options.initialConversationId || crypto.randomUUID(),
  );

  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const isDragging = useRef(false);
  const dragStartX = useRef(0);
  const dragStartWidth = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const timersRef = useRef<number[]>([]);
  const sendCountRef = useRef(0);
  const conversationIdRef = useRef(conversationId);
  conversationIdRef.current = conversationId;

  const hasConversation = activeSessionId !== null || messages.some(m => m.role === 'user');

  // ── Drag resize ──

  const handleDragStart = useCallback((e: React.MouseEvent) => {
    isDragging.current = true;
    setDragging(true);
    dragStartX.current = e.clientX;
    dragStartWidth.current = chatWidth;
    document.body.style.cursor = 'col-resize';

    const handleMouseMove = (e: MouseEvent) => {
      if (!isDragging.current) return;
      const delta = dragStartX.current - e.clientX;
      const newWidth = Math.min(Math.max(dragStartWidth.current + delta, 280), Math.round(window.innerWidth * 0.5));
      setChatWidth(newWidth);
    };

    const handleMouseUp = () => {
      isDragging.current = false;
      setDragging(false);
      document.body.style.cursor = '';
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  }, [chatWidth]);

  // ── Session grouping ──

  const groupIntoSessions = useCallback((allMessages: Message[]): ConversationSession[] => {
    if (allMessages.length === 0) return [];
    const GAP_MS = 30 * 60 * 1000;
    const groups: Message[][] = [[]];
    for (const msg of allMessages) {
      const current = groups[groups.length - 1];
      if (current.length > 0) {
        const prev = current[current.length - 1];
        const timeGap = msg.timestamp && prev.timestamp
          ? new Date(msg.timestamp).getTime() - new Date(prev.timestamp).getTime()
          : 0;
        const diffConversation = msg.conversation_id && prev.conversation_id
          && msg.conversation_id !== prev.conversation_id;
        if (diffConversation || timeGap > GAP_MS) groups.push([]);
      }
      groups[groups.length - 1].push(msg);
    }
    return groups.map((msgs, i) => {
      const title = msgs.find(m => m.conversation_title)?.conversation_title || '';
      const firstUser = msgs.find(m => m.role === 'user');
      const label = title || (firstUser ? firstUser.content.slice(0, 30) + (firstUser.content.length > 30 ? '...' : '') : '对话');
      const lastMsg = msgs[msgs.length - 1];
      return { id: i, label, title, messages: msgs, lastTime: lastMsg.timestamp || '', conversationId: lastMsg.conversation_id };
    });
  }, []);

  // ── Session management ──

  const handleLoadSession = useCallback((session: ConversationSession) => {
    setMessages(session.messages);
    setTaskList(null);
    setActiveSessionId(session.id);
    setSessionOpen(false);
    const lastMsg = session.messages[session.messages.length - 1];
    if (lastMsg?.conversation_id) {
      setConversationId(lastMsg.conversation_id);
    }
  }, []);

  /** 恢复历史消息中 metadata 的 visual 到 toolStep，确保侧栏切换时卡片不消失 */
  const restoreVisualsFromMetadata = useCallback((msgs: Message[]): Message[] => {
    return msgs.map((m) => {
      const meta = (m as any).metadata;
      const visuals = meta?.all_visuals || (meta?.visual ? [meta.visual] : null);
      if (!visuals || visuals.length === 0) return m;
      const v = visuals[0];
      const msg = { ...m };
      if (msg.toolStep) {
        if (msg.toolStep.name === 'render_visual' && msg.toolStep.status === 'done' && !msg.toolStep.visual) {
          msg.toolStep = { ...msg.toolStep, visual: v };
        }
      } else {
        msg.toolStep = {
          call_id: `hist-${m.id || 0}`,
          step: 0,
          name: 'render_visual',
          status: 'done',
          label: (v.payload as any)?.title || '可视化',
          visual: v,
          args_summary: '',
          result_summary: '',
        };
      }
      if (msg.metadata) {
        delete (msg.metadata as any).visual;
        delete (msg.metadata as any).all_visuals;
      }
      return msg;
    });
  }, []);

  const handleRefreshSessions = useCallback(async () => {
    if (!bot) return;
    try {
      const hRes = await api.get('/ai/history/', { params: { bot_id: bot.id } });
      if (hRes.data.length > 0) {
        const allMsgs: Message[] = hRes.data
          .filter((m: Record<string, unknown>) => m.content !== '[Thinking...]')
          .map((m: Record<string, unknown>) => ({
            ...m,
            content: m.content as string,
            visible: true,
          }));
        setSessions(groupIntoSessions(restoreVisualsFromMetadata(allMsgs)));
      }
    } catch (e) { console.error('[useAgentConversation] history fetch failed:', e); }
  }, [bot, groupIntoSessions, restoreVisualsFromMetadata]);

  const handleDeleteSession = useCallback(async (session: ConversationSession) => {
    if (!session.conversationId) return;
    try {
      await api.post('/ai/delete-conversation/', { conversation_id: session.conversationId });
      setSessions(prev => prev.filter(s => s.id !== session.id));
      if (activeSessionId === session.id) {
        setMessages([]);
        setTaskList(null);
        setActiveSessionId(null);
        setConversationId(crypto.randomUUID());
      }
      toast.success('对话已删除');
    } catch {
      toast.error('删除失败，请重试');
    }
  }, [activeSessionId]);

  // ── Auto-scroll ──

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  // ── SSE streaming ──

  const doSend = useCallback(async (text: string, silent: boolean = false) => {
    if (!bot) return;

    // Abort any in-flight request
    if (abortRef.current) abortRef.current.abort();
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];

    const controller = new AbortController();
    abortRef.current = controller;
    const currentSend = ++sendCountRef.current;

    setLoading(true);

    let msgId = 0;
    const nextId = () => `msg_${++msgId}_${Date.now()}`;

    if (!silent) {
      const userMsg: Message = { _id: nextId(), role: 'user', content: text, timestamp: new Date().toISOString() };
      setMessages(prev => [...prev, userMsg]);
    }
    setInput('');

    try {
      const { url, init } = streamFetch('/api/ai/chat/stream/', {
        message: text,
        bot_id: bot.id,
        conversation_id: conversationIdRef.current,
        ...(getExtraPayloadRef.current?.() ?? {}),
      }, controller.signal);
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
          setMessages(prev => prev.map(m => m._id === id ? { ...m, visible: true } : m));
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
              setMessages(prev => [...prev, {
                _id: id,
                role: 'assistant' as const,
                content: payload.content,
                visible: false,
                timestamp: new Date().toISOString(),
              }]);
              // scheduleShow 在 updater 外调用，用 rAF 确保 DOM 更新
              requestAnimationFrame(() => {
                setMessages(prev => {
                  const pos = prev.findIndex(m => m._id === id);
                  if (pos >= 0) scheduleShow(id, pos);
                  return prev;
                });
              });
            } else if (payload.type === 'step') {
              const step = payload as AgentStep;

              // batch_start: initialize task list (UI-only, not a message)
              if (step.status === 'batch_start' && step.task_list?.items) {
                setTaskList({
                  task_id: step.task_list.task_id,
                  items: step.task_list.items,
                });
                continue;
              }

              // Incremental task_list update (done events with task_list.update)
              if (step.task_list?.update) {
                setTaskList(prev => {
                  if (!prev || prev.task_id !== step.task_list!.task_id) return prev;
                  return {
                    ...prev,
                    items: prev.items.map(item =>
                      item.id === step.task_list!.update!.id
                        ? { ...item, status: step.task_list!.update!.status, duration_ms: step.task_list!.update!.duration_ms ?? item.duration_ms }
                        : item,
                    ),
                  };
                });
              }

              // render_visual 的 visual 数据由下方 step.status 块统一处理：
              //   calling → 创建带 toolStep 的消息，scheduleShow 淡入
              //   done    → 更新 toolStep（含 visual），AgentChatLayout 根据 toolStep.visual 渲染 InlineVisualCard
              if (step.status === 'calling') {
                setMessages(prev => {
                  // 同一 call_id 已存在则更新（进度事件），否则新建
                  const existingIdx = prev.findIndex(m => m.toolStep?.call_id === step.call_id);
                  if (existingIdx >= 0) {
                    const updated = [...prev];
                    updated[existingIdx] = { ...updated[existingIdx], toolStep: step };
                    return updated;
                  }
                  const id = nextId();
                  scheduleShow(id, prev.length);
                  return [...prev, {
                    _id: id,
                    role: 'assistant' as const,
                    content: '',
                    toolStep: step,
                    visible: false,
                    timestamp: new Date().toISOString(),
                  }];
                });
              } else if (step.status === 'done') {
                if (onStepDoneRef.current) {
                  setMessages(prev => onStepDoneRef.current!(step, prev) || prev);
                } else {
                  setMessages(prev => prev.map(m =>
                    m.toolStep?.call_id === step.call_id ? { ...m, toolStep: step } : m
                  ));
                }
                onStepDoneEffectRef.current?.(step);
                if (step.questions?.length) {
                  onStepQuestionsRef.current?.(step.questions);
                }
              }
            } else if (payload.type === 'text_delta') {
              // Ignore streaming text, wait for final done event
            } else if (payload.type === 'error') {
              toast.error(payload.message || 'AI 调用失败');
            } else if (payload.done) {
              const finalContent = payload.full_content || '';
              if (payload.is_error) {
                toast.error(finalContent || 'AI 调用失败');
              } else if (finalContent) {
                // 最终消息也通过 scheduleShow 排队，确保出现在中间消息和 tool steps 之后
                const id = nextId();
                setMessages(prev => [...prev, {
                  _id: id,
                  id: payload.message_id,
                  role: 'assistant' as const,
                  content: finalContent,
                  conversation_title: payload.conversation_title || undefined,
                  metadata: payload.metadata || undefined,
                  visible: false,
                  timestamp: new Date().toISOString(),
                }]);
                requestAnimationFrame(() => {
                  setMessages(prev => {
                    const pos = prev.findIndex(m => m._id === id);
                    if (pos >= 0) scheduleShow(id, pos);
                    return prev;
                  });
                });
              } else if (payload.has_intermediate) {
                // 中间消息已展示全部内容，不需空最终气泡
              }
              // Notify parent about visuals from done event metadata
              const doneVisuals = payload.metadata?.all_visuals || (payload.metadata?.visual ? [payload.metadata.visual] : []);
              if (doneVisuals.length) {
                onAllVisualsRef.current?.(doneVisuals);
              }
              if (currentSend === sendCountRef.current) {
                setLoading(false);
              }
              onDoneRef.current?.();
            } else if (payload.error) {
              toast.error(payload.error);
            }
          } catch { /* skip malformed SSE lines */ }
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      const msg = err instanceof Error ? err.message : '发送失败，请重试';
      toast.error(msg.includes('HTTP') ? '服务暂时不可用，请稍后再试' : '发送失败，请重试');
      setInput(text);
    } finally {
      // 清除未触发的 scheduleShow 定时器，同时让所有消息立即可见
      timersRef.current.forEach(clearTimeout);
      timersRef.current = [];
      setMessages(prev => prev.map(m => m.visible === false ? { ...m, visible: true } : m));
      // Only clear loading if no newer request has started
      if (currentSend === sendCountRef.current) {
        setLoading(false);
      }
    }
  }, [bot, activeSessionId]);

  // ── Handlers ──

  const handleReset = useCallback(() => {
    if (!bot) return;
    if (abortRef.current) abortRef.current.abort();
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
    setMessages([]);
    setTaskList(null);
    setActiveSessionId(null);
    setConversationId(crypto.randomUUID());
    toast.success(resetMessage);
  }, [bot, resetMessage]);

  const handleSkillSelect = useCallback((prompt: string) => {
    setInput(prompt);
    setSkillOpen(false);
    setTimeout(() => inputRef.current?.focus(), 0);
  }, []);

  // ── Cleanup on unmount ──

  useEffect(() => {
    return () => {
      if (abortRef.current) abortRef.current.abort();
      timersRef.current.forEach(clearTimeout);
    };
  }, []);

  return {
    // State
    bot,
    messages,
    input,
    loading,
    isComposing,
    initialized,
    skillOpen,
    sessions,
    activeSessionId,
    sessionOpen,
    chatWidth,
    dragging,
    hasConversation,
    conversationId,
    taskList,

    // Refs
    scrollRef,
    inputRef,

    // Setters
    setMessages,
    setInput,
    setBot,
    setInitialized,
    setSkillOpen,
    setSessionOpen,
    setIsComposition,
    setActiveSessionId,
    setSessions,
    setChatWidth,
    setConversationId,

    // Handlers
    handleDragStart,
    handleLoadSession,
    handleRefreshSessions,
    handleDeleteSession,
    handleReset,
    handleSkillSelect,
    doSend,
    groupIntoSessions,

    // Convenience
    findBot,
  };
}
