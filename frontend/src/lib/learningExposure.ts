import type { Message } from '@/hooks/useAgentConversation';
import api, { backgroundRequest } from './api';

type Surface = 'chat_card' | 'hint_reply' | 'recheck_card' | 'practice_card';
const reportedPresentations = new Set<string>();

export function reportLearningExposure(messageId: number, surface: Surface, cardType = '') {
  const key = `${messageId}:${surface}:${cardType}`;
  if (reportedPresentations.has(key)) return;
  reportedPresentations.add(key);
  void api.post('/ai/learning/exposure/present/', { message_id: messageId, surface, card_type: cardType },
    backgroundRequest).catch(() => {});
}

export function reportMessageExposure(message: Message, showCards: boolean) {
  if (message.role !== 'assistant' || typeof message.id !== 'number' || message.visible === false) return;

  const teaching = message.metadata?.ulr_teaching as { presentation?: string; action?: string } | undefined;
  if (teaching?.presentation === 'unknown') {
    if (teaching.action === 'offer_recheck') {
      if (showCards) reportLearningExposure(message.id, 'recheck_card');
    } else {
      reportLearningExposure(message.id, 'hint_reply');
    }
  }
  const cards = message.metadata?.dsh_cards;
  if (!showCards || !Array.isArray(cards)) return;
  for (const card of cards) {
    if (card?.type === 'practice_quiz') {
      reportLearningExposure(message.id, 'practice_card', card.type);
    } else if (card?.type === 'manage_learning_tasks' || (card?.type === 'data_card' && card.tool === 'manage_learning_tasks')) {
      reportLearningExposure(message.id, 'chat_card', 'manage_learning_tasks');
    }
  }
}
