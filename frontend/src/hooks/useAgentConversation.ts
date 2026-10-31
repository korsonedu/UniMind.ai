import type { VisualData } from '@/pages/xiaoyu/visuals';
import { useState, useRef, useEffect, useLayoutEffect, useCallback } from 'react';
import api from '@/lib/api';
import { notifyDesktop } from '@/lib/desktop';
import { useAuthStore } from '@/store/useAuthStore';
import { deleteRecovery, readRecovery, recoveryScope, saveRecovery, type PendingChatRequest } from '@/lib/conversationRecovery';
import { upsertChatMessage } from '@/lib/chatMessages';
import { readChatStream } from '@/lib/chatStream';
import { createRevealQueue, createStreamSmoother } from '@/lib/chatReveal';
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
  streaming?: boolean;
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

type PendingSend = PendingChatRequest;

interface StreamEntry {
  controller: AbortController;
  reveal: ReturnType<typeof createRevealQueue>;
  smoother: ReturnType<typeof createStreamSmoother> | null;
}

export interface Bot {
  id: number;
  name: string;
  avatar: string | null;
  bot_type: string;
  institution?: number | null;
  is_active?: boolean;
}

// ── Hook options ──

interface UseAgentConversationOptions {
  enableProjects?: boolean;
  /** Find the target bot from the bots list */
  findBot: (bots: Bot[]) => Bot | undefined;
  /** Extra SSE payload fields (appended by doSend automatically) */
  getExtraPayload?: () => Record<string, unknown>;
  beforeSend?: () => Promise<void>;
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
  const beforeSendRef = useRef(options.beforeSend);

  const [bot, setBot] = useState<Bot | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const userId = useAuthStore(state => state.user?.id);
  const [input, updateInput] = useState('');
  const inputValueRef = useRef('');
  const inputRevisionRef = useRef(0);
  const scopeRef = useRef<string | null>(null);
  const identityRef = useRef('');
  const recoveryEpochRef = useRef(0);
  const recoveryBusyRef = useRef<number | null>(null);
  const [recoveryStatuses, setRecoveryStatuses] = useState<Record<string, 'pending' | 'completed' | 'unknown'>>({});
  const [generatingIds, setGeneratingIds] = useState<string[]>([]);
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
  const followScrollRef = useRef(true);
  const inputRef = useRef<HTMLInputElement>(null);
  const isDragging = useRef(false);
  const dragStartX = useRef(0);
  const dragStartWidth = useRef(0);
  const messagesRef = useRef<Message[]>([]);
  const messageBuffersRef = useRef(new Map<string, Message[]>());
  const streamsRef = useRef(new Map<string, StreamEntry>());
  const taskListsRef = useRef(new Map<string, TaskListData | null>());
  const pendingSendsRef = useRef(new Map<string, PendingSend>());
  const sendCountsRef = useRef(new Map<string, number>());
  const generatingRef = useRef(new Set<string>());
  const conversationIdRef = useRef(conversationId);
  const sessionIdsRef = useRef(new Map<string, number>());
  const sessionsRevisionRef = useRef(0);
  const sessionSyncKeyRef = useRef('');
  const sessionMetadataRef = useRef(new Map<string, ConversationPatch>());

  const loading = generatingIds.includes(conversationId);
  const identity = `${userId ?? ''}:${bot?.id ?? ''}`;
  useLayoutEffect(() => { identityRef.current = identity; }, [identity]);
  const previousIdentityRef = useRef({ userId, botId: bot?.id });

  const setInput = useCallback((value: React.SetStateAction<string>) => {
    const next = typeof value === 'function' ? value(inputValueRef.current) : value;
    inputValueRef.current = next;
    ++inputRevisionRef.current;
    updateInput(next);
    saveRecovery(scopeRef.current, conversationIdRef.current, { draft: next, draftRevision: crypto.randomUUID() });
  }, []);

  const setConversationId = useCallback((id: string) => {
    conversationIdRef.current = id;
    updateConversationId(id);
    if (scopeRef.current) {
      const draft = readRecovery(scopeRef.current).conversations[id]?.draft ?? '';
      inputValueRef.current = draft;
      ++inputRevisionRef.current;
      updateInput(draft);
      saveRecovery(scopeRef.current, id, {}, true);
    }
  }, []);

  const markGenerating = useCallback((id: string, active: boolean) => {
    const set = generatingRef.current;
    if (active === set.has(id)) return;
    if (active) set.add(id); else set.delete(id);
    setGeneratingIds([...set]);
  }, []);

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

