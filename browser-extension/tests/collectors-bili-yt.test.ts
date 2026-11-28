// @vitest-environment jsdom
// @vitest-environment-options {"url":"https://www.youtube.com/watch?v=abcdefghijk"}
import { describe, expect, it, vi } from 'vitest';
import {
  extractBilibiliDashAudio, getWbiMixinKey, parseBilibiliSubtitles, parseBilibiliVideoUrl,
  resolveBilibiliPageState, selectBilibiliSubtitle, signWbiParams,
} from '../src/collectors/bilibili';
import { installBilibiliNetworkObserver } from '../src/collectors/bilibili/main';
import { installPageMediaCollector, sliceTranscriptWindow } from '../src/collectors/transcriptWindow';
import {
  extractYouTubeDashAudio, extractYouTubePlayerResponse, parseYouTubeJson3, parseYouTubeVideoUrl,
  selectCurrentYouTubePlayerResponse, selectYouTubeCaptionTrack,
} from '../src/collectors/youtube';
import { createYouTubeCollector } from '../src/collectors/youtube/collector';
import { observePlayerUi } from '../src/collectors/playerUi';
import videoBridge from '../src/entrypoints/video-bridge.content';
import {
  UNIMIND_COLLECT_PAGE_SNAPSHOT, UNIMIND_GET_ACTIVE_VIDEO, UNIMIND_OPEN_SIDEPANEL,
  UNIMIND_SEEK_VIDEO, UNIMIND_VIDEO_STATE_CHANGED, type BridgeMessage, type MessageResponses,
} from '../src/shared/bridge';

const BILI_ID = 'BV1xx411c7mD';
const BILI_URL = `https://www.bilibili.com/video/${BILI_ID}`;
const YOUTUBE_ID = 'abcdefghijk';
const YOUTUBE_URL = `https://www.youtube.com/watch?v=${YOUTUBE_ID}`;

