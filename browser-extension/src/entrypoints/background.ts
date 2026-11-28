import { defineBackground } from 'wxt/utils/define-background';
import { parseBilibiliVideoUrl } from '../collectors/bilibili';
import { installMediaHeaders, transcribeDashAudio, uploadAudioSnippet } from '../collectors/dash-range';
import { clearVisual, collectVisual } from '../collectors/visual';
import { extractWorkbenchArticle } from '../collectors/workbenchArticle';
import { fullWorkbenchTranscript } from '../collectors/workbenchVideo';
import { parseYouTubeVideoUrl } from '../collectors/youtube';
import { handleAuthCookieChange, syncCookieToken } from '../lib/auth';
import { readSession } from '../lib/storage';
import {
  sendTabMessage,
  UNIMIND_AUTH_SYNC,
  UNIMIND_CAPTURE_CONTEXT_FOR_ASK,
  UNIMIND_CAPTURE_SOURCE_FOR_WORKBENCH,
  UNIMIND_COLLECT_PAGE_SNAPSHOT,
  UNIMIND_COLLECT_WORKBENCH_VIDEO,
  UNIMIND_GET_ACTIVE_VIDEO,
  UNIMIND_OPEN_SIDEPANEL,
  UNIMIND_TOGGLE_TAB_AUDIO,
  type BridgeMessage,
} from '../shared/bridge';
import type {
  CaptureContextResult, PageCollectSnapshot, TranscriptSegmentItem, TranscriptSource, WorkbenchCaptureResult,
} from '../shared/types';
import { collectTabAudio, installOffscreenAudioBridge, setTabAudioEnabled, stopTabAudio } from './offscreen/client';

// The side panel stops waiting for the entire snapshot after four seconds.
const ASK_CAPTURE_BUDGET_MS = 3700;
const emptyTranscript = { source: 'none' as const, segments: [] };

interface TranscriptResult {
  source: TranscriptSource;
  segments: TranscriptSegmentItem[];
}
const bufferedTranscripts = new Map<number, {
  videoKey: string; auth: string; segments: TranscriptSegmentItem[];
}>();

async function activeTabId() {
  return (await chrome.tabs.query({ active: true, lastFocusedWindow: true }))[0]?.id;
}

async function collectTranscript(
  tabId: number,
  snapshot: PageCollectSnapshot,
  deadline: number,
  warnings: string[],
): Promise<TranscriptResult> {
  if (snapshot.segments.length) {
    return { source: snapshot.transcript_source, segments: snapshot.segments };
  }

  const session = await readSession().catch(() => null);
  if (!session?.token || Date.now() >= deadline) return emptyTranscript;
  const { serverOrigin, token } = session;
  const { descriptor, dash_audio: track, video_seconds: targetSeconds } = snapshot;
  const auth = `${serverOrigin}:${token}`;
  const previous = bufferedTranscripts.get(tabId);
  const buffer = previous?.videoKey === descriptor.video_key && previous.auth === auth
    ? previous : { videoKey: descriptor.video_key, auth, segments: [] };
  bufferedTranscripts.set(tabId, buffer);
  function remember(source: TranscriptSource, segments: TranscriptSegmentItem[]): TranscriptResult {
    if (bufferedTranscripts.get(tabId) === buffer) {
      buffer.segments = fullWorkbenchTranscript([...buffer.segments, ...segments]);
    }
    return { source, segments };
  }

  if (track) {
    try {
      await installMediaHeaders().catch(() => { warnings.push('暂时无法设置 DASH 音频请求头。'); });
      if (Date.now() >= deadline) return emptyTranscript;
      const result = await transcribeDashAudio({ descriptor, track, targetSeconds, serverOrigin, token });
      warnings.push(...result.warnings);
      if (result.segments.length) return remember('dash_range_asr', result.segments);
    } catch {
      warnings.push('DASH 音频切片暂时无法转写。');
    }
  }
  if (Date.now() >= deadline) return emptyTranscript;

  try {
    const clip = await collectTabAudio(tabId, snapshot);
    if (!clip || Date.now() >= deadline) return emptyTranscript;
    const result = await uploadAudioSnippet({ descriptor, ...clip, serverOrigin, token });
    warnings.push(...result.warnings);
    if (result.segments.length) return remember('tab_capture_asr', result.segments);
  } catch {
    warnings.push('实时听课录音暂时无法转写。');
  }
  return emptyTranscript;
}

