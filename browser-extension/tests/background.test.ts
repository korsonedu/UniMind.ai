import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { installMediaHeaders, transcribeDashAudio, uploadAudioSnippet } from '../src/collectors/dash-range';
import background from '../src/entrypoints/background';
import { collectTabAudio, setTabAudioEnabled, stopTabAudio } from '../src/entrypoints/offscreen/client';
import { syncCookieToken } from '../src/lib/auth';
import { readSession } from '../src/lib/storage';
import {
  UNIMIND_AUTH_SYNC, UNIMIND_CAPTURE_CONTEXT_FOR_ASK, UNIMIND_COLLECT_PAGE_SNAPSHOT,
  UNIMIND_OPEN_SIDEPANEL, UNIMIND_TOGGLE_TAB_AUDIO, type BridgeMessage,
} from '../src/shared/bridge';
import type { ActiveVideoDescriptor, CaptureContextResult, PageCollectSnapshot } from '../src/shared/types';

vi.mock('../src/lib/auth', () => ({
  handleAuthCookieChange: vi.fn().mockResolvedValue(undefined),
  syncCookieToken: vi.fn().mockResolvedValue('fixture-token'),
}));
vi.mock('../src/lib/storage', () => ({ readSession: vi.fn() }));
vi.mock('../src/collectors/dash-range', () => ({
  installMediaHeaders: vi.fn(),
  transcribeDashAudio: vi.fn(),
  uploadAudioSnippet: vi.fn(),
}));
vi.mock('../src/entrypoints/offscreen/client', () => ({
  installOffscreenAudioBridge: vi.fn(),
  collectTabAudio: vi.fn(),
  setTabAudioEnabled: vi.fn(),
  stopTabAudio: vi.fn(),
}));

type MessageListener = (
  message: BridgeMessage, sender: chrome.runtime.MessageSender, respond: (value: unknown) => void,
) => boolean | undefined;

const descriptor: ActiveVideoDescriptor = {
  video_key: 'bilibili:fixture:p2', platform: 'bilibili', external_id: 'fixture', part: 2,
  url: 'https://www.bilibili.com/video/fixture?p=2', title: '测试视频',
};
const session = {
  serverOrigin: 'https://uni.example', token: 'fixture-token', user: null, tokenSource: 'inline' as const,
};
const track = { url: 'https://unit.bilivideo.com/audio.m4s' };
const transcript = [{ start_time: 318, end_time: 322, text: '讲稿' }];
const visualFrame = { video_seconds: 320, image: 'data:image/jpeg;base64,AA==' };
const dashSnapshot: PageCollectSnapshot = {
  descriptor, paused: false, video_seconds: 320, transcript_source: 'none', segments: [],
  dash_audio: track, direct_visual: { current: visualFrame },
};

