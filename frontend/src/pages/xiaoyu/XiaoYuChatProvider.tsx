import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { toast } from 'sonner';
import api from '@/lib/api';
import { restoreVisualSteps } from '@/lib/visualHistory';
import { useAgentConversation, type Bot, type Message } from '@/hooks/useAgentConversation';
import { useAuthStore } from '@/store/useAuthStore';
import { useChatUnreadStore } from '@/store/useChatUnreadStore';
import { XiaoYuChatContext, findAssistantBot, type PageChatHooks } from './xiaoYuChatContext';

/**
 * 路由级常驻聊天。Provider 在 Router 根部挂载，路由切换只卸载页面 UI，
 * SSE 流、会话快照和输入草稿仍由 useAgentConversation 持有。
 */
export function XiaoYuChatProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const [activated, setActivated] = useState(false);
  const pageHooksRef = useRef<PageChatHooks>({});
  const viewedRef = useRef<string | null>(null);
  const initializingRef = useRef(false);
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
  const { initialized, conversationId, setBot, setInitialized, setSessions, groupIntoSessions } = chat;

  useEffect(() => {
    if (!activated || initialized || initializingRef.current) return;
    initializingRef.current = true;
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
        if (!cancelled) setInitialized(true);
      }
    };
    void init();
    return () => { cancelled = true; };
  }, [activated, initialized, setBot, setInitialized, setSessions, groupIntoSessions]);

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

  const value = useMemo(
    () => ({ chat, unreadIds, activate, setPageHooks }),
    [chat, unreadIds, activate, setPageHooks],
  );
  return <XiaoYuChatContext.Provider value={value}>{children}</XiaoYuChatContext.Provider>;
}

/** 登录后挂载，路由切换不卸载。未登录时只渲染路由。 */
export function XiaoYuChatHost() {
  const user = useAuthStore(state => state.user);
  if (!user) return <Outlet />;
  return <XiaoYuChatProvider key={user.id}><Outlet /></XiaoYuChatProvider>;
}