describe('B 站字幕与音轨', () => {
  it('按标准 WBI 向量生成混合盐和 w_rid', () => {
    const img = 'https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png';
    const sub = 'https://i0.hdslb.com/bfs/wbi/4932caff0ff746eab6f01bf08b70ac45.png';
    expect(getWbiMixinKey(img, sub)).toBe('ea1db124af3c7062474693fa704f4ff8');
    expect(signWbiParams({ foo: '114', bar: '514', zab: 1919810 }, img, sub, 1702204169)).toEqual({
      foo: '114', bar: '514', zab: '1919810', wts: '1702204169',
      w_rid: '8f6f2b5b3d485fe1886cec6a0be8c5d4',
    });
  });

  it('优先人工中文字幕，再选 ai-zh 并补齐协议', () => {
    const english = { lan: 'en', subtitle_url: '//aisubtitle.hdslb.com/en.json' };
    const ai = { lan: 'ai-zh', subtitle_url: '//aisubtitle.hdslb.com/ai.json' };
    const chinese = { lan: 'zh-Hans', subtitle_url: '//aisubtitle.hdslb.com/zh.json' };
    expect(selectBilibiliSubtitle({ data: { subtitle: { subtitles: [english, ai, chinese] } } }))
      .toEqual({ lan: 'zh-Hans', subtitle_url: 'https://aisubtitle.hdslb.com/zh.json', isAI: false });
    expect(selectBilibiliSubtitle([english, ai])).toMatchObject({ lan: 'ai-zh', isAI: true });
  });

  it('从字幕 body 提取并清洗句级时间轴', () => {
    expect(parseBilibiliSubtitles({ body: [
      { from: 5.2, to: 7.8, content: ' 第二句\n 接下去 ' },
      { from: 0, to: 3, content: '第一句' },
      { from: 4, to: 4, content: '无效时间' },
      { from: 4, to: 5, content: '\n  ' },
    ] })).toEqual([
      { start_time: 0, end_time: 3, text: '第一句' },
      { start_time: 5.2, end_time: 7.8, text: '第二句 接下去' },
    ]);
  });

  it('按 URL 的分 P 读 cid 并拒绝复用另一 BV 的初始状态', () => {
    const state = { videoData: {
      bvid: BILI_ID, aid: 10, cid: 100, title: '课程',
      pages: [{ page: 1, cid: 100 }, { page: 2, cid: 200, part: '第二讲', duration: 75 }],
    } };
    expect(resolveBilibiliPageState(`${BILI_URL}?p=2`, state)).toMatchObject({
      cid: 200, aid: 10, bvid: BILI_ID, descriptor: { part: 2, title: '课程 · 第二讲', duration: 75 },
    });
    expect(resolveBilibiliPageState(`${BILI_URL}?p=3`, state)?.cid).toBeUndefined();
    expect(resolveBilibiliPageState('https://www.bilibili.com/video/BVother', state)?.cid).toBeUndefined();
  });

  it('选择最低码率纯音轨并识别两种 SegmentBase 命名', () => {
    expect(extractBilibiliDashAudio({ data: { dash: { audio: [
      { baseUrl: 'https://cdn.bilivideo.com/hq', bandwidth: 128000, SegmentBase: { Initialization: '0-999' } },
      { base_url: '//cdn.bilivideo.com/lq', bandwidth: 64000, mime_type: 'audio/mp4',
        segment_base: { initialization: '0-899', index_range: '900-1900' } },
    ] } } })).toMatchObject({
      url: 'https://cdn.bilivideo.com/lq', bandwidth: 64000, mimeType: 'audio/mp4',
      initRange: '0-899', indexRange: '900-1900', referer: 'https://www.bilibili.com/',
    });
    expect(extractBilibiliDashAudio({ dash: { audio: [
      { baseUrl: 'https://cdn.bilivideo.com/low', bandwidth: 1, SegmentBase: { Initialization: '0-100', indexRange: '101-200' } },
    ] } })).toMatchObject({ initRange: '0-100', indexRange: '101-200' });
  });

  it('被动观察 fetch 和 XHR，保留原 Promise、响应和异常', async () => {
    const payload = { code: 0, data: { subtitle: { subtitles: [] } } };
    const response = new Response(JSON.stringify(payload));
    const promise = Promise.resolve(response);
    const originalFetch = vi.spyOn(window, 'fetch').mockReturnValue(promise);
    const open = vi.spyOn(XMLHttpRequest.prototype, 'open').mockImplementation(() => undefined);
    const send = vi.spyOn(XMLHttpRequest.prototype, 'send').mockImplementation(() => undefined);
    const observed = vi.fn();
    const key = `bilibili:${BILI_ID}:p2`;
    const stop = installBilibiliNetworkObserver(observed, () => key);
    const endpoint = `https://api.bilibili.com/x/player/wbi/v2?bvid=${BILI_ID}&cid=200`;
    try {
      expect(window.fetch(endpoint)).toBe(promise);
      expect(await promise).toBe(response);
      expect(response.bodyUsed).toBe(false);
      await vi.waitFor(() => expect(observed).toHaveBeenCalledWith(
        payload, expect.objectContaining({ url: new URL(endpoint), videoKey: key }),
      ));

      const failure = new Error('fetch network error');
      const rejected = Promise.reject(failure);
      originalFetch.mockReturnValueOnce(rejected);
      const result = window.fetch(endpoint);
      expect(result).toBe(rejected);
      await expect(result).rejects.toBe(failure);

      const xhr = new XMLHttpRequest();
      Object.defineProperties(xhr, { responseType: { value: 'json' }, response: { value: payload } });
      xhr.open('GET', endpoint, true);
      xhr.send(null);
      xhr.dispatchEvent(new Event('load'));
      expect(open).toHaveBeenCalledWith('GET', endpoint, true);
      expect(send).toHaveBeenCalledWith(null);
      expect(observed).toHaveBeenCalledTimes(2);
    } finally {
      stop();
      vi.restoreAllMocks();
    }
  });
});

