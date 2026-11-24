import { formatVideoKey } from '../../shared/bridge';
import type { ActiveVideoDescriptor, DashAudioTrackMeta, TranscriptSegmentItem } from '../../shared/types';

type JsonObject = Record<string, unknown>;

export interface YouTubeCaptionTrack {
  baseUrl: string;
  languageCode: string;
  kind?: string;
}

export function asYouTubeObject(value: unknown): JsonObject {
  return value !== null && typeof value === 'object' ? value as JsonObject : {};
}

export function parseYouTubeVideoUrl(input: string | URL): ActiveVideoDescriptor | null {
  let url: URL;
  try {
    url = new URL(input);
  } catch {
    return null;
  }
  if (!['http:', 'https:'].includes(url.protocol)) return null;
  const host = url.hostname.toLowerCase();
  let videoId: string | null = null;
  if (host === 'youtu.be') videoId = url.pathname.split('/')[1] ?? null;
  if (host === 'youtube.com' || host.endsWith('.youtube.com')) {
    if (url.pathname === '/watch') videoId = url.searchParams.get('v');
    else videoId = /^\/(?:shorts|embed|live)\/([^/]+)/.exec(url.pathname)?.[1] ?? null;
  }
  if (!videoId || !/^[A-Za-z0-9_-]{11}$/.test(videoId)) return null;
  return {
    platform: 'youtube',
    external_id: videoId,
    part: 1,
    video_key: formatVideoKey('youtube', videoId, 1),
    url: url.href,
    title: '',
  };
}

export function parseYouTubeJson3(input: unknown): TranscriptSegmentItem[] {
  const events = asYouTubeObject(input).events;
  if (!Array.isArray(events)) return [];
  const segments: TranscriptSegmentItem[] = [];
  for (const value of events) {
    const event = asYouTubeObject(value);
    if (!Array.isArray(event.segs)) continue;
    const text = event.segs.map(segment => {
      const utf8 = asYouTubeObject(segment).utf8;
      return typeof utf8 === 'string' ? utf8 : '';
    }).join('').replace(/\s+/g, ' ').trim();
    if (!text || /^[\s♪♫♬♩]+$/u.test(text)) continue;
    const start = Number(event.tStartMs);
    const duration = Number(event.dDurationMs) || 2000;
    if (!Number.isFinite(start) || start < 0 || !Number.isFinite(duration) || duration < 0) continue;
    segments.push({ start_time: start / 1000, end_time: (start + duration) / 1000, text });
  }
  return segments.sort((left, right) => left.start_time - right.start_time);
}

export function getYouTubeCaptionTracks(input: unknown): YouTubeCaptionTrack[] {
  const captions = asYouTubeObject(asYouTubeObject(input).captions);
  const renderer = asYouTubeObject(captions.playerCaptionsTracklistRenderer);
  const tracks = Array.isArray(input) ? input : renderer.captionTracks;
  if (!Array.isArray(tracks)) return [];
  return tracks.flatMap(value => {
    const track = asYouTubeObject(value);
    if (typeof track.baseUrl !== 'string' || !track.baseUrl) return [];
    return [{
      baseUrl: track.baseUrl,
      languageCode: typeof track.languageCode === 'string' ? track.languageCode : '',
      kind: typeof track.kind === 'string' ? track.kind : undefined,
    }];
  });
}

export function selectYouTubeCaptionTrack(input: unknown): YouTubeCaptionTrack | null {
  const rank = (track: YouTubeCaptionTrack): number => {
    const language = track.languageCode.toLowerCase();
    const languageRank = language.startsWith('zh') ? 0 : language.startsWith('en') ? 1 : 2;
    if (track.kind === 'asr') return 2 + languageRank;
    return languageRank === 2 ? 5 : languageRank;
  };
  return getYouTubeCaptionTracks(input).sort((left, right) => rank(left) - rank(right))[0] ?? null;
}

export function extractYouTubeDashAudio(input: unknown): DashAudioTrackMeta | null {
  const formats = asYouTubeObject(asYouTubeObject(input).streamingData).adaptiveFormats;
  if (!Array.isArray(formats)) return null;
  const audio = formats.map(asYouTubeObject).filter(format =>
    typeof format.url === 'string' && format.url.length > 0 &&
    typeof format.mimeType === 'string' && format.mimeType.startsWith('audio/mp4'),
  ).sort((left, right) => Number(left.bitrate ?? Infinity) - Number(right.bitrate ?? Infinity))[0];
  if (!audio) return null;
  const range = (value: unknown): string | undefined => {
    const object = asYouTubeObject(value);
    const start = Number(object.start);
    const end = Number(object.end);
    return Number.isSafeInteger(start) && start >= 0 && Number.isSafeInteger(end) && end >= start
      ? `${start}-${end}` : undefined;
  };
  const mimeType = String(audio.mimeType);
  const bitrate = Number(audio.bitrate);
  return {
    url: String(audio.url),
    bandwidth: Number.isFinite(bitrate) && bitrate > 0 ? bitrate : undefined,
    mimeType: mimeType.split(';')[0]?.trim(),
    codecs: /codecs="([^"]+)"/.exec(mimeType)?.[1],
    initRange: range(audio.initRange),
    indexRange: range(audio.indexRange),
    referer: 'https://www.youtube.com/',
  };
}

export function selectCurrentYouTubePlayerResponse(
  videoId: string, playerResponse: unknown, initialResponse: unknown,
): JsonObject | null {
  for (const candidate of [playerResponse, initialResponse]) {
    const response = asYouTubeObject(candidate);
    if (asYouTubeObject(response.videoDetails).videoId === videoId) return response;
  }
  return null;
}

/** Scan a JSON object without evaluating executable page script. */
export function extractYouTubePlayerResponse(html: string, videoId: string): JsonObject | null {
  const marker = /(?:ytInitialPlayerResponse\s*=|["']ytInitialPlayerResponse["']\s*\]?\s*[:=])\s*/g;
  for (let match = marker.exec(html); match; match = marker.exec(html)) {
    const start = marker.lastIndex;
    if (html[start] !== '{') continue;
    let depth = 0;
    let quoted = false;
    let escaped = false;
    for (let index = start; index < html.length; index++) {
      const character = html[index];
      if (quoted) {
        if (escaped) escaped = false;
        else if (character === '\\') escaped = true;
        else if (character === '"') quoted = false;
        continue;
      }
      if (character === '"') quoted = true;
      else if (character === '{') depth++;
      else if (character === '}') {
        depth--;
        if (depth !== 0) continue;
        try {
          const response: unknown = JSON.parse(html.slice(start, index + 1));
          const current = selectCurrentYouTubePlayerResponse(videoId, response, null);
          if (current) return current;
        } catch {
          // Other script text can contain this name. Continue to a valid assignment.
        }
        break;
      }
    }
  }
  return null;
}
