import type { PageMediaCollector, PageMediaData } from '../transcriptWindow';
import { installPageMediaCollector } from '../transcriptWindow';
import {
  extractBilibiliDashAudio, parseBilibiliSubtitles, record, resolveBilibiliPageState,
  selectBilibiliSubtitle, signWbiParams,
} from './index';
import type { BilibiliPageState } from './index';

interface BilibiliWindow extends Window {
  __INITIAL_STATE__?: unknown;
  __playinfo__?: unknown;
}

interface RequestIdentity {
  url: URL;
  videoKey: string | undefined;
  route: string;
}

/** Observe responses without changing the site's response objects, promises or exceptions. */
export function installBilibiliNetworkObserver(
  onResponse: (body: unknown, request: RequestIdentity) => void,
  currentVideoKey: () => string | undefined,
): () => void {
  const nativeFetch = window.fetch;
  const nativeOpen = XMLHttpRequest.prototype.open;
  const nativeSend = XMLHttpRequest.prototype.send;
  const requests = new WeakMap<XMLHttpRequest, RequestIdentity>();
  const listeners = new WeakMap<XMLHttpRequest, EventListener>();
  const identify = (input: unknown): RequestIdentity | undefined => {
    try {
      const raw = input instanceof Request ? input.url : String(input);
      const url = new URL(raw, location.href);
      if (!/(^|\.)bilibili\.com$/i.test(url.hostname)) return undefined;
      if (!/^\/(?:x\/player\/(?:wbi\/)?v2|x\/player\/(?:wbi\/)?playurl|pgc\/player\/web\/(?:v2\/)?playurl)$/.test(url.pathname)) return undefined;
      return { url, videoKey: currentVideoKey(), route: location.href };
    } catch { return undefined; }
  };
  const safelyObserve = (body: unknown, request: RequestIdentity) => {
    try { onResponse(body, request); } catch { /* Page playback always retains priority. */ }
  };
  const wrappedFetch: typeof fetch = function (this: Window, ...args: Parameters<typeof fetch>) {
    const response = Reflect.apply(nativeFetch, this, args) as ReturnType<typeof fetch>;
    const request = identify(args[0]);
    if (request) {
      void response.then(result => {
        try {
          void result.clone().json().then(body => safelyObserve(body, request)).catch(() => undefined);
        } catch { /* Opaque or consumed responses are simply unavailable. */ }
      }, () => undefined);
    }
    return response;
  };
  const wrappedOpen: typeof nativeOpen = function (
    this: XMLHttpRequest, method: string, url: string | URL, ...options: unknown[]
  ) {
    const result = Reflect.apply(nativeOpen, this, [method, url, ...options]);
    const oldListener = listeners.get(this);
    if (oldListener) this.removeEventListener('load', oldListener);
    listeners.delete(this);
    requests.delete(this);
    const request = identify(url);
    if (request) requests.set(this, request);
    return result;
  };
  const wrappedSend: typeof nativeSend = function (this: XMLHttpRequest, ...args: Parameters<typeof nativeSend>) {
    const request = requests.get(this);
    if (request && !listeners.has(this)) {
      const listener: EventListener = () => {
        try {
          const body = this.responseType === 'json' ? this.response : JSON.parse(this.responseText);
          safelyObserve(body, request);
        } catch { /* Non-JSON responses cannot provide subtitles. */ }
      };
      listeners.set(this, listener);
      this.addEventListener('load', listener);
    }
    return Reflect.apply(nativeSend, this, args);
  };
  window.fetch = wrappedFetch;
  XMLHttpRequest.prototype.open = wrappedOpen;
  XMLHttpRequest.prototype.send = wrappedSend;
  return () => {
    if (window.fetch === wrappedFetch) window.fetch = nativeFetch;
    if (XMLHttpRequest.prototype.open === wrappedOpen) XMLHttpRequest.prototype.open = nativeOpen;
    if (XMLHttpRequest.prototype.send === wrappedSend) XMLHttpRequest.prototype.send = nativeSend;
  };
}