describe('YouTube 字幕、音轨与 SPA', () => {
  it('解析 json3 并过滤事件控制项、音乐符号和纯空白', () => {
    expect(parseYouTubeJson3({ events: [
      { tStartMs: 3300, segs: [{ utf8: '下一句' }] },
      { tStartMs: 1000, dDurationMs: 1300, segs: [{ utf8: 'Hi' }, { utf8: '\n there' }] },
      { tStartMs: 2000, segs: [{ utf8: '♪\n♫' }] },
      { tStartMs: 2200, segs: [{ utf8: '\n ' }] },
      { tStartMs: 2300, id: 1, wpWinPosId: 0 },
    ] })).toEqual([
      { start_time: 1, end_time: 2.3, text: 'Hi there' },
      { start_time: 3.3, end_time: 5.3, text: '下一句' },
    ]);
  });

  it('优先中英文人工字幕，回退自动字幕', () => {
    const automatic = { baseUrl: 'https://www.youtube.com/api/timedtext?v=one', languageCode: 'zh', kind: 'asr' };
    const manual = { baseUrl: 'https://www.youtube.com/api/timedtext?v=two', languageCode: 'en' };
    expect(selectYouTubeCaptionTrack({ captions: { playerCaptionsTracklistRenderer: { captionTracks: [automatic, manual] } } }))
      .toMatchObject(manual);
    expect(selectYouTubeCaptionTrack([automatic])).toMatchObject(automatic);
  });

  it('从可直连 MP4 音轨提取码率和字节区间', () => {
    expect(extractYouTubeDashAudio({ streamingData: { adaptiveFormats: [
      { mimeType: 'audio/mp4', bitrate: 10, signatureCipher: 's=...' },
      { mimeType: 'audio/webm', bitrate: 100, url: 'https://cdn.googlevideo.com/webm' },
      { mimeType: 'audio/mp4; codecs="mp4a.40.2"', bitrate: 200, url: 'https://cdn.googlevideo.com/mp4',
        initRange: { start: '0', end: '900' }, indexRange: { start: '901', end: '2000' } },
      { mimeType: 'video/mp4', bitrate: 100, url: 'https://cdn.googlevideo.com/video' },
    ] } })).toMatchObject({
      url: 'https://cdn.googlevideo.com/mp4', bandwidth: 200, mimeType: 'audio/mp4',
      codecs: 'mp4a.40.2', initRange: '0-900', indexRange: '901-2000',
    });
  });

  it('在播放器和 watch HTML 中都按 videoId 拦住旧首屏响应', () => {
    const stale = { videoDetails: { videoId: 'zzzzzzzzzzz', title: 'Previous' } };
    const current = { videoDetails: { videoId: YOUTUBE_ID, title: 'JSON with } and " chars' } };
    expect(selectCurrentYouTubePlayerResponse(YOUTUBE_ID, current, stale)).toBe(current);
    expect(selectCurrentYouTubePlayerResponse(YOUTUBE_ID, stale, stale)).toBeNull();
    const html = `<script>var ytInitialPlayerResponse = ${JSON.stringify(stale)};</script>` +
      `<script>window["ytInitialPlayerResponse"] = ${JSON.stringify(current)};</script>`;
    expect(extractYouTubePlayerResponse(html, YOUTUBE_ID)).toEqual(current);
  });

  it('同源补拉当前视频，并在切集后跳过悬而未决的旧字幕', async () => {
    const otherId = 'lmnopqrstuv';
    const timedTextUrl = `https://www.youtube.com/api/timedtext?v=${YOUTUBE_ID}`;
    const response = {
      videoDetails: { videoId: YOUTUBE_ID, title: '视频 A' },
      captions: { playerCaptionsTracklistRenderer: { captionTracks: [
        { baseUrl: timedTextUrl, languageCode: 'zh', kind: 'asr' },
      ] } },
    };
    window.history.replaceState(null, '', `/watch?v=${YOUTUBE_ID}`);
    document.body.innerHTML = '<div id="movie_player"></div>';
    Object.assign(document.getElementById('movie_player')!, {
      getPlayerResponse: () => ({ videoDetails: { videoId: otherId, title: '视频 B' } }),
    });
    const timedText = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      events: [{ tStartMs: 1000, segs: [{ utf8: '视频 A 字幕' }] }],
    })));
    const fetcher = vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
      const url = new URL(String(input));
      if (url.pathname === '/watch') return new Response(`var ytInitialPlayerResponse = ${JSON.stringify(response)};`);
      return timedText();
    });
    try {
      const collector = createYouTubeCollector();
      expect(await collector.collect()).toMatchObject({
        descriptor: { external_id: YOUTUBE_ID }, transcript_source: 'platform_ai_subtitle',
        segments: [{ start_time: 1, end_time: 3, text: '视频 A 字幕' }],
      });
      expect(fetcher).toHaveBeenCalledWith(`${timedTextUrl}&fmt=json3`, expect.any(Object));

      let finish: (response: Response) => void = () => {};
      timedText.mockReturnValue(new Promise<Response>(resolve => { finish = resolve; }));
      const beforeSwitch = createYouTubeCollector();
      const pending = beforeSwitch.collect();
      await vi.waitFor(() => expect(timedText).toHaveBeenCalledTimes(2));
      window.history.pushState(null, '', `/watch?v=${otherId}`);
      expect(beforeSwitch.read()?.segments).toEqual([]);
      finish(new Response(JSON.stringify({ events: [{ tStartMs: 0, segs: [{ utf8: '过时字幕' }] }] })));
      await pending;
      expect(beforeSwitch.read()).toMatchObject({ descriptor: { external_id: otherId }, segments: [] });
    } finally {
      window.history.replaceState(null, '', `/watch?v=${YOUTUBE_ID}`);
      document.body.replaceChildren();
      fetcher.mockRestore();
    }
  });
});

