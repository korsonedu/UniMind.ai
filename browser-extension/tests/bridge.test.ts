import { describe, expect, it, vi } from 'vitest';
import {
  formatVideoKey, parseSeekSeconds, sendRuntimeMessage, sendTabMessage,
  UNIMIND_CAPTURE_CONTEXT_FOR_ASK, UNIMIND_SEEK_VIDEO, UNIMIND_VIDEO_STATE_CHANGED,
} from '../src/shared/bridge';

describe('视频唯一键', () => {
  it('保留 B 站默认分 P 和其他平台非首分 P', () => {
    expect(formatVideoKey('bilibili', 'BV1', 0)).toBe('bilibili:BV1:p1');
    expect(formatVideoKey('bilibili', 'BV1', 2)).toBe('bilibili:BV1:p2');
    expect(formatVideoKey('youtube', 'id', 1)).toBe('youtube:id');
    expect(formatVideoKey('generic', 'url', 3)).toBe('generic:url:p3');
  });
});

describe('跳播时间戳', () => {
  it.each([
    ['#seek:320.5', 320.5], ['[05:20]', 320], ['[01:02:03]', 3723],
    ['[1:02:15]', 3735], ['#seek:0', 0], ['05:20', 320],
    ['[01:60]', null], ['[01:62:03]', null], ['#seek:-2', null],
    ['[01:02', null], ['https://site/#seek:2', null],
  ])('解析 %s', (input, seconds) => {
    expect(parseSeekSeconds(input)).toBe(seconds);
  });
});

it('为 Wave 2 保持统一的消息外形', async () => {
  const tab = vi.fn().mockResolvedValue({ ok: true });
  const runtime = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal('chrome', { tabs: { sendMessage: tab }, runtime: { sendMessage: runtime } });
  try {
    await sendTabMessage(18, UNIMIND_SEEK_VIDEO, { seconds: 320.5 });
    await sendRuntimeMessage(UNIMIND_CAPTURE_CONTEXT_FOR_ASK);
    await sendRuntimeMessage(UNIMIND_VIDEO_STATE_CHANGED, null);
    expect(tab).toHaveBeenCalledWith(18, { type: UNIMIND_SEEK_VIDEO, payload: { seconds: 320.5 } });
    expect(runtime.mock.calls).toEqual([
      [{ type: UNIMIND_CAPTURE_CONTEXT_FOR_ASK }],
      [{ type: UNIMIND_VIDEO_STATE_CHANGED, payload: null }],
    ]);
  } finally {
    vi.unstubAllGlobals();
  }
});
