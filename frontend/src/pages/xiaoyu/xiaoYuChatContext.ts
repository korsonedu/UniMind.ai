import { createContext, useContext } from 'react';
import type { Bot, useAgentConversation } from '@/hooks/useAgentConversation';
import type { AgentStep } from '@/types/toolRun';

export const findAssistantBot = (bots: Bot[]) => bots.filter(bot => bot.name === '小宇' && bot.bot_type === 'planner' && bot.institution == null && bot.is_active !== false).sort((a, b) => a.id - b.id)[0];

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
  activate: () => void;
  setPageHooks: (hooks: PageChatHooks | null) => void;
}

export const XiaoYuChatContext = createContext<XiaoYuChatContextValue | null>(null);

export function useXiaoYuChat() {
  const value = useContext(XiaoYuChatContext);
  if (!value) throw new Error('useXiaoYuChat must be used inside XiaoYuChatHost');
  return value;
}