describe('视频 URL 与字幕窗口', () => {
  it('为 B 站分 P、番剧和 YouTube 视频生成共享描述符', () => {
    expect(parseBilibiliVideoUrl(`${BILI_URL}?p=3`)).toMatchObject({
      platform: 'bilibili', external_id: BILI_ID, part: 3, video_key: `bilibili:${BILI_ID}:p3`,
    });
    expect(parseBilibiliVideoUrl(`${BILI_URL}?p=0`)?.part).toBe(1);
    expect(parseBilibiliVideoUrl('https://www.bilibili.com/bangumi/play/ep123')?.video_key).toBe('bilibili:ep123:p1');
    expect(parseYouTubeVideoUrl(`${YOUTUBE_URL}&list=PL1`)).toMatchObject({
      platform: 'youtube', external_id: YOUTUBE_ID, part: 1, video_key: `youtube:${YOUTUBE_ID}`,
    });
    expect(parseYouTubeVideoUrl(`https://www.youtube.com/shorts/${YOUTUBE_ID}`)?.video_key).toBe(`youtube:${YOUTUBE_ID}`);
    expect(parseYouTubeVideoUrl(`https://youtube.com.invalid/watch?v=${YOUTUBE_ID}`)).toBeNull();
    expect(parseBilibiliVideoUrl('https://www.bilibili.com/')).toBeNull();
  });

  it('保留与 [t-45, t+30] 相交的字幕，清洗并合并重叠重复句', () => {
    const segments = [
      { start_time: 131, end_time: 140, text: '后窗之外' },
      { start_time: 54, end_time: 55, text: '左边缘' },
      { start_time: 68, end_time: 73, text: '  同一条\n字幕 ' },
      { start_time: 70, end_time: 80, text: '同一条 字幕' },
      { start_time: 54, end_time: 54.9, text: '前窗之外' },
      { start_time: 130, end_time: 133, text: '右边缘' },
      { start_time: 88, end_time: 91, text: '\n' },
    ];
    expect(sliceTranscriptWindow(segments, 100)).toEqual([
      { start_time: 54, end_time: 55, text: '左边缘' },
      { start_time: 68, end_time: 80, text: '同一条 字幕' },
      { start_time: 130, end_time: 133, text: '右边缘' },
    ]);
    expect(sliceTranscriptWindow(segments, 100, 5, 5)).toEqual([]);
  });

  it('保留最近 80 条超长字幕并按字符截断至 1000 字', () => {
    const segments = Array.from({ length: 100 }, (_, index) => ({
      start_time: 55 + index * 0.75, end_time: 55.25 + index * 0.75,
      text: index === 60 ? '课'.repeat(1100) : `句 ${index}`,
    }));
    const window = sliceTranscriptWindow(segments, 100);
    expect(window).toHaveLength(80);
    expect(window[0]?.start_time).toBeGreaterThan(55);
    expect(window.find(segment => segment.start_time === 100)?.text).toBe('课'.repeat(1000));
  });
});

