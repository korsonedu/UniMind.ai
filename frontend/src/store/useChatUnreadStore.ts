import { create } from 'zustand';

export type RunOutcome = 'completed' | 'error';

interface ChatUnreadState {
  unread: Record<string, true>;
  viewedConversationId: string | null;
  markSettled: (conversationId: string, outcome: RunOutcome) => void;
  view: (conversationId: string) => void;
  leave: (conversationId: string) => void;
  remove: (conversationId: string) => void;
  reset: () => void;
}

/** 未读只记录后台会话停住的结果；生成中由 thinking 点表达。 */
export const useChatUnreadStore = create<ChatUnreadState>((set) => ({
  unread: {},
  viewedConversationId: null,

  markSettled: (conversationId, outcome) => set(state => {
    if (outcome !== 'completed' && outcome !== 'error') return state;
    if (state.viewedConversationId === conversationId || state.unread[conversationId]) return state;
    return { unread: { ...state.unread, [conversationId]: true } };
  }),

  view: (conversationId) => set(state => {
    if (state.viewedConversationId === conversationId && !state.unread[conversationId]) return state;
    const unread = { ...state.unread };
    delete unread[conversationId];
    return { viewedConversationId: conversationId, unread };
  }),

  leave: (conversationId) => set(state =>
    state.viewedConversationId === conversationId ? { viewedConversationId: null } : state,
  ),

  remove: (conversationId) => set(state => {
    if (!state.unread[conversationId] && state.viewedConversationId !== conversationId) return state;
    const unread = { ...state.unread };
    delete unread[conversationId];
    return {
      unread,
      viewedConversationId: state.viewedConversationId === conversationId ? null : state.viewedConversationId,
    };
  }),

  reset: () => set({ unread: {}, viewedConversationId: null }),
}));
