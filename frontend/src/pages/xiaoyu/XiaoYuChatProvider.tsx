import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import api from '@/lib/api';
import { restoreVisualSteps } from '@/lib/visualHistory';
import { useAgentConversation, type Bot, type Message } from '@/hooks/useAgentConversation';
import { useAuthStore } from '@/store/useAuthStore';
import { useChatUnreadStore } from '@/store/useChatUnreadStore';
import { readRecovery, recoveryScope } from '@/lib/conversationRecovery';
import { queryClient } from '@/lib/queryClient';
import { learningKey, type ProjectLearning } from '@/lib/projectLearning';
import { XiaoYuChatContext, findAssistantBot, type PageChatHooks } from './xiaoYuChatContext';

/**
 * 路由级常驻聊天。Provider 在 Router 根部挂载，路由切换只卸载页面 UI，
 * SSE 流、会话快照和输入草稿仍由 useAgentConversation 持有。
 */
export function XiaoYuChatProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [openingProject, setOpeningProject] = useState(false);
  const openSequence = useRef(0);
  const restored = useRef<string>('');
  const [activated, setActivated] = useState(false);
  const pageHooksRef = useRef<PageChatHooks>({});
  const viewedRef = useRef<string | null>(null);
  const loadedUserIdRef = useRef<number | null>(null);
  const initializingUserIdRef = useRef<number | null>(null);
  const unread = useChatUnreadStore(state => state.unread);
  const unreadIds = useMemo(() => new Set(Object.keys(unread)), [unread]);
  const markUnread = useChatUnreadStore(state => state.markSettled);
  const viewUnread = useChatUnreadStore(state => state.view);
  const leaveUnread = useChatUnreadStore(state => state.leave);
  const resetUnread = useChatUnreadStore(state => state.reset);

  const chat = useAgentConversation({
    enableProjects: true,
    findBot: findAssistantBot,
    beforeSend: async () => { await pageHooksRef.current.beforeSend?.(); },
    getExtraPayload: () => pageHooksRef.current.getExtraPayload?.() ?? {},
    onDone: () => pageHooksRef.current.onDone?.(),
    onRunSettled: (id, outcome) => {
      if (id === viewedRef.current) return;
      markUnread(id, outcome);
    },
    onStepDoneEffect: step => pageHooksRef.current.onStepDoneEffect?.(step),
    onAllVisuals: visuals => pageHooksRef.current.onAllVisuals?.(visuals),
    onStepQuestions: questions => pageHooksRef.current.onStepQuestions?.(questions),
    resetMessage: '已开始新对话',
  });
  const { conversationId, setBot, setInitialized, setSessions, groupIntoSessions } = chat;
  const userId = useAuthStore(state => state.user?.id);

  useEffect(() => {
    if (!userId) {
      loadedUserIdRef.current = null;
      setInitialized(false);
      return;
    }
    if (!activated || !userId || loadedUserIdRef.current === userId || initializingUserIdRef.current === userId) return;
    initializingUserIdRef.current = userId;
    let cancelled = false;
    const init = async () => {
      try {
        const bRes = await api.get('/ai/bots/');
        if (cancelled) return;
        const bots: Bot[] = Array.isArray(bRes.data) ? bRes.data : (bRes.data?.results || []);
        const found = findAssistantBot(bots);
        if (!found) {
          toast.error('未找到小宇 bot');
          return;
        }
        setBot(found);
        const hRes = await api.get('/ai/history/', { params: { bot_id: found.id } });
        if (cancelled) return;
        if (Array.isArray(hRes.data) && hRes.data.length > 0) {
          const allMsgs: Message[] = restoreVisualSteps(
            hRes.data
              .filter((message: Message) => message.content !== '[Thinking...]')
              .map((message: Message) => ({ ...message, visible: true } as Message)),
          );
          setSessions(groupIntoSessions(allMsgs));
        }
      } catch {
        if (!cancelled) toast.error('小宇加载失败');
      } finally {
        if (initializingUserIdRef.current === userId) initializingUserIdRef.current = null;
        if (!cancelled) {
          loadedUserIdRef.current = userId;
          setInitialized(true);
        }
      }
    };
    void init();
    return () => {
      cancelled = true;
      if (initializingUserIdRef.current === userId) initializingUserIdRef.current = null;
    };
  }, [activated, userId, setBot, setInitialized, setSessions, groupIntoSessions]);

  useEffect(() => { if (userId && new URLSearchParams(location.search).has('project')) setActivated(true); }, [userId, location.search]);

  const viewed = location.pathname === '/xiaoyu' ? conversationId : null;
  useLayoutEffect(() => {
    viewedRef.current = viewed;
    if (viewed) viewUnread(viewed);
    else leaveUnread(conversationId);
  }, [viewed, conversationId, viewUnread, leaveUnread]);

  useEffect(() => () => resetUnread(), [resetUnread]);

  const activate = useCallback(() => setActivated(true), []);
  const setPageHooks = useCallback((hooks: PageChatHooks | null) => {
    pageHooksRef.current = hooks ?? {};
  }, []);

  const chatRef = useRef(chat);
  useLayoutEffect(() => { chatRef.current = chat; }, [chat]);
  const openProject = useCallback(async (id: number, explicitConversation?: string, draft?: string) => {
    if (!userId || !Number.isSafeInteger(id) || id < 1) return;
    const sequence = ++openSequence.current;
    setOpeningProject(true);
    try {
      const { data } = await api.get<ProjectLearning>(`/ai/projects/${id}/learning/`);
      const current = chatRef.current;
      if (!current.bot || sequence !== openSequence.current || useAuthStore.getState().user?.id !== userId) return;
      const saved = readRecovery(recoveryScope(userId, current.bot.id));
      const draftEntry = explicitConversation ? undefined : Object.entries(saved.conversations)
        .filter(([, value]) => value.projectId === id && value.draft?.trim())
        .sort((a, b) => (b[1].updatedAt || 0) - (a[1].updatedAt || 0))[0];
      const selectedId = explicitConversation || draftEntry?.[0] || data.conversation_id;
      const response = await api.get<Message[]>('/ai/history/', { params: { bot_id: current.bot.id, ...(selectedId ? { conversation_id: selectedId } : {}) } });
      if (sequence !== openSequence.current || useAuthStore.getState().user?.id !== userId) return;
      const messages = restoreVisualSteps(response.data.filter(m => m.content !== '[Thinking...]').map(m => ({ ...m, visible: true })));
      const sessions = current.groupIntoSessions(messages);
      const candidates = sessions.filter(session => session.projectId === id);
      const target = selectedId ? candidates.find(session => session.conversationId === selectedId) : candidates.at(-1);
      if ((explicitConversation || (selectedId && messages.length > 0)) && !target) throw new Error('这段对话不属于当前项目，或已删除。');
      if (target) {
        current.setSessions(previous => [...previous.filter(item => item.conversationId !== target.conversationId), target]);
        current.handleLoadSession(target, false, true);
      } else {
        current.handleReset(false);
        if (draftEntry) current.setConversationId(draftEntry[0]);
        current.setProjectId(id);
        if (draftEntry?.[1].draft) current.setInput(draftEntry[1].draft);
        if (draft) current.setInput(draft);
      }
      queryClient.setQueryData(learningKey(userId, id), data);
      localStorage.setItem(`unimind:learning:project:${userId}`, String(id));
    } catch (error) {
      if (sequence === openSequence.current && useAuthStore.getState().user?.id === userId) {
        const status = (error as { response?: { status?: number } })?.response?.status;
        if (status === 404) {
          if (localStorage.getItem(`unimind:learning:project:${userId}`) === String(id)) localStorage.removeItem(`unimind:learning:project:${userId}`);
          if (chatRef.current.projectId === id) chatRef.current.handleReset(false);
        }
        toast.error(status === 404 ? '这个项目或对话已删除，无法恢复旧安排。' : error instanceof Error ? error.message : '项目暂时无法打开，请重试。');
      }
    } finally {
      if (sequence === openSequence.current) setOpeningProject(false);
    }
  }, [userId]);

  useEffect(() => {
    if (!userId || !chat.initialized) return;
    const params = new URLSearchParams(location.search);
    const explicit = params.get('project');
    const key = `${userId}:${explicit ? location.key : 'initial'}`;
    if (restored.current === key || (!explicit && restored.current.startsWith(`${userId}:`))) return;
    if (explicit && !/^\d+$/.test(explicit)) return;
    restored.current = key;
    const id = Number(explicit || localStorage.getItem(`unimind:learning:project:${userId}`));
    if (id) void openProject(id, explicit ? params.get('conversation') || undefined : undefined);
    if (explicit) {
      params.delete('project');
      params.delete('conversation');
      // Keep course context in its address. It is needed by the course assistant.
      if (location.pathname === '/xiaoyu') navigate({ pathname: location.pathname, search: params.toString() }, { replace: true });
    }
  }, [userId, chat.initialized, location.key, location.pathname, location.search, navigate, openProject]);
  useEffect(() => {
    if (userId && chat.projectId) localStorage.setItem(`unimind:learning:project:${userId}`, String(chat.projectId));
  }, [userId, chat.projectId]);
  useEffect(() => {
    if (!chat.loading && chat.projectId && userId) void queryClient.invalidateQueries({ queryKey: learningKey(userId, chat.projectId) });
  }, [chat.loading, chat.messages.at(-1)?.id, chat.projectId, userId]);
  useEffect(() => () => { ++openSequence.current; }, [userId]);

  const value = useMemo(
    () => ({ chat, unreadIds, activate, setPageHooks, openProject, openingProject }),
    [chat, unreadIds, activate, setPageHooks, openProject, openingProject],
  );
  return <XiaoYuChatContext.Provider value={value}>{children}</XiaoYuChatContext.Provider>;
}

/** 始终挂载，用户变化只在 Provider 内重置，不重挂路由子树。 */
export function XiaoYuChatHost() {
  return <XiaoYuChatProvider><Outlet /></XiaoYuChatProvider>;
}