it('通过内容脚本消息交付视觉双帧、CORS 裁剪、跳播和按钮事件', async () => {
  vi.useFakeTimers();
  window.history.replaceState(null, '', `/watch?v=${YOUTUBE_ID}`);
  document.body.innerHTML = '<div id="movie_player"><video></video><div class="ytp-right-controls"></div></div>';
  const video = document.querySelector('video')!;
  Object.defineProperties(video, {
    readyState: { value: 4 }, videoWidth: { value: 1920 }, videoHeight: { value: 1080 },
    duration: { value: 120 }, paused: { value: false, configurable: true },
  });
  vi.spyOn(video, 'getBoundingClientRect').mockReturnValue(new DOMRect(10, 20, 600, 300));
  const play = vi.spyOn(video, 'play').mockResolvedValue();
  const drawImage = vi.fn();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage } as unknown as CanvasRenderingContext2D);
  const encode = vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/jpeg;base64,YQ==');

  const descriptor = { ...parseYouTubeVideoUrl(YOUTUBE_URL)!, title: '视频 A', has_native_subtitle: true };
  const media = {
    descriptor, transcript_source: 'platform_cc' as const, segments: [{ start_time: 1, end_time: 3, text: '字幕' }],
    dash_audio: { url: 'https://cdn.googlevideo.com/audio', backupUrls: ['http://localhost/audio'] },
  };
  const read = () => media;
  vi.spyOn(window, 'postMessage').mockImplementation(data => {
    void Promise.resolve().then(() => window.dispatchEvent(new MessageEvent('message', {
      source: window, origin: location.origin, data,
    })));
  });
  const relayListener = vi.spyOn(window, 'addEventListener');
  installPageMediaCollector({ read, collect: async () => read() });
  const relay = relayListener.mock.calls.at(-1)?.[1];
  relayListener.mockRestore();

  const addListener = vi.fn();
  const sendMessage = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal('chrome', { runtime: { onMessage: { addListener, removeListener: vi.fn() }, sendMessage } });
  const onCleanup: Array<() => void> = [];
  const ctx = {
    addEventListener(target: EventTarget, type: string, handler: EventListener, options?: AddEventListenerOptions) {
      target.addEventListener(type, handler, options);
      onCleanup.push(() => target.removeEventListener(type, handler, options));
    },
    setInterval(callback: () => void, delay: number) {
      const timer = window.setInterval(callback, delay);
      onCleanup.push(() => window.clearInterval(timer));
    },
    onInvalidated: (callback: () => void) => onCleanup.push(callback),
  } as unknown as NonNullable<Parameters<typeof videoBridge.main>[0]>;

  try {
    await videoBridge.main(ctx);
    const onMessage = addListener.mock.calls[0]?.[0];
    function send<Type extends BridgeMessage['type']>(message: Extract<BridgeMessage, { type: Type }>): Promise<MessageResponses[Type]> {
      return new Promise(resolve => onMessage(message, {}, resolve));
    }
    expect(await send({ type: UNIMIND_GET_ACTIVE_VIDEO })).toMatchObject({ video_key: descriptor.video_key });
    expect(sendMessage).toHaveBeenCalledWith({ type: UNIMIND_VIDEO_STATE_CHANGED, payload: expect.objectContaining({ title: '视频 A' }) });

    const controls = document.querySelector('.ytp-right-controls')!;
    const companionButton = controls.firstElementChild?.shadowRoot?.querySelector('button');
    expect(companionButton?.textContent).toBe('小宇伴学');
    expect(companionButton?.title).toBe('打开小宇伴学');
    expect(companionButton?.querySelector('[aria-hidden="true"]')).toBeTruthy();
    companionButton?.click();
    expect(sendMessage).toHaveBeenCalledWith({ type: UNIMIND_OPEN_SIDEPANEL });

    video.currentTime = 10;
    await vi.advanceTimersByTimeAsync(2000);
    video.currentTime = 12;
    const direct = await send({ type: UNIMIND_COLLECT_PAGE_SNAPSHOT });
    expect(direct).toMatchObject({
      video_seconds: 12, segments: media.segments,
      dash_audio: { url: 'https://cdn.googlevideo.com/audio', backupUrls: [] },
      direct_visual: { current: { video_seconds: 12 }, previous: { video_seconds: 10 } },
    });
    expect(drawImage).toHaveBeenCalledWith(video, 0, 0, 1280, 720);

    video.currentTime = 14;
    encode.mockImplementationOnce(() => { throw new DOMException('Tainted canvas', 'SecurityError'); });
    expect(await send({ type: UNIMIND_COLLECT_PAGE_SNAPSHOT })).toMatchObject({
      direct_visual: null, previous_frame: { video_seconds: 12 },
      cors_fallback_rect: { x: 10, y: 20, width: 600, height: 300 },
    });

    Object.defineProperty(video, 'paused', { value: true });
    expect(await send({ type: UNIMIND_SEEK_VIDEO, payload: { seconds: 6.5 } })).toEqual({ ok: true, currentTime: 6.5 });
    expect(play).toHaveBeenCalledTimes(1);
    video.currentTime = 14;
    expect((await send({ type: UNIMIND_COLLECT_PAGE_SNAPSHOT }))?.direct_visual?.previous).toBeUndefined();

    window.history.pushState(null, '', '/watch?v=lmnopqrstuv');
    document.dispatchEvent(new Event('yt-navigate-finish'));
    expect(await send({ type: UNIMIND_GET_ACTIVE_VIDEO })).toMatchObject({ video_key: 'youtube:lmnopqrstuv' });
    expect(await send({ type: UNIMIND_COLLECT_PAGE_SNAPSHOT })).toMatchObject({
      segments: [], transcript_source: 'none', descriptor: { video_key: 'youtube:lmnopqrstuv' },
    });
  } finally {
    for (const cleanup of onCleanup) cleanup();
    if (relay) window.removeEventListener('message', relay);
    document.body.replaceChildren();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  }
});

