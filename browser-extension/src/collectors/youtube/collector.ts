import type { PageMediaCollector, PageMediaData } from '../transcriptWindow';
import {
  asYouTubeObject,
  extractYouTubeDashAudio,
  extractYouTubePlayerResponse,
  getYouTubeCaptionTracks,
  parseYouTubeJson3,
  parseYouTubeVideoUrl,
  selectCurrentYouTubePlayerResponse,
  selectYouTubeCaptionTrack,
} from './index';

interface YouTubeWindow extends Window {
  ytInitialPlayerResponse?: unknown;
}

interface YouTubePlayer extends HTMLElement {
  getPlayerResponse?: () => unknown;
}

export function createYouTubeCollector(): PageMediaCollector {
  let activeKey: string | null = null;
  let generation = 0;
  let cached: PageMediaData | null = null;
  let watchResponse: Record<string, unknown> | null = null;
  let watchRequested = false;
  let completedTrackUrl: string | null = null;
  let pending: { generation: number; promise: Promise<PageMediaData | null> } | null = null;

  function currentResponse(videoId: string): Record<string, unknown> | null {
    let playerResponse: unknown;
    try {
      playerResponse = (document.getElementById('movie_player') as YouTubePlayer | null)?.getPlayerResponse?.();
    } catch {
      // The player can be between instances during navigation.
    }
    const candidates = [playerResponse, (window as YouTubeWindow).ytInitialPlayerResponse, watchResponse]
      .map(candidate => selectCurrentYouTubePlayerResponse(videoId, candidate, null))
      .filter((candidate): candidate is Record<string, unknown> => candidate !== null);
    const primary = candidates[0];
    if (!primary) return null;
    const captionResponse = candidates.find(candidate => getYouTubeCaptionTracks(candidate).length > 0);
    const audioResponse = candidates.find(candidate => extractYouTubeDashAudio(candidate) !== null);
    return {
      ...primary,
      captions: captionResponse?.captions ?? primary.captions,
      streamingData: audioResponse?.streamingData ?? primary.streamingData,
    };
  }

  function read(): PageMediaData | null {
    const descriptor = parseYouTubeVideoUrl(location.href);
    const videoKey = descriptor?.video_key ?? null;
    if (videoKey !== activeKey) {
      activeKey = videoKey;
      generation++;
      cached = null;
      watchResponse = null;
      watchRequested = false;
      completedTrackUrl = null;
      pending = null;
    }
    if (!descriptor) return null;
    const response = currentResponse(descriptor.external_id);
    const details = asYouTubeObject(response?.videoDetails);
    const video = document.querySelector<HTMLVideoElement>('#movie_player video, video.html5-main-video, video');
    const duration = Number(details.lengthSeconds ?? video?.duration);
    const title = typeof details.title === 'string' ? details.title :
      document.querySelector('ytd-watch-metadata h1, #title h1, h1.ytd-watch-metadata')?.textContent?.trim() ||
      document.title.replace(/\s*[-–]\s*YouTube\s*$/, '');
    cached = {
      descriptor: {
        ...descriptor,
        title,
        duration: Number.isFinite(duration) && duration >= 0 ? duration : undefined,
        has_native_subtitle: getYouTubeCaptionTracks(response).length > 0,
      },
      transcript_source: cached?.transcript_source ?? 'none',
      segments: cached?.segments ?? [],
      dash_audio: extractYouTubeDashAudio(response) ?? cached?.dash_audio ?? null,
    };
    return cached;
  }

  async function collectCurrent(expectedGeneration: number): Promise<PageMediaData | null> {
    const initial = read();
    if (!initial) return null;
    const videoId = initial.descriptor.external_id;
    const stillCurrent = (): boolean => {
      read();
      return generation === expectedGeneration;
    };
    let response = currentResponse(videoId);
    if (!selectYouTubeCaptionTrack(response) && !watchRequested) {
      watchRequested = true;
      try {
        const page = await fetch(`${location.origin}/watch?v=${encodeURIComponent(videoId)}`, {
          credentials: 'include', signal: AbortSignal.timeout(6000),
        });
        if (page.ok) {
          const parsed = extractYouTubePlayerResponse(await page.text(), videoId);
          if (!stillCurrent()) return read();
          if (parsed) {
            watchResponse = parsed;
            response = currentResponse(videoId);
          } else watchRequested = false;
        } else if (stillCurrent()) watchRequested = false;
      } catch {
        if (stillCurrent()) watchRequested = false;
      }
    }
    if (!stillCurrent()) return read();
    read();
    const track = selectYouTubeCaptionTrack(response);
    if (!track || completedTrackUrl === track.baseUrl) return cached;
    try {
      const url = new URL(track.baseUrl, location.origin);
      url.searchParams.set('fmt', 'json3');
      const result = await fetch(url.href, { credentials: 'include', signal: AbortSignal.timeout(6000) });
      if (!stillCurrent()) return read();
      if (!result.ok) return read();
      const body: unknown = await result.json();
      if (!stillCurrent()) return read();
      const segments = parseYouTubeJson3(body);
      cached = {
        ...read()!,
        segments,
        transcript_source: segments.length ? track.kind === 'asr' ? 'platform_ai_subtitle' : 'platform_cc' : 'none',
      };
      completedTrackUrl = track.baseUrl;
    } catch {
      // Native captions, DASH and visual collection fail independently.
    }
    return read();
  }

  function collect(): Promise<PageMediaData | null> {
    if (!read()) return Promise.resolve(null);
    if (pending?.generation === generation) return pending.promise;
    const expectedGeneration = generation;
    const promise = collectCurrent(expectedGeneration).finally(() => {
      if (pending?.generation === expectedGeneration) pending = null;
    });
    pending = { generation: expectedGeneration, promise };
    return promise;
  }

  return { read, collect };
}
