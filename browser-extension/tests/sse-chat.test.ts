import { afterEach, describe, expect, it, vi } from 'vitest';
import { createApiClient } from '../src/lib/api';
import { consumeSSE, extractPracticeVisuals, streamChat, type ChatEvent } from '../src/lib/sseChat';

const practice = { type: 'practice_quiz', payload: { practice_id: 'practice-a', title: '随堂习题' } };
const otherPractice = { type: 'practice_quiz', payload: { practice_id: 'practice-b', title: '第二份习题' } };
const message = { bot_id: 4, conversation_id: '00000000-0000-4000-8000-000000000001', message: '解释一下', project_id: null };
const client = createApiClient({ serverOrigin: 'http://localhost:5173', token: 'fixture-token' });

function encodedStream(source: string, chunkLength = 3): ReadableStream<Uint8Array> {
  const data = new TextEncoder().encode(source);
  let offset = 0;
  return new ReadableStream({
    pull(controller) {
      if (offset >= data.length) { controller.close(); return; }
      controller.enqueue(data.slice(offset, offset + chunkLength));
      offset += chunkLength;
    },
  });
}

afterEach(() => vi.unstubAllGlobals());

describe('小宇 SSE', () => {
  it('拆包读取 CRLF、事件名称、注释、多行 data 和末尾数据', async () => {
    const events: ChatEvent[] = [];
    const source = ': heartbeat\r\n\r\nevent: text_delta\r\ndata: {\r\ndata: "delta":"折现率"}\r\n\r\n'
      + 'data: {"done":true}';
    await consumeSSE(encodedStream(source, 1), event => { events.push(event); });
    expect(events).toEqual([{ type: 'text_delta', delta: '折现率' }, { done: true }]);
  });

  it('合并标准和 DSH 增量与练习，使用最终正文及标题，并通过 Vite 端口发送 Token', async () => {
    const source = [
      { type: 'text_delta', delta: '先算' },
      { type: 'step', visual: practice },
      { type: 'message', content: '先算现值' },
      { type: 'text_reset' },
      { type: 'text_delta', delta: '然后' },
      { dsh_cards: [otherPractice] },
      { done: true, full_content: '最终推导', metadata: { dsh_cards: [practice, otherPractice], engine: 'dsh' }, conversation_title: '折现课程' },
    ].map(event => `data: ${JSON.stringify(event)}\n\n`).join('');
    const fetch = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>()
      .mockResolvedValue(new Response(encodedStream(source), { headers: { 'Content-Type': 'text/event-stream' } }));
    vi.stubGlobal('fetch', fetch);
    const updated: string[] = [];
    const result = await streamChat(client, message, { onUpdate: state => updated.push(state.content) });
    expect(updated).toEqual(['先算', '先算', '先算现值', '', '然后', '然后', '最终推导']);
    expect(result).toEqual({
      content: '最终推导',
      visuals: [practice, otherPractice],
      metadata: { dsh_cards: [practice, otherPractice], engine: 'dsh' },
      conversationTitle: '折现课程',
    });
    const request = fetch.mock.calls[0]?.[1];
    expect(fetch.mock.calls[0]?.[0]).toBe('http://localhost:5173/api/ai/chat/stream/');
    expect(request?.credentials).toBe('omit');
    expect(new Headers(request?.headers).get('Authorization')).toBe('Token fixture-token');
    expect(new Headers(request?.headers).get('Accept-Language')).toBe('zh-CN');
    expect(new Headers(request?.headers).get('Accept')).toBe('text/event-stream, application/json');
    expect(JSON.parse(String(request?.body))).toEqual(message);
  });

  it('恢复历史消息中多个来源的练习并按 practice_id 去重', () => {
    expect(extractPracticeVisuals({
      metadata: { visual: practice, all_visuals: [practice], dsh_cards: [practice, otherPractice] },
    })).toEqual([practice, otherPractice]);
  });

  it('收到完成标志后交付结果，即使连接仍保持打开', async () => {
    const cancel = vi.fn();
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('data: {"done":true,"full_content":"已完成"}\n\n'));
      },
      cancel,
    });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body)));
    expect(await streamChat(client, message)).toMatchObject({ content: '已完成' });
    expect(cancel).toHaveBeenCalledOnce();
  });

  it('工具失败附带的错误允许继续，标准引擎的终止错误保留原提示', async () => {
    const source = 'data: {"type":"step","status":"failed","error":{"message":"工具暂时不可用"}}\n\n'
      + 'data: {"error":"连接中断，请稍后再试。"}\n\n';
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(encodedStream(source))));
    const seen = vi.fn();
    await expect(streamChat(client, message, { onEvent: seen })).rejects.toThrow('连接中断，请稍后再试。');
    expect(seen).toHaveBeenCalledTimes(2);
  });
});