async function captureWorkbenchSource(windowId?: number): Promise<WorkbenchCaptureResult> {
  try {
    const [tab] = await chrome.tabs.query({ active: true, ...(windowId === undefined ? { lastFocusedWindow: true } : { windowId }) });
    if (tab?.id === undefined || !tab.url || !/^https?:\/\//i.test(tab.url)) {
      return { error: '请打开一个 HTTP 或 HTTPS 网页再收入工作台。' };
    }
    const url = new URL(tab.url);
    if (url.username || url.password) return { error: '当前网页链接中包含账号或密码，无法收入工作台。' };
    url.hash = '';
    const videoRoute = parseBilibiliVideoUrl(url) ?? parseYouTubeVideoUrl(url);
    if (videoRoute) {
      const snapshot = await sendTabMessage(tab.id, UNIMIND_COLLECT_WORKBENCH_VIDEO).catch(() => null);
      if (snapshot?.descriptor.video_key !== videoRoute.video_key) {
        return { error: '暂时无法读取当前视频，请刷新视频页面后再试。' };
      }
      const { descriptor } = snapshot;
      let segments = snapshot.segments;
      if (!segments.length) {
        const buffer = bufferedTranscripts.get(tab.id);
        if (buffer?.videoKey === descriptor.video_key && buffer.segments.length) {
          const session = await readSession();
          if (buffer.auth === `${session.serverOrigin}:${session.token}`) segments = buffer.segments;
        }
      }
      if (!segments.length) return { error: '当前视频暂无可用字幕或已转写的讲稿。' };
      return { source: {
        kind: 'external_video',
        platform: videoRoute.platform as 'bilibili' | 'youtube',
        external_id: descriptor.external_id, part: descriptor.part,
        title: Array.from(descriptor.title).slice(0, 240).join(''), url: url.href,
        duration_seconds: descriptor.duration ?? segments.reduce((end, segment) => Math.max(end, segment.end_time), 0),
        segments,
      } };
    }

    const [{ result: article } = {}] = await chrome.scripting.executeScript({
      target: { tabId: tab.id }, func: extractWorkbenchArticle, args: [120_000],
    });
    if (!article || article.pageUrl !== url.href) return { error: '当前网页已切换，请重新收入工作台。' };
    const { content } = article;
    const title = Array.from(article.title).slice(0, 240).join('');
    if (content) return { source: { kind: 'text', title, source_url: article.url, content } };
    if (article.url.startsWith('https://')) return { source: { kind: 'web_url', title, url: article.url } };
    return { error: '当前网页没有可读取的正文。' };
  } catch {
    return { error: '暂时无法读取当前页面，请在该标签页点击工具栏中的 UniMind 图标后再试。' };
  }
}

async function collectTranscriptForAsk(tabId: number, snapshot: PageCollectSnapshot, deadline: number) {
  const warnings: string[] = [];
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const result = await Promise.race([
      collectTranscript(tabId, snapshot, deadline, warnings),
      new Promise<TranscriptResult>(resolve => {
        timer = setTimeout(() => {
          warnings.push('音频转写仍在处理，已继续采集播放信息。');
          resolve(emptyTranscript);
        }, Math.max(0, deadline - Date.now()));
      }),
    ]);
    return { ...result, warnings: [...warnings] };
  } finally {
    clearTimeout(timer);
  }
}

