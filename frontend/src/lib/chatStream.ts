import { streamFetch } from '@/lib/api';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type ChatStreamPayload = Record<string, any>;

interface ReadChatStreamOptions {
  body: Record<string, unknown>;
  signal: AbortSignal;
  isCurrent: () => boolean;
}

/**
 * 统一的小宇/工作台 SSE 读取器。
 * 只负责请求、解码和按行解析，事件语义由调用方处理。
 */
export async function* readChatStream({
  body,
  signal,
  isCurrent,
}: ReadChatStreamOptions): AsyncGenerator<ChatStreamPayload> {
  const { url, init } = streamFetch('/api/ai/chat/stream/', body, signal);
  const res = await fetch(url, init);
  if (!isCurrent()) return;
  if (!res.ok) throw new Error(`HTTP ${res.status}`);

  const reader = res.body?.getReader();
  if (!reader) throw new Error('Stream not available');

  const decoder = new TextDecoder();
  let leftover = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (!isCurrent()) {
        await reader.cancel();
        return;
      }
      if (done) break;

      leftover += decoder.decode(value, { stream: true });
      const lines = leftover.split('\n');
      leftover = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        let payload: ChatStreamPayload;
        try {
          payload = JSON.parse(line.slice(6));
        } catch {
          continue;
        }
        yield payload;
        if (!isCurrent()) {
          await reader.cancel();
          return;
        }
      }
    }
  } finally {
    try {
      await reader.cancel();
    } catch {
      /* stream already closed */
    }
  }
}
