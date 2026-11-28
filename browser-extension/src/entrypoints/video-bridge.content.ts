import { defineContentScript } from 'wxt/utils/define-content-script';
import { parseBilibiliVideoUrl } from '../collectors/bilibili';
import { findPlayerVideo, observePlayerUi, readPlayerTitle } from '../collectors/playerUi';
import {
  readPageMediaUpdate, requestPageMedia, sliceTranscriptWindow, type PageMediaData,
} from '../collectors/transcriptWindow';
import { parseYouTubeVideoUrl } from '../collectors/youtube';
import { fullWorkbenchTranscript, readPlayerSubtitles } from '../collectors/workbenchVideo';
import {
  sendRuntimeMessage, UNIMIND_COLLECT_PAGE_SNAPSHOT, UNIMIND_GET_ACTIVE_VIDEO,
  UNIMIND_COLLECT_WORKBENCH_VIDEO, UNIMIND_OPEN_SIDEPANEL, UNIMIND_SEEK_VIDEO, UNIMIND_VIDEO_STATE_CHANGED,
  type BridgeMessage, type MessageResponses,
} from '../shared/bridge';
import type {
  ActiveVideoDescriptor, DashAudioTrackMeta, PageCollectSnapshot, VideoRectInfo, VisualFrameSnapshot, WorkbenchVideoSnapshot,
} from '../shared/types';

const FRAME_INTERVAL_MS = 2000;
const FRAME_HISTORY_SECONDS = 12;
const MAX_BUFFERED_FRAMES = 8;
const MAX_IMAGE_EDGE = 1280;
const MAX_IMAGE_BYTES = 500 * 1024;
const PAGE_MEDIA_TIMEOUT_MS = 2000;
const JPEG_PREFIX = 'data:image/jpeg;base64,';

function readPosition(video: HTMLVideoElement | null): number {
  return video && Number.isFinite(video.currentTime) ? video.currentTime : 0;
}

function captureFrame(video: HTMLVideoElement, seconds: number): VisualFrameSnapshot | null {
  if (video.readyState < 2 || video.seeking || !video.videoWidth || !video.videoHeight) return null;
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d');
  if (!context) return null;
  let scale = Math.min(1, MAX_IMAGE_EDGE / Math.max(video.videoWidth, video.videoHeight));

  try {
    for (let resize = 0; resize < 3; resize++, scale *= 0.7) {
      canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
      canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      for (const quality of [0.84, 0.65, 0.45]) {
        const image = canvas.toDataURL('image/jpeg', quality);
        if (!image.startsWith(JPEG_PREFIX)) return null;
        const padding = image.endsWith('==') ? 2 : image.endsWith('=') ? 1 : 0;
        const bytes = (image.length - JPEG_PREFIX.length) * 3 / 4 - padding;
        if (bytes <= MAX_IMAGE_BYTES) return { video_seconds: seconds, image };
      }
    }
  } catch {
    // Tainted or unavailable video pixels can still be captured from the visible tab.
    return null;
  }
  return null;
}

function videoRect(video: HTMLVideoElement | null): VideoRectInfo | null {
  if (!video?.isConnected) return null;
  const { x, y, width, height } = video.getBoundingClientRect();
  if (width <= 0 || height <= 0) return null;
  return {
    x, y, width, height, devicePixelRatio: window.devicePixelRatio,
    viewportWidth: window.innerWidth, viewportHeight: window.innerHeight,
  };
}

function pageDashAudio(track: DashAudioTrackMeta | null | undefined, platform: 'bilibili' | 'youtube'): DashAudioTrackMeta | null {
  if (!track) return null;
  // The page relay carries public media URLs to the privileged background fetcher.
  const cdn = platform === 'youtube'
    ? /(?:^|\.)googlevideo\.com$/i : /(?:^|\.)(?:bilivideo\.(?:com|cn)|hdslb\.com|akamaized\.net)$/i;
  const backups = Array.isArray(track.backupUrls) ? track.backupUrls : [];
  const [url, ...backupUrls] = [track.url, ...backups].filter(value => {
    if (typeof value !== 'string') return false;
    try {
      const parsed = new URL(value);
      return (parsed.protocol === 'https:' || parsed.protocol === 'http:') && cdn.test(parsed.hostname);
    } catch {
      return false;
    }
  });
  return url ? { ...track, url, backupUrls } : null;
}