describe('Background 页面采集与录音路由', () => {
  const query = vi.fn();
  const sendMessage = vi.fn();
  const setPanelBehavior = vi.fn();
  const open = vi.fn();
  const onClicked = vi.fn();
  const onRemoved = vi.fn();
  const onUpdated = vi.fn();
  let listener: MessageListener;

  beforeEach(() => {
    vi.resetAllMocks();
    query.mockResolvedValue([{ id: 4 }]);
    open.mockResolvedValue(undefined);
    setPanelBehavior.mockResolvedValue(undefined);
    vi.mocked(syncCookieToken).mockResolvedValue('fixture-token');
    vi.mocked(readSession).mockResolvedValue(session);
    vi.mocked(installMediaHeaders).mockResolvedValue(undefined);
    vi.mocked(stopTabAudio).mockResolvedValue(undefined);
    vi.stubGlobal('chrome', {
      action: { onClicked: { addListener: onClicked } },
      cookies: { onChanged: { addListener: vi.fn() } },
      sidePanel: { open, setPanelBehavior },
      tabs: { query, sendMessage, onRemoved: { addListener: onRemoved }, onUpdated: { addListener: onUpdated } },
      runtime: {
        onInstalled: { addListener: vi.fn() },
        onStartup: { addListener: vi.fn() },
        onMessage: { addListener: (handler: MessageListener) => { listener = handler; } },
        getURL: (path: string) => `chrome-extension://fixture${path}`,
      },
    });
    background.main();
  });

  afterEach(() => vi.unstubAllGlobals());

  it('打开原生侧栏，并用请求指定的 Tab 采集字幕和双帧', async () => {
    expect(setPanelBehavior).toHaveBeenCalledWith({ openPanelOnActionClick: false });
    onClicked.mock.calls[0]?.[0]({ id: 4, windowId: 2 });
    expect(open).toHaveBeenCalledWith({ windowId: 2 });
    const response = vi.fn();
    const sender = { tab: { id: 4 } } as chrome.runtime.MessageSender;
    expect(listener({ type: UNIMIND_OPEN_SIDEPANEL }, sender, response)).toBe(true);
    expect(open).toHaveBeenCalledWith({ tabId: 4 });
    await vi.waitFor(() => expect(response).toHaveBeenCalledWith({ ok: true }));

    const snapshot: PageCollectSnapshot = {
      descriptor, paused: false, video_seconds: 320,
      transcript_source: 'platform_cc',
      segments: [{ start_time: 318, end_time: 322, text: '讲稿' }],
      direct_visual: { current: { video_seconds: 320, image: 'data:image/jpeg;base64,AA==' } },
      previous_frame: { video_seconds: 314, image: 'data:image/jpeg;base64,AQ==' },
    };
    sendMessage.mockResolvedValueOnce(snapshot);
    const captured = new Promise(resolve => listener({
      type: UNIMIND_CAPTURE_CONTEXT_FOR_ASK, payload: { tabId: 9 },
    }, {}, resolve));
    expect(await captured).toEqual({
      ok: true, descriptor, warnings: [],
      context: {
        platform: descriptor.platform, external_id: descriptor.external_id, part: 2,
        url: descriptor.url, title: descriptor.title, video_seconds: 320,
        transcript_source: 'platform_cc', segments: snapshot.segments,
        visual: { current: snapshot.direct_visual?.current, previous: snapshot.previous_frame },
        integration_hooks: { knowledge_tree_id: null, knowledge_node_id: null, memory_event_target: null },
      },
    });
    expect(sendMessage).toHaveBeenCalledWith(9, { type: UNIMIND_COLLECT_PAGE_SNAPSHOT });
    expect(query).not.toHaveBeenCalled();
    expect(readSession).not.toHaveBeenCalled();
    expect(transcribeDashAudio).not.toHaveBeenCalled();
    expect(collectTabAudio).not.toHaveBeenCalled();
  });

  function ask(tabId: number) {
    return new Promise<CaptureContextResult>(resolve => listener({
      type: UNIMIND_CAPTURE_CONTEXT_FOR_ASK, payload: { tabId },
    }, {}, value => resolve(value as CaptureContextResult)));
  }

  it('使用 DASH 转写的绝对字幕，有结果时跳过实时录音', async () => {
    const snapshot = { ...dashSnapshot, direct_visual: null, cors_fallback_rect: {
      x: 5, y: 5, width: 400, height: 200, devicePixelRatio: 1, viewportWidth: 800, viewportHeight: 600,
    } };
    sendMessage.mockResolvedValueOnce(snapshot);
    vi.stubGlobal('chrome', {
      ...chrome,
      tabs: { ...chrome.tabs, get: vi.fn().mockRejectedValue(new Error('截图失败')) },
    });
    vi.mocked(transcribeDashAudio).mockResolvedValueOnce({ available: true, warnings: [], segments: transcript });

    const result = await ask(10);
    expect(result.context).toMatchObject({ segments: transcript, transcript_source: 'dash_range_asr' });
    expect(result.context?.visual).toBeUndefined();
    expect(result.warnings).toEqual(['截图失败']);
    expect(transcribeDashAudio).toHaveBeenCalledWith({
      descriptor, track, targetSeconds: 320, serverOrigin: session.serverOrigin, token: session.token,
    });
    expect(collectTabAudio).not.toHaveBeenCalled();
  });

  it('DASH 转写无结果时使用 Offscreen 音频，保留画面及采集告警', async () => {
    const audio = new Blob(['fixture'], { type: 'audio/wav' });
    sendMessage.mockResolvedValueOnce(dashSnapshot);
    vi.mocked(transcribeDashAudio).mockResolvedValueOnce({
      available: false, warnings: ['DASH 未找到 sidx'], segments: [],
    });
    vi.mocked(collectTabAudio).mockResolvedValueOnce({ audio, clipStartSeconds: 267 });
    vi.mocked(uploadAudioSnippet).mockResolvedValueOnce({ available: true, warnings: [], segments: transcript });

    const result = await ask(11);
    expect(result.context).toMatchObject({
      segments: transcript, transcript_source: 'tab_capture_asr', visual: { current: visualFrame },
    });
    expect(result.warnings).toEqual(['DASH 未找到 sidx']);
    expect(collectTabAudio).toHaveBeenCalledWith(11, dashSnapshot);
    expect(uploadAudioSnippet).toHaveBeenCalledWith({
      audio, clipStartSeconds: 267, descriptor, serverOrigin: session.serverOrigin, token: session.token,
    });
  });

  it('未登录时返回标题与画面，省略音频上传', async () => {
    sendMessage.mockResolvedValueOnce(dashSnapshot);
    vi.mocked(readSession).mockResolvedValueOnce({ ...session, token: null });
    const result = await ask(12);
    expect(result.context).toMatchObject({
      title: descriptor.title, segments: [], transcript_source: 'none', visual: { current: visualFrame },
    });
    expect(transcribeDashAudio).not.toHaveBeenCalled();
    expect(collectTabAudio).not.toHaveBeenCalled();
  });

  it('慢转写在侧栏截止前返回已有画面和标题', async () => {
    vi.useFakeTimers();
    try {
      sendMessage.mockResolvedValueOnce(dashSnapshot);
      vi.mocked(transcribeDashAudio).mockReturnValueOnce(new Promise(() => {}));
      const response = ask(13);
      await vi.advanceTimersByTimeAsync(3700);
      expect(await response).toMatchObject({
        ok: true, warnings: ['音频转写仍在处理，已继续采集播放信息。'],
        context: { title: descriptor.title, segments: [], transcript_source: 'none', visual: { current: visualFrame } },
      });
    } finally {
      vi.useRealTimers();
    }
  });

  it('按用户消息切换录音，关闭或重新加载 Tab 时停止', async () => {
    vi.mocked(setTabAudioEnabled).mockResolvedValueOnce({ enabled: true });
    const result = await new Promise(resolve => listener({
      type: UNIMIND_TOGGLE_TAB_AUDIO, payload: { enabled: true },
    }, {}, resolve));
    expect(result).toEqual({ enabled: true });
    expect(setTabAudioEnabled).toHaveBeenCalledWith(4, true);
    onRemoved.mock.calls[0]?.[0](4);
    onUpdated.mock.calls[0]?.[0](5, { status: 'loading' });
    expect(stopTabAudio).toHaveBeenNthCalledWith(1, 4);
    expect(stopTabAudio).toHaveBeenNthCalledWith(2, 5);
  });

  it('无内容脚本时返回空上下文，不阻塞通用问答', async () => {
    sendMessage.mockRejectedValue(new Error('Receiving end does not exist'));
    const response = new Promise(resolve => listener({ type: UNIMIND_CAPTURE_CONTEXT_FOR_ASK }, {}, resolve));
    expect(await response).toEqual({ ok: false, descriptor: null, context: null, warnings: [] });
  });

  it('只对扩展页面返回主站 Token', async () => {
    const message: BridgeMessage = { type: UNIMIND_AUTH_SYNC };
    const response = vi.fn();
    const sender = { tab: { id: 4 }, url: descriptor.url } as chrome.runtime.MessageSender;
    expect(listener(message, sender, response)).toBeUndefined();
    expect(response).not.toHaveBeenCalled();
    const result = await new Promise(resolve => listener(message, {}, resolve));
    expect(result).toEqual({ token: 'fixture-token' });
  });
});
