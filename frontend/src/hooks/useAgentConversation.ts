import type { VisualData } from '@/pages/xiaoyu/visuals';
import { useState, useRef, useEffect, useCallback } from 'react';
import api from '@/lib/api';
import { upsertChatMessage } from '@/lib/chatMessages';
import { readChatStream } from '@/lib/chatStream';
import { createRevealQueue } from '@/lib/chatReveal';
import { restoreVisualSteps } from '@/lib/visualHistory';
// processMathContent removed — LLM outputs LaTeX directly
import { toast } from 'sonner';
import {
  completeToolRun,
  reduceToolRun,
  type AgentStep,
  type TaskListData,
} from '@/types/toolRun';

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
  conversation_project?: number | null;
  conversation_pinned?: boolean;
  metadata?: Record<string, unknown> & { visual?: VisualData; all_visuals?: VisualData[] };
}

export interface ConversationSession {
  id: number;
  label: string;
  title?: string;
  messages: Message[];
  lastTime: string;
  conversationId?: string;
  projectId?: number | null;
  isPinned?: boolean;
}

export interface ConversationPatch { title?: string; is_pinned?: boolean; project_id?: number | null; }

export interface Bot {
  id: number;
  name: string;
  avatar: string | null;
  bot_type: string;
}

// ── Hook options ──

interface UseAgentConversationOptions {
  enableProjects?: boolean;
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
  const onStepDoneRef = useRef(options.onStepDone);
  const onStepDoneEffectRef = useRef(options.onStepDoneEffect);
  const onStepQuestionsRef = useRef(options.onStepQuestions);
  const onAllVisualsRef = useRef(options.onAllVisuals);
  const getExtraPayloadRef = useRef(options.getExtraPayload);

  const [bot, setBot] = useState<Bot | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [isComposing, setIsComposition] = useState(false);
  const [initialized, setInitialized] = useState(false);
  const [skillOpen, setSkillOpen] = useState(false);
  const [sessions, setSessions] = useState<ConversationSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [projectId, updateProjectId] = useState<number | null>(null);
  const projectIdRef = useRef(projectId);
  const setProjectId = useCallback((value: React.SetStateAction<number | null>) => {
    const next = typeof value === 'function' ? value(projectIdRef.current) : value;
    projectIdRef.current = next;
    updateProjectId(next);
  }, []);
  const [sessionOpen, setSessionOpen] = useState(false);
  const [taskList, setTaskList] = useState<TaskListData | null>(null);
  const [chatWidth, setChatWidth] = useState(() => Math.min(Math.round(window.innerWidth * 0.36), 420));
  const [dragging, setDragging] = useState(false);
  const [conversationId, updateConversationId] = useState<string>(
    () => options.initialConversationId || crypto.randomUUID(),
  );

  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const isDragging = useRef(false);
  const dragStartX = useRef(0);
  const dragStartWidth = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const revealRef = useRef<ReturnType<typeof createRevealQueue> | null>(null);
  const sendCountRef = useRef(0);
  const conversationIdRef = useRef(conversationId);
  const sessionIdsRef = useRef(new Map<string, number>());
  const sessionsRevisionRef = useRef(0);
  const sessionMetadataRef = useRef(new Map<string, ConversationPatch>());

  const setConversationId = useCallback((id: string) => {
    conversationIdRef.current = id;
    updateConversationId(id);
  }, []);

  const cancelRequest = useCallback(() => {
    ++sendCountRef.current;
    abortRef.current?.abort();
    abortRef.current = null;
    revealRef.current?.dispose();
    revealRef.current = null;
    setLoading(false);
  }, []);

