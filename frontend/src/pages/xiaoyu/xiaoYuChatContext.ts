import { createContext, useContext } from 'react';
import type { useAgentConversation } from '@/hooks/useAgentConversation';
import type { AgentStep } from '@/types/toolRun';

export interface PageChatHooks {
  beforeSend?: () => Promise<void>;
  getExtraPayload?: () => Record<string, unknown>;
  onDone?: () => void;
  onStepDoneEffect?: (step: AgentStep) => void;
  onAllVisuals?: (visuals: unknown[]) => void;
  onStepQuestions?: (questions: NonNullable<AgentStep['questions']>) => void;
}

export interface XiaoYuChatContextValue {
  chat: ReturnType<typeof useAgentConversation>;
  unreadIds: ReadonlySet<string>;
  openProject: (id: number, conversationId?: string, draft?: string) => Promise<void>;
  openingProject: boolean;
  activate: () => void;
  setPageHooks: (hooks: PageChatHooks | null) => void;
}

export const XiaoYuChatContext = createContext<XiaoYuChatContextValue | null>(null);

export function useXiaoYuChat() {
  const value = useContext(XiaoYuChatContext);
  if (!value) throw new Error('useXiaoYuChat must be used inside XiaoYuChatHost');
  return value;
}