async function captureContext(tabId?: number): Promise<CaptureContextResult> {
  const deadline = Date.now() + ASK_CAPTURE_BUDGET_MS;
  const noContext: CaptureContextResult = { ok: false, context: null, descriptor: null, warnings: [] };
  try {
    const id = tabId ?? await activeTabId();
    if (id === undefined) return noContext;
    const snapshot = await sendTabMessage(id, UNIMIND_COLLECT_PAGE_SNAPSHOT).catch(() => null);
    if (!snapshot) {
      const descriptor = await sendTabMessage(id, UNIMIND_GET_ACTIVE_VIDEO).catch(() => null);
      return { ...noContext, descriptor: descriptor ?? null };
    }

    const { descriptor, video_seconds } = snapshot;
    const [{ visual, warnings: visualWarnings }, transcript] = await Promise.all([
      collectVisual(id, snapshot, deadline - Date.now())
        .catch(() => ({ visual: undefined, warnings: ['暂时无法截取播放器画面。'] })),
      collectTranscriptForAsk(id, snapshot, deadline),
    ]);
    return {
      ok: true,
      descriptor,
      warnings: [...visualWarnings, ...transcript.warnings],
      context: {
        platform: descriptor.platform,
        external_id: descriptor.external_id,
        part: descriptor.part,
        url: descriptor.url,
        title: descriptor.title,
        video_seconds,
        transcript_source: transcript.source,
        segments: transcript.segments,
        ...(visual ? { visual } : {}),
        integration_hooks: {
          knowledge_tree_id: null,
          knowledge_node_id: null,
          memory_event_target: null,
        },
      },
    };
  } catch {
    return { ...noContext, warnings: ['暂时无法获取当前页面的播放信息。'] };
  }
}

async function toggleTabAudio(tabId: number | undefined, enabled: boolean) {
  try {
    const id = tabId ?? await activeTabId();
    if (id !== undefined) {
      const result = await setTabAudioEnabled(id, enabled);
      if (enabled && result.error?.includes('activeTab permission')) {
        return { enabled: false, error: '请先在视频标签页点击浏览器工具栏中的 UniMind 图标，再开启实时听课录音。' };
      }
      return result;
    }
  } catch {
    return { enabled: false, error: '暂时无法切换实时听课录音。' };
  }
  return { enabled: false, ...(enabled ? { error: '没有可录音的活动标签页。' } : {}) };
}

export default defineBackground(() => {
  const configurePanel = () => {
    // Migrate older installs. Chromium's automatic toggle skips the activeTab grant.
    void chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: false })
      .catch(error => console.warn('无法配置侧栏入口', error));
  };
  chrome.action.onClicked.addListener(tab => {
    void chrome.sidePanel.open({ windowId: tab.windowId }).catch(error => console.warn('无法打开侧栏', error));
  });
  chrome.runtime.onInstalled.addListener(configurePanel);
  chrome.runtime.onStartup.addListener(configurePanel);
  configurePanel();

  chrome.cookies.onChanged.addListener(change => {
    void handleAuthCookieChange(change).catch(() => undefined);
  });

  installOffscreenAudioBridge();
  const clearTab = (tabId: number) => {
    clearVisual(tabId);
    bufferedTranscripts.delete(tabId);
    void stopTabAudio(tabId).catch(() => undefined);
  };
  chrome.tabs.onRemoved.addListener(clearTab);
  chrome.tabs.onUpdated.addListener((tabId, change) => {
    if (change.status === 'loading') clearTab(tabId);
  });

  chrome.runtime.onMessage.addListener((message: BridgeMessage, sender, respond) => {
    if (message?.type === UNIMIND_OPEN_SIDEPANEL) {
      const tabId = sender.tab?.id;
      if (tabId === undefined) {
        respond({ ok: false });
        return;
      }
      // Open synchronously within the click's message handler to retain user activation.
      void chrome.sidePanel.open({ tabId }).then(() => respond({ ok: true }), () => respond({ ok: false }));
      return true;
    }
    // A tab's content script only publishes video state and requests opening the panel.
    if (sender.tab && !sender.url?.startsWith(chrome.runtime.getURL('/'))) return;
    if (message?.type === UNIMIND_AUTH_SYNC) {
      void syncCookieToken(message.payload?.serverOrigin)
        .then(token => respond({ token }), () => respond({ token: null }));
      return true;
    }
    if (message?.type === UNIMIND_CAPTURE_CONTEXT_FOR_ASK) {
      void captureContext(message.payload?.tabId).then(respond);
      return true;
    }
    if (message?.type === UNIMIND_CAPTURE_SOURCE_FOR_WORKBENCH) {
      void captureWorkbenchSource(message.payload?.windowId).then(respond);
      return true;
    }
    if (message?.type === UNIMIND_TOGGLE_TAB_AUDIO) {
      void toggleTabAudio(message.payload?.tabId, message.payload.enabled).then(respond);
      return true;
    }
  });
});