  const syncSession = useCallback((id: string, nextMessages: Message[], nextProjectId?: number | null) => {
    if (!nextMessages.length) return;
    const current = groupIntoSessions(nextMessages.map(message => ({ ...message, conversation_id: id })))[0];
    if (!current) return;
    current.messages = nextMessages;
    setSessions(previous => {
      const existing = previous.find(session => session.conversationId === id);
      const currentProjectId = nextProjectId !== undefined ? nextProjectId : current.projectId ?? existing?.projectId ?? null;
      const updated = existing ? { ...existing, ...current, projectId: currentProjectId } : { ...current, projectId: currentProjectId };
      return [...previous.filter(session => session.conversationId !== id), updated]
        .sort((a, b) => (Date.parse(a.lastTime) || 0) - (Date.parse(b.lastTime) || 0));
    });
    if (id === conversationIdRef.current) setActiveSessionId(current.id);
  }, [groupIntoSessions]);

  const updateConversationMessages = useCallback((id: string, updater: (previous: Message[]) => Message[]) => {
    if (id === conversationIdRef.current) {
      const next = updater(messagesRef.current);
      messagesRef.current = next;
      messageBuffersRef.current.set(id, next);
      // Update sidebar snapshots at message boundaries, before history can refresh.
      const key = `${id}:${projectIdRef.current ?? ''}:${next.length}:${next[next.length - 1]?._id ?? ''}`;
      if (sessionSyncKeyRef.current !== key) {
        sessionSyncKeyRef.current = key;
        ++sessionsRevisionRef.current;
        syncSession(id, next, projectIdRef.current);
      }
      setMessages(next);
      return next;
    }
    const next = updater(messageBuffersRef.current.get(id) ?? []);
    messageBuffersRef.current.set(id, next);
    return next;
  }, [syncSession]);

