/** 流式文本、轮次结束和最终结果共用气泡，保留已有消息信息。 */
export function upsertChatMessage<T extends { _id?: string }>(
  messages: T[],
  message: T & { _id: string },
): T[] {
  const index = messages.findIndex(item => item._id === message._id);
  if (index < 0) return [...messages, message];
  const updated = [...messages];
  updated[index] = { ...messages[index], ...message };
  return updated;
}
