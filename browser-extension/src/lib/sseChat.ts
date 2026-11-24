import { throwApiError, type ApiClient } from './api';
import type { ExternalVideoContextPayload } from '../shared/types';

export interface VisualData {
  type: string;
  payload: Record<string, unknown>;
  priority?: 'high' | 'normal' | 'low';
}

export interface ChatEvent extends Record<string, unknown> {
  type?: string;
  delta?: string;
  content?: string;
  text?: string;
  done?: boolean;
  full_content?: string;
  metadata?: Record<string, unknown>;
  conversation_title?: string;
  is_error?: boolean;
}

export interface ChatStreamState {
  content: string;
  visuals: VisualData[];
  metadata: Record<string, unknown>;
  conversationTitle?: string;
}

export interface ChatPayload {
  bot_id: number;
  conversation_id: string;
  message: string;
  project_id?: number | string | null;
  external_video_context?: ExternalVideoContextPayload;
  request_id?: string;
  [field: string]: unknown;
}

export function extractVisuals(input: unknown): VisualData[] {
  const visuals: VisualData[] = [];
  const visited = new Set<unknown>();
  const visit = (value: unknown) => {
    if (!value || typeof value !== 'object' || visited.has(value)) return;
    visited.add(value);
    if (Array.isArray(value)) {
      value.forEach(visit);
      return;
    }
    const record = value as Record<string, unknown>;
    if (typeof record.type === 'string' && record.payload && typeof record.payload === 'object' && !Array.isArray(record.payload)) {
      visuals.push(record as unknown as VisualData);
    }
    for (const field of ['visual', 'visuals', 'all_visuals', 'dsh_cards', 'metadata', 'toolStep']) visit(record[field]);
  };
  visit(input);
  return mergeVisuals([], visuals);
}

export function extractPracticeVisuals(input: unknown): VisualData[] {
  return extractVisuals(input).filter(visual => visual.type === 'practice_quiz');
}

function visualKey(visual: VisualData): string {
  const practiceId = visual.type === 'practice_quiz' && visual.payload.practice_id;
  return practiceId ? `practice_quiz:${practiceId}` : JSON.stringify(visual);
}

function mergeVisuals(previous: VisualData[], incoming: VisualData[]): VisualData[] {
  const merged = new Map(previous.map(visual => [visualKey(visual), visual]));
  incoming.forEach(visual => merged.set(visualKey(visual), visual));
  return [...merged.values()];
}

export function reduceChatEvent(state: ChatStreamState, event: ChatEvent): ChatStreamState {
  let content = state.content;
  if (event.type === 'text_reset') content = '';
  if (event.type === 'text_delta') content += event.delta ?? event.text ?? '';
  if (event.type === 'message' && typeof event.content === 'string') content = event.content;
  if ((event.done || event.type === 'done') && typeof event.full_content === 'string') content = event.full_content;
  const metadata = { ...state.metadata, ...event.metadata };
  const visuals = mergeVisuals(state.visuals, extractVisuals(event));
  return {
    content,
    visuals,
    metadata,
    conversationTitle: event.conversation_title ?? state.conversationTitle,
  };
}

export async function consumeSSE(
  stream: ReadableStream<Uint8Array>,
  onEvent: (event: ChatEvent) => void | Promise<void>,
): Promise<void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let data: string[] = [];
  let eventName = '';
  let completed = false;
  let terminal = false;
  const dispatch = async () => {
    if (!data.length) {
      eventName = '';
      return;
    }
    const message = data.join('\n');
    data = [];
    const name = eventName;
    eventName = '';
    if (message.trim() === '[DONE]') {
      await onEvent({ done: true });
      terminal = true;
      return;
    }
    let parsed: unknown;
    try { parsed = JSON.parse(message); }
    catch { throw new Error('收到无法解析的对话数据，请重试。'); }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return;
    const event = parsed as ChatEvent;
    if (name && !event.type) event.type = name;
    await onEvent(event);
    terminal = event.done === true || event.type === 'done';
  };
  const line = async (value: string) => {
    if (!value) return dispatch();
    if (value.startsWith(':')) return;
    const separator = value.indexOf(':');
    const field = separator < 0 ? value : value.slice(0, separator);
    let valueText = separator < 0 ? '' : value.slice(separator + 1);
    if (valueText.startsWith(' ')) valueText = valueText.slice(1);
    if (field === 'data') data.push(valueText);
    if (field === 'event') eventName = valueText;
  };
  const drain = async (final: boolean) => {
    let match: RegExpExecArray | null;
    while ((match = /\r\n|\r|\n/.exec(buffer))) {
      if (!final && match[0] === '\r' && match.index === buffer.length - 1) break;
      const value = buffer.slice(0, match.index);
      buffer = buffer.slice(match.index + match[0].length);
      await line(value);
      if (terminal) return;
    }
    if (final && buffer) {
      await line(buffer);
      buffer = '';
    }
  };
  try {
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) {
        buffer += decoder.decode();
        await drain(true);
        await dispatch();
        completed = true;
        return;
      }
      buffer += decoder.decode(chunk.value, { stream: true });
      await drain(false);
      if (terminal) return;
    }
  } finally {
    if (!completed) await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}

export interface StreamChatOptions {
  signal?: AbortSignal;
  onEvent?: (event: ChatEvent) => void;
  onUpdate?: (state: ChatStreamState, event: ChatEvent) => void;
}

function streamError(event: ChatEvent): string {
  if (typeof event.full_content === 'string' && event.full_content) return event.full_content;
  if (typeof event.error === 'string') return event.error;
  if (event.error && typeof event.error === 'object') {
    const message = (event.error as Record<string, unknown>).message;
    if (typeof message === 'string') return message;
  }
  return typeof event.message === 'string' ? event.message : '对话暂时中断，请重试。';
}

export async function streamChat(
  api: ApiClient,
  payload: ChatPayload,
  options: StreamChatOptions = {},
): Promise<ChatStreamState> {
  const response = await api.fetch('/ai/chat/stream/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream, application/json' },
    body: JSON.stringify(payload),
    signal: options.signal,
  });
  if (!response.ok) return throwApiError(response);
  if (!response.body) throw new Error('浏览器未提供对话流，请重试。');
  let state: ChatStreamState = { content: '', visuals: [], metadata: {} };
  let done = false;
  await consumeSSE(response.body, event => {
    if (done) return;
    state = reduceChatEvent(state, event);
    options.onUpdate?.(state, event);
    options.onEvent?.(event);
    if (event.is_error || event.type === 'error' || (!event.type && event.error)) {
      throw new Error(streamError(event));
    }
    if (event.done || event.type === 'done') done = true;
  });
  if (!done) throw new Error('连接已中断，回答可能尚未完成，请重试。');
  return state;
}