  const abortStream = useCallback((id: string) => {
    const entry = streamsRef.current.get(id);
    if (entry) {
      streamsRef.current.delete(id);
      entry.controller.abort();
      entry.reveal.dispose();
      entry.smoother?.dispose();
    }
    // 让仍在 beforeSend 里的请求在恢复后看到自己已失效。
    sendCountsRef.current.set(id, (sendCountsRef.current.get(id) ?? 0) + 1);
    updateConversationMessages(id, previous => previous.filter(message => !message.streaming));
    markGenerating(id, false);
  }, [markGenerating, updateConversationMessages]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    onDoneRef.current = options.onDone;
    onStepDoneRef.current = options.onStepDone;
    onStepDoneEffectRef.current = options.onStepDoneEffect;
    onStepQuestionsRef.current = options.onStepQuestions;
    onAllVisualsRef.current = options.onAllVisuals;
    getExtraPayloadRef.current = options.getExtraPayload;
    beforeSendRef.current = options.beforeSend;
    projectIdRef.current = projectId;
    conversationIdRef.current = conversationId;
  }, [options.onDone, options.onStepDone, options.onStepDoneEffect, options.onStepQuestions, options.onAllVisuals, options.getExtraPayload, options.beforeSend, projectId, conversationId]);

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

  // ── Session management ──

  const handleLoadSession = useCallback((session: ConversationSession) => {
    messageBuffersRef.current.set(conversationIdRef.current, messagesRef.current);
    const id = session.conversationId || session.messages.find(message => message.conversation_id)?.conversation_id || crypto.randomUUID();
    setConversationId(id);
    const next = (messageBuffersRef.current.get(id) ?? session.messages)
      .map(message => ({ ...message, conversation_id: id, visible: true }));
    messagesRef.current = next;
    messageBuffersRef.current.set(id, next);
    setMessages(next);
    if (!scopeRef.current) setInput('');
    setTaskList(taskListsRef.current.get(id) ?? null);
    setActiveSessionId(session.id);
    setProjectId(session.projectId ?? null);
    setSessionOpen(false);
  }, [setConversationId, setProjectId]);

  const handleRefreshSessions = useCallback(async () => {
    if (!bot) return;
    const revision = ++sessionsRevisionRef.current;
    try {
      const hRes = await api.get('/ai/history/', { params: { bot_id: bot.id } });
      if (revision !== sessionsRevisionRef.current) return;
      const allMsgs: Message[] = hRes.data
        .filter((m: Message) => m.content !== '[Thinking...]')
        .map((m: Message) => ({ ...m, visible: true }));
      const serverSessions = groupIntoSessions(restoreVisualSteps(allMsgs));
      setSessions(previous => {
        const merged = new Map<string, ConversationSession>();
        for (const session of serverSessions) {
          const key = session.conversationId || `session:${session.id}`;
          const buffered = session.conversationId ? messageBuffersRef.current.get(session.conversationId) : undefined;
          merged.set(key, buffered
            ? { ...session, messages: buffered, lastTime: buffered[buffered.length - 1]?.timestamp || session.lastTime }
            : session);
        }
        for (const session of previous) {
          if (!session.conversationId) continue;
          if (streamsRef.current.has(session.conversationId) || messageBuffersRef.current.has(session.conversationId)
              || session.conversationId === conversationIdRef.current) {
            const key = session.conversationId;
            if (!merged.has(key)) merged.set(key, session);
          }
        }
        return [...merged.values()].sort((a, b) => (Date.parse(a.lastTime) || 0) - (Date.parse(b.lastTime) || 0));
      });
    } catch (e) { console.error('[useAgentConversation] history fetch failed:', e); }
  }, [bot, groupIntoSessions]);

  const handleDeleteSession = useCallback(async (session: ConversationSession) => {
    if (!session.conversationId) return;
    const id = session.conversationId;
    const scope = scopeRef.current;
    const epoch = recoveryEpochRef.current;
    try {
      await api.post('/ai/delete-conversation/', { conversation_id: id });
      deleteRecovery(scope, id);
      if (epoch !== recoveryEpochRef.current) return;
      ++sessionsRevisionRef.current;
      abortStream(id);
      messageBuffersRef.current.delete(id);
      taskListsRef.current.delete(id);
      pendingSendsRef.current.delete(id);
      setRecoveryStatuses(previous => { const next = { ...previous }; delete next[id]; return next; });
      sendCountsRef.current.delete(id);
      setSessions(prev => prev.filter(s => s.conversationId !== id));
      if (conversationIdRef.current === id) {
        setProjectId(session.projectId ?? null);
        messagesRef.current = [];
        setMessages([]);
        if (!scopeRef.current) setInput('');
        setTaskList(null);
        setActiveSessionId(null);
        setConversationId(crypto.randomUUID());
      }
      toast.success('对话已删除');
    } catch {
      toast.error('删除失败，请重试');
    }
  }, [abortStream, setConversationId, setProjectId]);

  const handleUpdateSession = useCallback(async (session: ConversationSession, patch: ConversationPatch) => {
    if (!session.conversationId) return false;
    ++sessionsRevisionRef.current;
    const epoch = recoveryEpochRef.current;
    try {
      const { data } = await api.patch<ConversationPatch>(`/ai/conversations/${session.conversationId}/`, patch);
      if (epoch !== recoveryEpochRef.current) return false;
      ++sessionsRevisionRef.current;
      sessionMetadataRef.current.set(session.conversationId, { ...sessionMetadataRef.current.get(session.conversationId), ...patch, is_pinned: data.is_pinned, project_id: data.project_id });
      const updateMessage = (message: Message) => ({ ...message, conversation_title: data.title || message.conversation_title, conversation_project: data.project_id, conversation_pinned: data.is_pinned });
      const buffered = messageBuffersRef.current.get(session.conversationId);
      const patched = (buffered ?? messagesRef.current).map(updateMessage);
      if (buffered) messageBuffersRef.current.set(session.conversationId, patched);
      setSessions(previous => previous.map(item => item.conversationId === session.conversationId
        ? { ...item, title: data.title || item.title, label: data.title || item.label, projectId: data.project_id, isPinned: data.is_pinned, messages: item.messages.map(updateMessage) } : item));
      if (conversationIdRef.current === session.conversationId) {
        if (data.project_id !== undefined) setProjectId(data.project_id);
        messagesRef.current = patched;
        messageBuffersRef.current.set(session.conversationId, patched);
        setMessages(patched);
      }
      return true;
    } catch { toast.error('对话保存失败，请重试'); return false; }
  }, [setProjectId]);

  // Identity changes invalidate async recovery and every stream before restoring local state.
  useEffect(() => {
    const previous = previousIdentityRef.current;
    previousIdentityRef.current = { userId, botId: bot?.id };
    ++recoveryEpochRef.current;
    scopeRef.current = null;
    if (previous.userId === userId && (!previous.botId || previous.botId === bot?.id)) return;
    streamsRef.current.forEach(entry => { entry.controller.abort(); entry.reveal.dispose(); entry.smoother?.dispose(); });
    streamsRef.current.clear();
    sendCountsRef.current.clear();
    generatingRef.current.clear();
    messageBuffersRef.current.clear();
    taskListsRef.current.clear();
    pendingSendsRef.current.clear();
    sessionMetadataRef.current.clear();
    sessionIdsRef.current.clear();
    sessionSyncKeyRef.current = '';
    ++sessionsRevisionRef.current;
    setGeneratingIds([]);
    setRecoveryStatuses({});
    messagesRef.current = [];
    setMessages([]);
    setSessions([]);
    setActiveSessionId(null);
    setTaskList(null);
    setProjectId(null);
    inputValueRef.current = '';
    inputRevisionRef.current = 0;
    updateInput('');
  }, [identity]);

  useEffect(() => {
    if (!initialized || !bot || !userId || !window.unimindDesktop) return;
    const scope = recoveryScope(userId, bot.id);
    if (scopeRef.current === scope) return;
    const saved = readRecovery(scope);
    scopeRef.current = scope;
    const restoredStatuses: Record<string, 'unknown'> = {};
    for (const [id, record] of Object.entries(saved.conversations)) {
      if (record.pending) { pendingSendsRef.current.set(id, record.pending); restoredStatuses[id] = 'unknown'; }
    }
    setRecoveryStatuses(restoredStatuses);
    // Initialization may have fetched history, but it must not overwrite a newly typed draft.
    if (inputRevisionRef.current === 0 && saved.lastConversationId
        && (!options.initialConversationId || (!saved.conversations[options.initialConversationId]
          && !sessions.some(row => row.conversationId === options.initialConversationId)))) {
      const id = saved.lastConversationId;
      setConversationId(id);
      const session = sessions.find(row => row.conversationId === id);
      const next = session?.messages ?? [];
      messagesRef.current = next;
      messageBuffersRef.current.set(id, next);
      setMessages(next);
      setActiveSessionId(session?.id ?? null);
      setProjectId(session?.projectId ?? null);
    } else if (inputRevisionRef.current === 0) {
      setConversationId(conversationIdRef.current);
    } else {
      saveRecovery(scope, conversationIdRef.current, { draft: inputValueRef.current }, true);
    }
  }, [initialized, identity, bot, userId, options.initialConversationId, sessions, setConversationId, setProjectId]);

  const recoverRequests = useCallback(async () => {
    if (!bot || !userId || !navigator.onLine) return;
    const epoch = recoveryEpochRef.current;
    if (recoveryBusyRef.current === epoch) return;
    recoveryBusyRef.current = epoch;
    const scope = scopeRef.current;
    const expectedIdentity = identity;
    const isCurrent = () => epoch === recoveryEpochRef.current
      && identityRef.current === expectedIdentity && useAuthStore.getState().user?.id === userId;
    try {
      for (const [id, pending] of [...pendingSendsRef.current]) {
        if (!isCurrent()) return;
        const draftAtStart = readRecovery(scope).conversations[id];
        try {
          const data = await api.get<{ status: 'pending' | 'completed' | 'unknown' }>(`/ai/chat-requests/${pending.id}/`)
            .then(response => response.data, () => ({ status: 'unknown' as const }));
          // History is authoritative; recovery never starts another model/tool request.
          const history = await api.get<Message[]>('/ai/history/', { params: { bot_id: bot.id, conversation_id: id } });
          if (!isCurrent() || pendingSendsRef.current.get(id)?.id !== pending.id) continue;
          if (data.status === 'completed' || !streamsRef.current.has(id)) {
            if (data.status === 'completed') abortStream(id);
            const next = restoreVisualSteps(history.data.filter(message => message.content !== '[Thinking...]')
              .map(message => ({ ...message, visible: true })));
            messageBuffersRef.current.set(id, next);
            if (id === conversationIdRef.current) { messagesRef.current = next; setMessages(next); }
            syncSession(id, next);
          }
          setRecoveryStatuses(previous => ({ ...previous, [id]: data.status }));
          if (data.status === 'unknown') toast.info('执行结果尚未确认，可稍后刷新历史', { id: `chat-recovery-${pending.id}` });
          if (data.status === 'completed') {
            pendingSendsRef.current.delete(id);
            const saved = readRecovery(scope).conversations[id];
            const clearDraft = saved?.draft === pending.text && saved.draftRevision === draftAtStart?.draftRevision;
            saveRecovery(scope, id, { pending: undefined, ...(clearDraft ? { draft: '' } : {}) });
            if (clearDraft && id === conversationIdRef.current && inputValueRef.current === pending.text) setInput('');
          }
        } catch {
          if (isCurrent()) setRecoveryStatuses(previous => ({ ...previous, [id]: 'unknown' }));
        }
      }
    } finally {
      if (recoveryBusyRef.current === epoch) recoveryBusyRef.current = null;
    }
  }, [bot, userId, identity, abortStream, syncSession, setInput]);

  useEffect(() => {
    if (!initialized) return;
    void recoverRequests();
    const resume = () => { void recoverRequests(); };
    window.addEventListener('online', resume);
    window.addEventListener('focus', resume);
    const unsubscribe = window.unimindDesktop?.onResume?.(resume);
    return () => { window.removeEventListener('online', resume); window.removeEventListener('focus', resume); unsubscribe?.(); };
  }, [initialized, recoverRequests]);

  useEffect(() => {
    if (!Object.values(recoveryStatuses).includes('pending')) return;
    // Stop after one minute; a later online/focus/resume event can check again.
    let attempts = 0;
    const timer = window.setInterval(() => {
      if (++attempts > 12) { window.clearInterval(timer); return; }
      void recoverRequests();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [recoverRequests, Object.values(recoveryStatuses).includes('pending')]);

  // ── Auto-scroll ──

  useEffect(() => {
    const pane = scrollRef.current;
    if (!pane) return;
    const onScroll = () => {
      followScrollRef.current = pane.scrollHeight - pane.clientHeight - pane.scrollTop < 80;
    };
    pane.addEventListener('scroll', onScroll, { passive: true });
    return () => pane.removeEventListener('scroll', onScroll);
  }, [messages.length > 0]);

  useEffect(() => { followScrollRef.current = true; }, [conversationId]);

  useEffect(() => {
    if (scrollRef.current && followScrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  // ── SSE streaming ──

  const doSend = useCallback(async (text: string, silent: boolean = false) => {
    if (!bot) return;

    const requestConversationId = conversationIdRef.current;
    const requestIdentity = identityRef.current;
    const requestEpoch = recoveryEpochRef.current;
    const requestUserId = userId;
    const requestScope = scopeRef.current;
    let sentInputRevision = inputRevisionRef.current;
    const existingPending = pendingSendsRef.current.get(requestConversationId);
    if (existingPending && existingPending.text !== text) {
      toast.info('上一条提问的执行结果尚未确认，请先恢复历史。');
      void recoverRequests();
      return;
    }

    // 只中止同一会话的上一条请求，其他会话的后台流继续跑。
    const previousEntry = streamsRef.current.get(requestConversationId);
    if (previousEntry) {
      streamsRef.current.delete(requestConversationId);
      previousEntry.controller.abort();
      previousEntry.reveal.dispose();
      previousEntry.smoother?.dispose();
      updateConversationMessages(requestConversationId, previous => previous.filter(message => !message.streaming));
    }

    const controller = new AbortController();
    const currentSend = (sendCountsRef.current.get(requestConversationId) ?? 0) + 1;
    sendCountsRef.current.set(requestConversationId, currentSend);
    const isRequestActive = () => !controller.signal.aborted
      && sendCountsRef.current.get(requestConversationId) === currentSend
      && recoveryEpochRef.current === requestEpoch
      && identityRef.current === requestIdentity && useAuthStore.getState().user?.id === requestUserId;
    const isVisible = () => requestConversationId === conversationIdRef.current;

    markGenerating(requestConversationId, true);
    taskListsRef.current.set(requestConversationId, null);
    if (isVisible()) setTaskList(null);

    try {
      await beforeSendRef.current?.();
      if (!isRequestActive()) return;
    } catch (error) {
      if (isRequestActive()) {
        markGenerating(requestConversationId, false);
        toast.error(error instanceof Error ? error.message : '笔记尚未保存，问题已保留，请重试。');
      }
      return;
    }

    let msgId = 0;
    const streamPrefix = crypto.randomUUID();
    const nextId = () => `${streamPrefix}_${++msgId}`;
    let streamingId: string | null = null;
    let streamingContent = '';
    let completed = false;

    const body = existingPending ? JSON.parse(existingPending.key) : {
      message: text, bot_id: bot.id, conversation_id: requestConversationId,
      ...(options.enableProjects ? { project_id: projectIdRef.current } : {}),
      ...(getExtraPayloadRef.current?.() ?? {}),
    };
    const key = JSON.stringify(body);
    const pending: PendingSend = existingPending?.key === key ? existingPending : { key, id: crypto.randomUUID(), text };
    pendingSendsRef.current.set(requestConversationId, pending);
    const userMessageId = pending.userMessageId || nextId();
    pending.userMessageId = userMessageId;
    saveRecovery(requestScope, requestConversationId, { pending }, isVisible());
    if (!silent) {
      if (isVisible()) followScrollRef.current = true;
      const userMsg: Message = { _id: userMessageId, role: 'user', content: text, timestamp: new Date().toISOString(), conversation_id: requestConversationId };
      updateConversationMessages(requestConversationId, previous => previous.some(row => row._id === userMessageId || (pending.serverMessageId && row.id === pending.serverMessageId)) ? previous : [...previous, userMsg]);
      syncSession(requestConversationId, messageBuffersRef.current.get(requestConversationId) ?? [], projectIdRef.current);
    }
    if (isVisible() && inputRevisionRef.current === sentInputRevision) {
      setInput('');
      sentInputRevision = inputRevisionRef.current;
    }

    const reveal = createRevealQueue({
      isActive: isRequestActive,
      onReveal: (id) => {
        updateConversationMessages(requestConversationId, previous => previous.map(message => message._id === id ? { ...message, visible: true } : message));
      },
    });

    // 流式文字平滑器只服务本次请求，每次轮次边界重新创建。
    let smoother: ReturnType<typeof createStreamSmoother> | null = null;
    const entry: StreamEntry = { controller, reveal, smoother: null };
    streamsRef.current.set(requestConversationId, entry);
    const ensureSmoother = () => {
      if (!smoother) {
        smoother = createStreamSmoother({
          isActive: isRequestActive,
          onUpdate: (content) => {
            if (!streamingId || !isRequestActive()) return;
            const id = streamingId;
            updateConversationMessages(requestConversationId, previous => upsertChatMessage(previous, {
              _id: id, role: 'assistant', content,
              visible: true, streaming: true, timestamp: new Date().toISOString(),
              conversation_id: requestConversationId,
            }));
          },
        });
        entry.smoother = smoother;
      }
      return smoother;
    };
    const stopSmoother = (content?: string, discard = false) => {
      const current = smoother;
      if (!current) return;
      smoother = null;
      if (entry.smoother === current) entry.smoother = null;
      if (!discard) current.flush(content);
      current.dispose();
    };
    const updateTaskList = (updater: (previous: TaskListData | null) => TaskListData | null) => {
      const next = updater(taskListsRef.current.get(requestConversationId) ?? null);
      taskListsRef.current.set(requestConversationId, next);
      if (isVisible()) setTaskList(next);
    };

    try {
      for await (const payload of readChatStream({
        body: { ...body, request_id: pending.id },
        signal: controller.signal,
        isCurrent: isRequestActive,
      })) {
        if (!isRequestActive()) return;
        try {
          if (payload.type === 'user_message') {
            pending.serverMessageId = payload.message_id;
            saveRecovery(requestScope, requestConversationId, { pending });
            updateConversationMessages(requestConversationId, previous => previous.map(message => message._id === userMessageId ? { ...message, id: payload.message_id, metadata: payload.metadata } : message));
          } else if (payload.type === 'message' && payload.content) {
            if (streamingId) {
              const id = streamingId;
              // 轮次边界先收尾文字，避免残留帧把内容回写并与后续工具卡片交错。
              stopSmoother(payload.content);
              updateConversationMessages(requestConversationId, previous => upsertChatMessage(previous, {
                _id: id, role: 'assistant', content: payload.content,
                visible: true, streaming: false, timestamp: new Date().toISOString(),
                conversation_id: requestConversationId,
              }));
              streamingId = null;
              streamingContent = '';
              continue;
            }
            const id = nextId();
            updateConversationMessages(requestConversationId, previous => [...previous, {
              _id: id,
              role: 'assistant' as const,
              content: payload.content,
              visible: false,
              timestamp: new Date().toISOString(),
              conversation_id: requestConversationId,
            }]);
            // scheduleShow 在 updater 外调用，用 rAF 确保 DOM 更新
            requestAnimationFrame(() => {
              if (!isRequestActive()) return;
              updateConversationMessages(requestConversationId, previous => {
                const pos = previous.findIndex(message => message._id === id);
                if (pos >= 0) reveal.schedule(id, pos);
                return previous;
              });
            });
          } else if (payload.type === 'step') {
            const step = payload as AgentStep;
            updateTaskList(previous => reduceToolRun(previous, step));

            if (step.status === 'batch_start') continue;

            // render_visual 的 visual 数据由下方 step.status 块统一处理：
            //   running   → 创建带 toolStep 的消息，scheduleShow 淡入
            //   terminal  → 更新 toolStep，成功时再处理 visual 和 questions
            if (step.status === 'running') {
              updateConversationMessages(requestConversationId, previous => {
                // 同一 call_id 已存在则更新（进度事件），否则新建
                const existingIdx = previous.findIndex(message => message.toolStep?.call_id === step.call_id);
                if (existingIdx >= 0) {
                  const updated = [...previous];
                  updated[existingIdx] = { ...updated[existingIdx], toolStep: step };
                  return updated;
                }
                return [...previous, {
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
                if (!isRequestActive()) return;
                updateConversationMessages(requestConversationId, previous => {
                  const pos = previous.findIndex(message => message.toolStep?.call_id === step.call_id);
                  const targetId = pos >= 0 ? previous[pos]._id : undefined;
                  if (targetId) reveal.schedule(targetId, pos);
                  return previous;
                });
              });
            } else if (step.status === 'succeeded' || step.status === 'failed') {
              if (step.status === 'succeeded' && onStepDoneRef.current) {
                updateConversationMessages(requestConversationId, previous => onStepDoneRef.current!(step, previous) || previous);
              } else {
                updateConversationMessages(requestConversationId, previous => previous.map(message =>
                  message.toolStep?.call_id === step.call_id ? { ...message, toolStep: step } : message
                ));
              }
              if (step.status === 'succeeded') {
                if (isVisible()) onStepDoneEffectRef.current?.(step);
              }
              if (step.status === 'succeeded' && step.questions?.length && isVisible()) {
                onStepQuestionsRef.current?.(step.questions);
              }
            }
          } else if (payload.type === 'text_reset') {
            stopSmoother(undefined, true);
            if (streamingId) {
              const id = streamingId;
              updateConversationMessages(requestConversationId, previous => previous.filter(message => message._id !== id));
            }
            streamingId = null; streamingContent = '';
          } else if (payload.type === 'text_delta') {
            if (!payload.delta) continue;
            streamingId ??= nextId();
            streamingContent += payload.delta;
            ensureSmoother().push(streamingContent);
          } else if (payload.type === 'error') {
            toast.error(payload.message || 'AI 调用失败');
          } else if (payload.done) {
            if (!payload.is_error) {
              if (!completed) notifyDesktop({ title: '小宇已完成回复', body: '打开 UniMind 查看回复。', route: '/xiaoyu' });
              completed = true;
              if (pendingSendsRef.current.get(requestConversationId)?.id === pending.id) {
                pendingSendsRef.current.delete(requestConversationId);
                saveRecovery(requestScope, requestConversationId, { pending: undefined });
                setRecoveryStatuses(previous => ({ ...previous, [requestConversationId]: 'completed' }));
              }
            }
            updateTaskList(previous => completeToolRun(previous, payload.run_id));
            const finalContent = payload.full_content || '';
            if (payload.is_error) {
              if (streamingId) {
                const id = streamingId;
                updateConversationMessages(requestConversationId, previous => previous.filter(message => message._id !== id));
              }
              streamingId = null; streamingContent = '';
              if (isVisible() && inputRevisionRef.current === sentInputRevision) setInput(text);
              toast.error(finalContent || 'AI 调用失败');
            } else if (finalContent && streamingId) {
              const id = streamingId;
              // 先补全逐字泵，再写 metadata，避免残留帧覆盖最终内容。
              stopSmoother(finalContent);
              updateConversationMessages(requestConversationId, previous => upsertChatMessage(previous, {
                _id: id, id: payload.message_id, role: 'assistant',
                content: finalContent, visible: true, streaming: false,
                conversation_title: sessionMetadataRef.current.get(requestConversationId)?.title ?? payload.conversation_title ?? undefined,
                metadata: payload.metadata || undefined,
              }));
              streamingId = null;
              streamingContent = '';
            } else if (finalContent) {
              // 最终消息也通过 scheduleShow 排队，确保出现在中间消息和 tool steps 之后
              const id = nextId();
              updateConversationMessages(requestConversationId, previous => [...previous, {
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
                if (!isRequestActive()) return;
                updateConversationMessages(requestConversationId, previous => {
                  const pos = previous.findIndex(message => message._id === id);
                  if (pos >= 0) reveal.schedule(id, pos);
                  return previous;
                });
              });
            } else if (payload.has_intermediate) {
              // 中间消息已展示全部内容，不需空最终气泡
            }
            // Notify parent about visuals from done event metadata
            const doneVisuals = payload.metadata?.all_visuals || (payload.metadata?.visual ? [payload.metadata.visual] : []);
            if (doneVisuals.length && isVisible()) {
              onAllVisualsRef.current?.(doneVisuals);
            }
            if (isVisible()) onDoneRef.current?.();
          } else if (payload.error) {
            toast.error(payload.error);
          }
        } catch { /* skip malformed SSE events */ }
      }
    } catch (err: unknown) {
      if (!isRequestActive()) return;
      if (err instanceof DOMException && err.name === 'AbortError') return;
      const msg = err instanceof Error ? err.message : '发送失败，请重试';
      toast.error(msg.includes('HTTP') || err instanceof TypeError ? '服务暂时不可用，请稍后再试' : msg);
      if (isVisible() && inputRevisionRef.current === sentInputRevision) setInput(text);
    } finally {
      const stillOwner = streamsRef.current.get(requestConversationId) === entry;
      if (stillOwner) streamsRef.current.delete(requestConversationId);
      if (!completed && streamingId && (stillOwner || messageBuffersRef.current.has(requestConversationId))) {
        const id = streamingId;
        updateConversationMessages(requestConversationId, previous => previous.filter(message => message._id !== id));
      }
      reveal.dispose();
      // 异常断流时补全已收到的文字；被取消时 isActive 已为 false，不会写回。
      stopSmoother(streamingContent);
      if (isRequestActive()) {
        updateConversationMessages(requestConversationId, previous => previous.map(message =>
          message.visible === false || message.streaming ? { ...message, visible: true, streaming: false } : message
        ));
        syncSession(requestConversationId, messageBuffersRef.current.get(requestConversationId) ?? []);
      }
      if (stillOwner) markGenerating(requestConversationId, false);
      if (!completed && isRequestActive()) {
        setRecoveryStatuses(previous => ({ ...previous, [requestConversationId]: 'unknown' }));
        void recoverRequests();
      }
    }
  }, [bot, userId, markGenerating, options.enableProjects, syncSession, updateConversationMessages, recoverRequests, setInput]);

  // ── Handlers ──

  const handleReset = useCallback((notify = true) => {
    setProjectId(null);
    if (!bot) return;
    // 保留原会话的后台流；只清空当前视图并新建会话。
    messageBuffersRef.current.set(conversationIdRef.current, messagesRef.current);
    messagesRef.current = [];
    setMessages([]);
    if (!scopeRef.current) setInput('');
    setTaskList(null);
    setActiveSessionId(null);
    setConversationId(crypto.randomUUID());
    if (notify) toast.success(resetMessage);
  }, [bot, resetMessage, setConversationId, setProjectId]);

  const handleSkillSelect = useCallback((prompt: string) => {
    setInput(prompt);
    setSkillOpen(false);
    setTimeout(() => inputRef.current?.focus(), 0);
  }, []);

  // ── Cleanup on unmount ──

  useEffect(() => {
    return () => {
      ++recoveryEpochRef.current;
      streamsRef.current.forEach(entry => {
        entry.controller.abort();
        entry.reveal.dispose();
        entry.smoother?.dispose();
      });
      streamsRef.current.clear();
      sendCountsRef.current.forEach((count, id) => sendCountsRef.current.set(id, count + 1));
    };
  }, []);

  return {
    projectId, setProjectId,
    // State
    bot,
    messages,
    input,
    loading,
    generatingIds,
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
    recovery: recoveryStatuses[conversationId] ?? null,
    retryPendingRequest: () => { const pending = pendingSendsRef.current.get(conversationIdRef.current); if (pending) void doSend(pending.text); },
    recoverRequests,

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