it('在标题和播放器控件之间迁移伴学按钮，并在视频页退出或卸载时清理', async () => {
  vi.useFakeTimers();
  document.body.innerHTML = '<ytd-watch-metadata><h1>课程标题</h1></ytd-watch-metadata>';
  let isVideoPage = true;
  const openSidePanel = vi.fn();
  const outerClick = vi.fn();
  document.body.addEventListener('click', outerClick);
  const stop = observePlayerUi('youtube', () => isVideoPage, openSidePanel);
  const title = document.querySelector('h1')!;
  const host = title.nextElementSibling!;
  const button = host.shadowRoot!.querySelector('button')!;
  try {
    expect(button.textContent).toBe('小宇伴学');
    button.click();
    expect(openSidePanel).toHaveBeenCalledTimes(1);
    expect(outerClick).not.toHaveBeenCalled();

    const player = document.createElement('div');
    player.id = 'movie_player';
    player.innerHTML = '<video></video><div class="ytp-right-controls"></div>';
    document.body.append(player);
    await vi.advanceTimersByTimeAsync(20);
    expect(host.parentElement).toBe(player.querySelector('.ytp-right-controls'));
    expect(document.querySelector('h1')?.nextElementSibling).toBeNull();

    isVideoPage = false;
    document.dispatchEvent(new Event('yt-navigate-finish'));
    await vi.advanceTimersByTimeAsync(20);
    expect(host.isConnected).toBe(false);

    isVideoPage = true;
    document.dispatchEvent(new Event('yt-navigate-finish'));
    await vi.advanceTimersByTimeAsync(20);
    expect(host.isConnected).toBe(true);
    stop();
    expect(host.isConnected).toBe(false);
    document.dispatchEvent(new Event('yt-navigate-finish'));
    await vi.advanceTimersByTimeAsync(20);
    expect(host.isConnected).toBe(false);
  } finally {
    stop();
    document.body.removeEventListener('click', outerClick);
    document.body.replaceChildren();
    vi.useRealTimers();
  }
});