  useEffect(() => {
    onDoneRef.current = options.onDone;
    onStepDoneRef.current = options.onStepDone;
    onStepDoneEffectRef.current = options.onStepDoneEffect;
    onStepQuestionsRef.current = options.onStepQuestions;
    onAllVisualsRef.current = options.onAllVisuals;
    getExtraPayloadRef.current = options.getExtraPayload;
    projectIdRef.current = projectId;
    conversationIdRef.current = conversationId;
  }, [options.onDone, options.onStepDone, options.onStepDoneEffect, options.onStepQuestions, options.onAllVisuals, options.getExtraPayload, projectId, conversationId]);

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
    const groups = new Map<string, Message[]>();
    let legacyKey = '';
    let previousLegacy: Message | undefined;
    for (const msg of allMessages) {
      if (!msg.conversation_id) {
        const timeGap = msg.timestamp && previousLegacy?.timestamp
          ? Date.parse(msg.timestamp) - Date.parse(previousLegacy.timestamp) : 0;
        if (!legacyKey || timeGap > GAP_MS) {
          legacyKey = `legacy:${msg.id ?? msg._id ?? msg.timestamp ?? groups.size}`;
        }
        previousLegacy = msg;
      } else {
        legacyKey = '';
        previousLegacy = undefined;
      }
      const key = msg.conversation_id || legacyKey;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(msg);
    }
    return Array.from(groups, ([key, msgs]) => {
      if (!sessionIdsRef.current.has(key)) sessionIdsRef.current.set(key, sessionIdsRef.current.size);
      const metadata = sessionMetadataRef.current.get(key);
      const title = metadata?.title ?? msgs.find(m => m.conversation_title)?.conversation_title ?? '';
      const firstUser = msgs.find(m => m.role === 'user');
      const label = title || (firstUser ? firstUser.content.slice(0, 30) + (firstUser.content.length > 30 ? '...' : '') : '对话');
      const lastMsg = msgs[msgs.length - 1];
      return { id: sessionIdsRef.current.get(key)!, label, title, messages: msgs, lastTime: lastMsg.timestamp || '', conversationId: lastMsg.conversation_id, projectId: metadata?.project_id !== undefined ? metadata.project_id : lastMsg.conversation_project ?? null, isPinned: metadata?.is_pinned ?? msgs.some(message => message.conversation_pinned) };
    }).sort((a, b) => (Date.parse(a.lastTime) || 0) - (Date.parse(b.lastTime) || 0));
  }, []);

  // Keep the sidebar snapshot current while sending, before any history refresh.
  useEffect(() => {
    ++sessionsRevisionRef.current;
    if (!messages.length) return;
    const current = groupIntoSessions(messages.map(message => ({ ...message, conversation_id: conversationId })))[0];
    current.messages = messages;
    current.projectId = projectId;
    setActiveSessionId(current.id);
    setSessions(previous => {
      const existing = previous.find(session => session.conversationId === conversationId);
      const updated = { ...existing, ...current };
      return [...previous.filter(session => session.conversationId !== conversationId), updated]
        .sort((a, b) => (Date.parse(a.lastTime) || 0) - (Date.parse(b.lastTime) || 0));
    });
  }, [messages, conversationId, projectId, groupIntoSessions]);

  // ── Session management ──

  const handleLoadSession = useCallback((session: ConversationSession) => {
    cancelRequest();
    const id = session.conversationId || session.messages.find(message => message.conversation_id)?.conversation_id || crypto.randomUUID();
    setConversationId(id);
    setMessages(session.messages.map(message => ({ ...message, conversation_id: id, visible: true })));
    setInput('');
    setTaskList(null);
    setActiveSessionId(session.id);
    setProjectId(session.projectId ?? null);
    setSessionOpen(false);
  }, [cancelRequest, setConversationId]);

  const handleRefreshSessions = useCallback(async () => {
    if (!bot) return;
    const revision = ++sessionsRevisionRef.current;
    try {
      const hRes = await api.get('/ai/history/', { params: { bot_id: bot.id } });
      if (revision !== sessionsRevisionRef.current) return;
      const allMsgs: Message[] = hRes.data
        .filter((m: Message) => m.content !== '[Thinking...]')
        .map((m: Message) => ({ ...m, visible: true }));
      setSessions(groupIntoSessions(restoreVisualSteps(allMsgs)));
    } catch (e) { console.error('[useAgentConversation] history fetch failed:', e); }
  }, [bot, groupIntoSessions]);

  const handleDeleteSession = useCallback(async (session: ConversationSession) => {
    if (!session.conversationId) return;
    try {
      await api.post('/ai/delete-conversation/', { conversation_id: session.conversationId });
      ++sessionsRevisionRef.current;
      setSessions(prev => prev.filter(s => s.conversationId !== session.conversationId));
      if (conversationIdRef.current === session.conversationId) {
        cancelRequest();
        setProjectId(session.projectId ?? null);
        setMessages([]);
        setInput('');
        setTaskList(null);
        setActiveSessionId(null);
        setConversationId(crypto.randomUUID());
      }
      toast.success('对话已删除');
    } catch {
      toast.error('删除失败，请重试');
    }
  }, [cancelRequest, setConversationId]);

  const handleUpdateSession = useCallback(async (session: ConversationSession, patch: ConversationPatch) => {
    if (!session.conversationId) return false;
    ++sessionsRevisionRef.current;
    try {
      const { data } = await api.patch<ConversationPatch>(`/ai/conversations/${session.conversationId}/`, patch);
      ++sessionsRevisionRef.current;
      sessionMetadataRef.current.set(session.conversationId, { ...sessionMetadataRef.current.get(session.conversationId), ...patch, is_pinned: data.is_pinned, project_id: data.project_id });
      const updateMessage = (message: Message) => ({ ...message, conversation_title: data.title || message.conversation_title, conversation_project: data.project_id, conversation_pinned: data.is_pinned });
      setSessions(previous => previous.map(item => item.conversationId === session.conversationId
        ? { ...item, title: data.title || item.title, label: data.title || item.label, projectId: data.project_id, isPinned: data.is_pinned, messages: item.messages.map(updateMessage) } : item));
      if (conversationIdRef.current === session.conversationId) {
        if (data.project_id !== undefined) setProjectId(data.project_id);
        setMessages(previous => previous.map(updateMessage));
      }
      return true;
    } catch { toast.error('对话保存失败，请重试'); return false; }
  }, [setProjectId]);

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
    setTaskList(null);

    let msgId = 0;
    const nextId = () => `msg_${++msgId}_${Date.now()}`;
    let streamingId: string | null = null;
    let streamingContent = '';

    if (!silent) {
      const userMsg: Message = { _id: nextId(), role: 'user', content: text, timestamp: new Date().toISOString(), conversation_id: requestConversationId };
      setMessages(prev => [...prev, userMsg]);
    }
    setInput('');

    const reveal = createRevealQueue({
      isActive: isCurrent,
      onReveal: (id) => {
        setMessages(prev => prev.map(m => m._id === id ? { ...m, visible: true } : m));
      },
    });
    revealRef.current = reveal;

    try {
      for await (const payload of readChatStream({
        body: {
          request_id: crypto.randomUUID(),
          message: text,
          bot_id: bot.id,
          conversation_id: requestConversationId,
          ...(options.enableProjects ? { project_id: projectIdRef.current } : {}),
          ...(getExtraPayloadRef.current?.() ?? {}),
        },
        signal: controller.signal,
        isCurrent,
      })) {
        if (!isCurrent()) return;
        try {
            if (payload.type === 'message' && payload.content) {
              if (streamingId) {
                const id = streamingId;
                setMessages(prev => upsertChatMessage(prev, {
                  _id: id, role: 'assistant', content: payload.content,
                  visible: true, timestamp: new Date().toISOString(),
                  conversation_id: conversationIdRef.current,
                }));
                streamingId = null;
                streamingContent = '';
                continue;
              }
              const id = nextId();
              setMessages(prev => [...prev, {
                _id: id,
                role: 'assistant' as const,
                content: payload.content,
                visible: false,
                timestamp: new Date().toISOString(),
                conversation_id: requestConversationId,
              }]);
              // scheduleShow 在 updater 外调用，用 rAF 确保 DOM 更新
              requestAnimationFrame(() => {
                if (!isCurrent()) return;
                setMessages(prev => {
                  const pos = prev.findIndex(m => m._id === id);
                  if (pos >= 0) reveal.schedule(id, pos);
                  return prev;
                });
              });
            } else if (payload.type === 'step') {
              const step = payload as AgentStep;
              setTaskList(prev => reduceToolRun(prev, step));

              if (step.status === 'batch_start') continue;

              // render_visual 的 visual 数据由下方 step.status 块统一处理：
              //   running   → 创建带 toolStep 的消息，scheduleShow 淡入
              //   terminal  → 更新 toolStep，成功时再处理 visual 和 questions
              if (step.status === 'running') {
                setMessages(prev => {
                  // 同一 call_id 已存在则更新（进度事件），否则新建
                  const existingIdx = prev.findIndex(m => m.toolStep?.call_id === step.call_id);
                  if (existingIdx >= 0) {
                    const updated = [...prev];
                    updated[existingIdx] = { ...updated[existingIdx], toolStep: step };
                    return updated;
                  }
                  return [...prev, {
                    _id: nextId(),
                    role: 'assistant' as const,
                    content: '',
                    toolStep: step,
                    visible: false,
                    timestamp: new Date().toISOString(),
                    conversation_id: requestConversationId,
                  }];
                });
                requestAnimationFrame(() => {
                  if (!isCurrent()) return;
                  setMessages(prev => {
                    const pos = prev.findIndex(m => m.toolStep?.call_id === step.call_id);
                    const targetId = pos >= 0 ? prev[pos]._id : undefined;
                    if (targetId) reveal.schedule(targetId, pos);
                    return prev;
                  });
                });
              } else if (step.status === 'succeeded' || step.status === 'failed') {
                if (step.status === 'succeeded' && onStepDoneRef.current) {
                  setMessages(prev => onStepDoneRef.current!(step, prev) || prev);
                } else {
                  setMessages(prev => prev.map(m =>
                    m.toolStep?.call_id === step.call_id ? { ...m, toolStep: step } : m
                  ));
                }
                if (step.status === 'succeeded') {
                  onStepDoneEffectRef.current?.(step);
                }
                if (step.status === 'succeeded' && step.questions?.length) {
                  onStepQuestionsRef.current?.(step.questions);
                }
              }
            } else if (payload.type === 'text_delta') {
              if (!payload.delta) continue;
              streamingId ??= nextId();
              streamingContent += payload.delta;
              const message: Message & { _id: string } = {
                _id: streamingId, role: 'assistant', content: streamingContent,
                visible: true, timestamp: new Date().toISOString(),
                conversation_id: conversationIdRef.current,
              };
              setMessages(prev => upsertChatMessage(prev, message));
            } else if (payload.type === 'error') {
              toast.error(payload.message || 'AI 调用失败');
            } else if (payload.done) {
              setTaskList(prev => completeToolRun(prev, payload.run_id));
              const finalContent = payload.full_content || '';
              if (payload.is_error) {
                toast.error(finalContent || 'AI 调用失败');
              } else if (finalContent && streamingId) {
                const id = streamingId;
                setMessages(prev => upsertChatMessage(prev, {
                  _id: id, id: payload.message_id, role: 'assistant',
                  content: finalContent, visible: true,
                  conversation_title: sessionMetadataRef.current.get(requestConversationId)?.title ?? payload.conversation_title ?? undefined,
                  metadata: payload.metadata || undefined,
                }));
                streamingId = null;
                streamingContent = '';
              } else if (finalContent) {
                // 最终消息也通过 scheduleShow 排队，确保出现在中间消息和 tool steps 之后
                const id = nextId();
                setMessages(prev => [...prev, {
                  _id: id,
                  id: payload.message_id,
                  role: 'assistant' as const,
                  content: finalContent,
                  conversation_title: sessionMetadataRef.current.get(requestConversationId)?.title ?? payload.conversation_title ?? undefined,
                  metadata: payload.metadata || undefined,
                  visible: false,
                  timestamp: new Date().toISOString(),
                  conversation_id: requestConversationId,
                }]);
                requestAnimationFrame(() => {
                  if (!isCurrent()) return;
                  setMessages(prev => {
                    const pos = prev.findIndex(m => m._id === id);
                    if (pos >= 0) reveal.schedule(id, pos);
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
        } catch { /* skip malformed SSE events */ }
      }
    } catch (err: unknown) {
      if (!isCurrent()) return;
      if (err instanceof DOMException && err.name === 'AbortError') return;
      const msg = err instanceof Error ? err.message : '发送失败，请重试';
      toast.error(msg.includes('HTTP') || err instanceof TypeError ? '服务暂时不可用，请稍后再试' : msg);
      setInput(text);
    } finally {
      reveal.dispose();
      if (revealRef.current === reveal) revealRef.current = null;
      if (isCurrent()) {
        setMessages(prev => prev.map(m => m.visible === false ? { ...m, visible: true } : m));
        setLoading(false);
      }
    }
  }, [bot, options.enableProjects]);

  // ── Handlers ──

  const handleReset = useCallback((notify = true) => {
    setProjectId(null);
    if (!bot) return;
    cancelRequest();
    setMessages([]);
    setInput('');
    setTaskList(null);
    setActiveSessionId(null);
    setConversationId(crypto.randomUUID());
    if (notify) toast.success(resetMessage);
  }, [bot, resetMessage, cancelRequest, setConversationId]);

  const handleSkillSelect = useCallback((prompt: string) => {
    setInput(prompt);
    setSkillOpen(false);
    setTimeout(() => inputRef.current?.focus(), 0);
  }, []);

  // ── Cleanup on unmount ──

  useEffect(() => {
    return () => {
      if (abortRef.current) abortRef.current.abort();
      revealRef.current?.dispose();
    };
  }, []);

  return {
    projectId, setProjectId,
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
    handleUpdateSession,
    handleReset,
    handleSkillSelect,
    doSend,
    groupIntoSessions,

    // Convenience
    findBot,
  };
}
