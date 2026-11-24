import type {
  ActiveVideoDescriptor, DashAudioTrackMeta, TranscriptSegmentItem, TranscriptSource,
} from '../shared/types';

const MAX_SEGMENTS = 80;
const MAX_SEGMENT_CHARACTERS = 1000;

export function sliceTranscriptWindow(
  segments: readonly TranscriptSegmentItem[],
  seconds: number,
  windowBefore = 45,
  windowAfter = 30,
): TranscriptSegmentItem[] {
  const start = Math.max(0, seconds - Math.max(0, windowBefore));
  const end = seconds + Math.max(0, windowAfter);
  const byStart = (a: TranscriptSegmentItem, b: TranscriptSegmentItem) => a.start_time - b.start_time;
  const inWindow = segments.filter(segment =>
    typeof segment?.text === 'string' && Number.isFinite(segment.start_time) && Number.isFinite(segment.end_time) &&
    segment.end_time >= segment.start_time && segment.end_time >= start && segment.start_time <= end,
  ).sort(byStart);
  const cleaned: TranscriptSegmentItem[] = [];
  const lastByText = new Map<string, TranscriptSegmentItem>();
  for (const segment of inWindow) {
    const text = segment.text.replace(/\s+/gu, ' ').trim();
    if (!text) continue;
    const last = lastByText.get(text);
    if (last && (segment.start_time < last.end_time || segment.start_time === last.start_time)) {
      last.end_time = Math.max(last.end_time, segment.end_time);
      continue;
    }
    const cue = {
      ...segment,
      text: text.length > MAX_SEGMENT_CHARACTERS
        ? Array.from(text).slice(0, MAX_SEGMENT_CHARACTERS).join('')
        : text,
    };
    lastByText.set(text, cue);
    cleaned.push(cue);
  }
  if (cleaned.length <= MAX_SEGMENTS) return cleaned;

  const distance = (segment: TranscriptSegmentItem) =>
    Math.max(0, seconds - segment.end_time, segment.start_time - seconds);
  return cleaned.sort((a, b) => distance(a) - distance(b)).slice(0, MAX_SEGMENTS).sort(byStart);
}

// Both worlds use this relay to share page-owned subtitle and DASH data.
export interface PageMediaData {
  descriptor: ActiveVideoDescriptor;
  transcript_source: TranscriptSource;
  segments: TranscriptSegmentItem[];
  dash_audio?: DashAudioTrackMeta | null;
}

export interface PageMediaCollector {
  read(): PageMediaData | null;
  collect(): Promise<PageMediaData | null>;
}

const PAGE_MEDIA_REQUEST = 'UNIMIND_PAGE_MEDIA_REQUEST';
const PAGE_MEDIA_UPDATE = 'UNIMIND_PAGE_MEDIA_UPDATE';

export interface PageMediaUpdate {
  type: typeof PAGE_MEDIA_UPDATE;
  payload: PageMediaData | null;
  requestId?: string;
}

function fromThisPage(event: MessageEvent): boolean {
  return event.source === window && event.origin === location.origin;
}

export function installPageMediaCollector(collector: PageMediaCollector): () => void {
  function update(payload: PageMediaData | null, requestId?: string) {
    window.postMessage({ type: PAGE_MEDIA_UPDATE, payload, requestId }, location.origin);
  }

  window.addEventListener('message', async event => {
    if (!fromThisPage(event) || event.data?.type !== PAGE_MEDIA_REQUEST) return;
    const { requestId, videoKey } = event.data;
    if (typeof videoKey !== 'string') return;
    try {
      const current = collector.read();
      if (requestId === undefined) {
        if (current?.descriptor.video_key === videoKey) update(current);
        return;
      }
      if (typeof requestId !== 'string') return;
      const data = current?.descriptor.video_key === videoKey ? await collector.collect() : null;
      update(data?.descriptor.video_key === videoKey ? data : null, requestId);
    } catch {
      if (typeof requestId === 'string') update(null, requestId);
    }
  });

  return () => update(collector.read());
}

export function requestPageMedia(videoKey: string, requestId?: string): void {
  window.postMessage({ type: PAGE_MEDIA_REQUEST, videoKey, requestId }, location.origin);
}

export function readPageMediaUpdate(event: MessageEvent): PageMediaUpdate | null {
  if (!fromThisPage(event) || event.data?.type !== PAGE_MEDIA_UPDATE) return null;
  const update = event.data as PageMediaUpdate;
  const data = update.payload;
  if (data === null || (typeof data?.descriptor?.video_key === 'string' && Array.isArray(data.segments))) {
    return update;
  }
  return null;
}
