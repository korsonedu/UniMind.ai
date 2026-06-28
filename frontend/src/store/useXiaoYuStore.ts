import { create } from 'zustand';
import type { AgentStep } from '@/hooks/useAgentChat';

export interface XiaoYuMessage {
  _id: string;
  role: 'user' | 'assistant';
  content: string;
  visible: boolean;
  timestamp: string;
  toolStep?: AgentStep;
  id?: number;
  feedback?: boolean | null;
  conversation_id?: string;
  conversation_title?: string;
  metadata?: Record<string, unknown>;
}

interface XiaoYuState {
  messages: XiaoYuMessage[];
  loading: boolean;
  conversationId: string;
  botId: number | null;
  /** SSE send function — injected by useXiaoYuEngine at App level */
  sendMessage: ((text: string) => void) | null;

  // Actions
  setMessages: (messages: XiaoYuMessage[] | ((prev: XiaoYuMessage[]) => XiaoYuMessage[])) => void;
  addMessage: (msg: XiaoYuMessage) => void;
  setLoading: (v: boolean) => void;
  setBotId: (id: number) => void;
  setConversationId: (id: string) => void;
  setSendMessage: (fn: ((text: string) => void) | null) => void;
  reset: () => void;
}

const initialConversationId = () => crypto.randomUUID();

export const useXiaoYuStore = create<XiaoYuState>((set) => ({
  messages: [],
  loading: false,
  conversationId: initialConversationId(),
  botId: null,
  sendMessage: null,

  setMessages: (messages) =>
    set((state) => ({
      messages: typeof messages === 'function' ? messages(state.messages) : messages,
    })),

  addMessage: (msg) =>
    set((state) => ({ messages: [...state.messages, msg] })),

  setLoading: (loading) => set({ loading }),

  setBotId: (botId) => set({ botId }),

  setConversationId: (conversationId) => set({ conversationId }),

  setSendMessage: (sendMessage) => set({ sendMessage }),

  reset: () =>
    set({
      messages: [],
      loading: false,
      conversationId: initialConversationId(),
    }),
}));
