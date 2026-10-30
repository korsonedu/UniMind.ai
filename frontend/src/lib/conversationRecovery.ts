/** Desktop recovery stores identities and drafts; restoring never submits a chat. */
export interface PendingChatRequest {
  key: string;
  id: string;
  text: string;
  userMessageId?: string;
  serverMessageId?: number;
}
export interface SavedConversation {
  draft?: string;
  draftRevision?: string;
  pending?: PendingChatRequest;
}
export interface SavedConversations {
  lastConversationId?: string;
  conversations: Record<string, SavedConversation>;
}
const prefix = 'unimind:chat-recovery:';
export function recoveryScope(userId: number, botId: number) { return `${prefix}${userId}:${botId}`; }
export function readRecovery(scope: string | null): SavedConversations {
  try {
    const value = scope && localStorage.getItem(scope);
    const saved = value ? JSON.parse(value) : null;
    if (saved && typeof saved.conversations === 'object' && saved.conversations) return saved;
  } catch { /* Unavailable storage must not prevent chatting. */ }
  return { conversations: {} };
}
export function saveRecovery(scope: string | null, id: string, patch: SavedConversation, remember = false) {
  if (!scope) return;
  try {
    const saved = readRecovery(scope);
    saved.conversations[id] = { ...saved.conversations[id], ...patch };
    if (remember) saved.lastConversationId = id;
    localStorage.setItem(scope, JSON.stringify(saved));
  } catch { /* Best effort when the device has no storage capacity. */ }
}
export function deleteRecovery(scope: string | null, id: string) {
  if (!scope) return;
  try {
    const saved = readRecovery(scope);
    delete saved.conversations[id];
    if (saved.lastConversationId === id) delete saved.lastConversationId;
    localStorage.setItem(scope, JSON.stringify(saved));
  } catch { /* Best effort. */ }
}
export function clearConversationRecovery(userId: number) {
  try {
    for (const key of Object.keys(localStorage)) {
      if (key.startsWith(`${prefix}${userId}:`)) localStorage.removeItem(key);
    }
  } catch { /* Best effort. */ }
}