function seekVideo(
  video: HTMLVideoElement | null, seconds: number | undefined, clearFrames: () => void,
): MessageResponses[typeof UNIMIND_SEEK_VIDEO] {
  if (!video || typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds < 0) return { ok: false };
  try {
    video.currentTime = Number.isFinite(video.duration) ? Math.min(seconds, video.duration) : seconds;
    clearFrames();
  } catch {
    return { ok: false };
  }
  // A successful seek is still useful when the browser blocks autoplay.
  if (video.paused) void video.play().catch(() => undefined);
  return { ok: true, currentTime: video.currentTime };
}

export default defineContentScript({
  matches: ['*://*.bilibili.com/*', '*://*.youtube.com/*'],
  world: 'ISOLATED',
  runAt: 'document_start',
  main(ctx) {
    const platform = /(?:^|\.)bilibili\.com$/i.test(location.hostname) ? 'bilibili' : 'youtube';
    const parseUrl = platform === 'bilibili' ? parseBilibiliVideoUrl : parseYouTubeVideoUrl;
    let activeKey: string | null = null;
    let activeVideo: HTMLVideoElement | null = null;
    let activeSrc = '';
    let pageMedia: PageMediaData | null = null;
    let lastReported: string | undefined;
    let frames: VisualFrameSnapshot[] = [];
    let lastSnapshot: VisualFrameSnapshot | null = null;
    let lastVideoTime = 0;
    let navigationVersion = 0;
    let requestSequence = 0;
    const pendingMedia = new Map<string, (media: PageMediaData | null) => void>();

    function clearFrames() {
      frames = [];
      lastSnapshot = null;
      lastVideoTime = readPosition(activeVideo);
    }

    function syncActiveVideo(): ActiveVideoDescriptor | null {
      const route = parseUrl(location.href);
      const video = route ? findPlayerVideo(platform) : null;
      const videoKey = route?.video_key ?? null;
      const src = video?.currentSrc ?? '';
      const keyChanged = activeKey !== videoKey;
      if (keyChanged) {
        activeKey = videoKey;
        pageMedia = null;
        navigationVersion++;
        for (const finish of pendingMedia.values()) finish(null);
        if (videoKey) requestPageMedia(videoKey);
      }
      const resetFrames = keyChanged || video !== activeVideo || src !== activeSrc || readPosition(video) < lastVideoTime;
      activeVideo = video;
      activeSrc = src;
      if (resetFrames) clearFrames();
      lastVideoTime = readPosition(video);

      const metadata = pageMedia?.descriptor;
      const playerDuration = video?.duration;
      const duration = metadata?.duration ??
        (typeof playerDuration === 'number' && Number.isFinite(playerDuration) ? playerDuration : undefined);
      const descriptor = route && {
        ...route,
        title: metadata?.title || readPlayerTitle(platform) || route.external_id,
        duration,
        has_native_subtitle: metadata?.has_native_subtitle,
      };
      const report = JSON.stringify(descriptor && [
        descriptor.video_key, descriptor.title, descriptor.duration, descriptor.has_native_subtitle,
      ]);
      if (report !== lastReported) {
        lastReported = report;
        void sendRuntimeMessage(UNIMIND_VIDEO_STATE_CHANGED, descriptor).catch(() => undefined);
      }
      return descriptor;
    }

    function receivePageMedia(event: MessageEvent) {
      const update = readPageMediaUpdate(event);
      if (!update) return;
      syncActiveVideo();
      const media = update.payload?.descriptor.video_key === activeKey ? update.payload : null;
      if (media) {
        pageMedia = media;
        syncActiveVideo();
      }
      if (update.requestId) pendingMedia.get(update.requestId)?.(media);
    }

    function collectPageMedia(videoKey: string, timeoutMs = PAGE_MEDIA_TIMEOUT_MS): Promise<PageMediaData | null> {
      if (pageMedia?.segments.length) return Promise.resolve(pageMedia);
      const requestId = String(++requestSequence);
      return new Promise(resolve => {
        const finish = (media: PageMediaData | null) => {
          window.clearTimeout(timeout);
          pendingMedia.delete(requestId);
          resolve(media);
        };
        const timeout = window.setTimeout(() => finish(null), timeoutMs);
        pendingMedia.set(requestId, finish);
        requestPageMedia(videoKey, requestId);
      });
    }

    async function collectWorkbenchVideo(): Promise<WorkbenchVideoSnapshot | null> {
      const descriptor = syncActiveVideo();
      if (!descriptor) return null;
      const version = navigationVersion;
      // Platform collectors may need to fetch both the track list and subtitle body.
      const collected = await collectPageMedia(descriptor.video_key, 30_000);
      const latest = syncActiveVideo();
      if (latest?.video_key !== descriptor.video_key || navigationVersion !== version) return null;
      const subtitles = fullWorkbenchTranscript((collected ?? pageMedia)?.segments ?? []);
      return {
        descriptor: latest,
        segments: subtitles.length ? subtitles : fullWorkbenchTranscript(readPlayerSubtitles(activeVideo)),
      };
    }

    function sampleFrame() {
      syncActiveVideo();
      if (!activeVideo || activeVideo.paused || activeVideo.ended) return;
      const seconds = readPosition(activeVideo);
      frames = frames.filter(frame => seconds - frame.video_seconds <= FRAME_HISTORY_SECONDS);
      if (frames.at(-1)?.video_seconds === seconds) return;
      const frame = captureFrame(activeVideo, seconds);
      if (frame) frames = [...frames, frame].slice(-MAX_BUFFERED_FRAMES);
    }

    async function collectSnapshot(
      options?: { windowBeforeSec?: number; windowAfterSec?: number },
    ): Promise<PageCollectSnapshot | null> {
      const descriptor = syncActiveVideo();
      if (!descriptor) return null;
      const version = navigationVersion;
      const video = activeVideo;
      const seconds = readPosition(video);
      const paused = video?.paused ?? true;
      const mediaRequest = collectPageMedia(descriptor.video_key);
      const frame = video && captureFrame(video, seconds);
      const previous = [lastSnapshot, ...frames].reduce<VisualFrameSnapshot | undefined>((latest, candidate) => {
        if (!candidate) return latest;
        const gap = seconds - candidate.video_seconds;
        return gap >= 1 && gap <= FRAME_HISTORY_SECONDS && (!latest || candidate.video_seconds > latest.video_seconds)
          ? candidate : latest;
      }, undefined);
      if (frame) lastSnapshot = frame;

      const collected = await mediaRequest;
      const latest = syncActiveVideo();
      if (latest?.video_key !== descriptor.video_key || navigationVersion !== version) return null;
      const media = collected ?? pageMedia;
      const before = Number.isFinite(options?.windowBeforeSec) ? options?.windowBeforeSec : undefined;
      const after = Number.isFinite(options?.windowAfterSec) ? options?.windowAfterSec : undefined;
      return {
        descriptor: latest,
        video_seconds: seconds,
        paused,
        transcript_source: media?.transcript_source ?? 'none',
        segments: sliceTranscriptWindow(media?.segments ?? [], seconds, before, after),
        dash_audio: pageDashAudio(media?.dash_audio, platform),
        direct_visual: frame ? { current: frame, ...(previous && { previous }) } : null,
        cors_fallback_rect: frame ? null : videoRect(activeVideo),
        previous_frame: frame ? null : previous ?? null,
      };
    }

    const onMessage: Parameters<typeof chrome.runtime.onMessage.addListener>[0] =
      (message: BridgeMessage, _sender, respond) => {
        switch (message?.type) {
          case UNIMIND_GET_ACTIVE_VIDEO:
            respond(syncActiveVideo());
            return;
          case UNIMIND_SEEK_VIDEO:
            syncActiveVideo();
            respond(seekVideo(activeVideo, message.payload?.seconds, clearFrames));
            return;
          case UNIMIND_COLLECT_PAGE_SNAPSHOT:
            void collectSnapshot(message.payload).then(respond, () => respond(null));
            return true;
          case UNIMIND_COLLECT_WORKBENCH_VIDEO:
            void collectWorkbenchVideo().then(respond, () => respond(null));
            return true;
        }
      };

    ctx.addEventListener(window, 'message', receivePageMedia);
    ctx.addEventListener(window, 'popstate', syncActiveVideo);
    ctx.addEventListener(document, 'yt-navigate-finish', syncActiveVideo);
    ctx.addEventListener(document, 'loadedmetadata', syncActiveVideo, { capture: true });
    ctx.addEventListener(document, 'seeking', event => {
      if (event.target === activeVideo) clearFrames();
    }, { capture: true });
    ctx.setInterval(syncActiveVideo, 700);
    ctx.setInterval(sampleFrame, FRAME_INTERVAL_MS);
    chrome.runtime.onMessage.addListener(onMessage);

    const removePlayerUi = observePlayerUi(platform, () => Boolean(parseUrl(location.href)), () => {
      void sendRuntimeMessage(UNIMIND_OPEN_SIDEPANEL).catch(() => undefined);
    });
    ctx.onInvalidated(() => {
      chrome.runtime.onMessage.removeListener(onMessage);
      removePlayerUi();
      for (const finish of pendingMedia.values()) finish(null);
    });
    syncActiveVideo();
  },
});