export function startBilibiliCollector(): () => void {
  const pageWindow = window as BilibiliWindow;
  const originalFetch = window.fetch.bind(window);
  let data: PageMediaData | null = null;
  let identity = '';
  let generation = 0;
  let latestPlayInfo: unknown;
  let activePullIdentity = '';
  let inflight: Promise<PageMediaData | null> | null = null;
  let selectedSubtitleUrl = '';
  let subtitleLoading: Promise<void> | null = null;
  let subtitleAttempt = 0;
  let wbiKeys: { img: string; sub: string } | undefined;
  let observedState: BilibiliPageState | null = null;
  let publish = () => {};

  const documentState = () => resolveBilibiliPageState(location.href, pageWindow.__INITIAL_STATE__);
  const pageState = () => {
    const state = documentState();
    if (observedState?.descriptor.video_key !== state?.descriptor.video_key) observedState = null;
    if (!state || state.cid || !observedState) return state;
    return {
      ...observedState,
      descriptor: { ...observedState.descriptor, ...state.descriptor },
    };
  };
  const refresh = (): PageMediaData | null => {
    const state = pageState();
    const nextIdentity = state ? `${state.descriptor.video_key}:${state.cid ?? ''}` : '';
    if (identity !== nextIdentity) {
      identity = nextIdentity;
      generation += 1;
      activePullIdentity = '';
      inflight = null;
      selectedSubtitleUrl = '';
      subtitleLoading = null;
      subtitleAttempt += 1;
      data = state ? { descriptor: state.descriptor, transcript_source: 'none', segments: [], dash_audio: null } : null;
    }
    if (!state || !data) return null;
    data.descriptor = {
      ...data.descriptor, ...state.descriptor,
      title: state.descriptor.title || document.querySelector('h1.video-title, .video-info h1, #viewbox_report h1')?.textContent?.trim() || document.title,
    };
    data.descriptor.has_native_subtitle = Boolean(selectedSubtitleUrl);
    const playInfo = pageWindow.__playinfo__;
    // Remember consumed objects across navigation so stale globals cannot be relabelled.
    if (playInfo && playInfo !== latestPlayInfo && state.cid && documentState()?.cid === state.cid) {
      latestPlayInfo = playInfo;
      data.dash_audio = extractBilibiliDashAudio(playInfo);
    }
    return data;
  };
  const fetchJson = async (url: string): Promise<unknown> => {
    const target = new URL(url, location.href);
    const credentials = target.hostname === 'api.bilibili.com' || target.origin === location.origin ? 'include' : 'omit';
    const response = await originalFetch(url, { credentials, signal: AbortSignal.timeout(6500) });
    if (!response.ok) throw new Error(`Bilibili HTTP ${response.status}`);
    return response.json();
  };
  const ingestSubtitles = async (body: unknown, expectedGeneration: number): Promise<void> => {
    const track = selectBilibiliSubtitle(body);
    if (!data || expectedGeneration !== generation) return;
    if (!track) {
      subtitleAttempt += 1;
      selectedSubtitleUrl = '';
      subtitleLoading = null;
      data.segments = [];
      data.transcript_source = 'none';
      data.descriptor.has_native_subtitle = false;
      publish();
      return;
    }
    if (selectedSubtitleUrl === track.subtitle_url) {
      await subtitleLoading;
      return;
    }
    const attempt = ++subtitleAttempt;
    selectedSubtitleUrl = track.subtitle_url;
    data.segments = [];
    data.transcript_source = 'none';
    data.descriptor.has_native_subtitle = true;
    publish();
    subtitleLoading = (async () => {
      try {
        const result = await fetchJson(track.subtitle_url);
        refresh();
        if (!data || expectedGeneration !== generation || attempt !== subtitleAttempt) return;
        data.segments = parseBilibiliSubtitles(result);
        data.transcript_source = data.segments.length ? (track.isAI ? 'platform_ai_subtitle' : 'platform_cc') : 'none';
        publish();
      } catch {
        if (attempt === subtitleAttempt && expectedGeneration === generation) selectedSubtitleUrl = '';
      }
    })();
    await subtitleLoading;
  };
  const onResponse = (body: unknown, request: RequestIdentity) => {
    const isSubtitleResponse = /\/v2$/.test(request.url.pathname);
    const envelope = record(body);
    const responseData = record(envelope.data);
    if (isSubtitleResponse && (envelope.code !== 0 || !Array.isArray(record(responseData.subtitle).subtitles))) return;
    let state = pageState();
    if (!state || request.videoKey !== state.descriptor.video_key) return;
    const params = request.url.searchParams;
    const cid = params.get('cid');
    const aid = params.get('aid') ?? params.get('avid');
    const bvid = params.get('bvid');
    const requestedPart = params.get('p') ?? params.get('page');
    if (requestedPart && Number(requestedPart) !== state.descriptor.part) return;
    if (Number.isFinite(Number(responseData.cid)) && responseData.cid != null && Number(responseData.cid) !== Number(cid)) return;
    if (!state.cid && isSubtitleResponse && cid && Number.isSafeInteger(Number(cid)) && Number(cid) > 0) {
      const route = resolveBilibiliPageState(request.route, undefined)?.descriptor;
      const matchesRoute = state.descriptor.external_id.startsWith('BV')
        ? bvid === state.descriptor.external_id
        : state.descriptor.external_id.startsWith('av') && Number(aid) === Number(state.descriptor.external_id.slice(2));
      if (!matchesRoute || route?.video_key !== state.descriptor.video_key) return;
      // Only current-route subtitle metadata establishes a missing identity. Playurl
      // prefetches cannot establish a cid, and explicit part metadata must agree.
      observedState = {
        descriptor: state.descriptor, cid: Number(cid),
        aid: aid && Number.isSafeInteger(Number(aid)) && Number(aid) > 0 ? Number(aid) : undefined,
        bvid: bvid ?? undefined,
      };
      state = pageState();
    }
    refresh();
    if (!data || !state) return;
    // Match current part as well as video, including responses arriving after a SPA switch.
    if (!state.cid || !cid || Number(cid) !== state.cid) return;
    if (bvid && state.bvid && bvid !== state.bvid) return;
    if (aid && state.aid && Number(aid) !== state.aid) return;
    const audio = extractBilibiliDashAudio(body);
    if (audio) data.dash_audio = audio;
    if (isSubtitleResponse) void ingestSubtitles(body, generation);
    publish();
  };
  const collector: PageMediaCollector = {
    read: refresh,
    async collect() {
      refresh();
      let state = pageState();
      if (!data || !state) return null;
      if (data.segments.length) return data;
      if (subtitleLoading) {
        await subtitleLoading;
        refresh();
        if (data?.segments.length) return data;
        state = pageState();
        if (!data || !state) return null;
      }
      if (inflight) return inflight;
      if (!state.cid || (!state.aid && !state.bvid) || activePullIdentity === identity) return data;
      const expectedGeneration = generation;
      const expectedIdentity = identity;
      activePullIdentity = identity;
      const task = (async () => {
        try {
          if (!wbiKeys) {
            const nav = record(await fetchJson('https://api.bilibili.com/x/web-interface/nav'));
            const keys = record(record(nav.data).wbi_img);
            if (typeof keys.img_url !== 'string' || typeof keys.sub_url !== 'string') return refresh();
            wbiKeys = { img: keys.img_url, sub: keys.sub_url };
          }
          refresh();
          if (generation !== expectedGeneration) return data;
          const params: Record<string, string | number> = { cid: state.cid! };
          if (state.aid) params.aid = state.aid;
          if (state.bvid) params.bvid = state.bvid;
          const signed = signWbiParams(params, wbiKeys.img, wbiKeys.sub);
          const query = Object.entries(signed).map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`).join('&');
          const result = await fetchJson(`https://api.bilibili.com/x/player/wbi/v2?${query}`);
          refresh();
          const envelope = record(result);
          if (envelope.code === 0 && Array.isArray(record(record(envelope.data).subtitle).subtitles)
            && generation === expectedGeneration && identity === expectedIdentity) await ingestSubtitles(result, expectedGeneration);
        } catch { /* Subtitle absence and network failures preserve visual-only collection. */ }
        return refresh();
      })();
      inflight = task;
      try { return await task; }
      finally { if (inflight === task) inflight = null; }
    },
  };
  const stopObserving = installBilibiliNetworkObserver(onResponse, () => pageState()?.descriptor.video_key);
  publish = installPageMediaCollector(collector);
  let lastPublished = '';
  const update = () => {
    const current = refresh();
    const signature = `${identity}:${current?.descriptor.title}:${current?.descriptor.duration}:${current?.dash_audio?.url}`;
    if (signature !== lastPublished) {
      lastPublished = signature;
      publish();
    }
  };
  const timer = window.setInterval(update, 1000);
  window.addEventListener('popstate', update);
  window.addEventListener('hashchange', update);
  document.addEventListener('DOMContentLoaded', update);
  document.addEventListener('loadedmetadata', update, true);
  update();
  return () => {
    clearInterval(timer);
    stopObserving();
    window.removeEventListener('popstate', update);
    window.removeEventListener('hashchange', update);
    document.removeEventListener('DOMContentLoaded', update);
    document.removeEventListener('loadedmetadata', update, true);
  };
}
