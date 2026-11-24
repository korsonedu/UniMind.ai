import { formatVideoKey } from '../../shared/bridge';
import type { ActiveVideoDescriptor, DashAudioTrackMeta, TranscriptSegmentItem } from '../../shared/types';

export { getWbiMixinKey, md5Hex, MIXIN_KEY_ENC_TAB, signWbiParams } from './wbi';

export function record(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? value as Record<string, unknown> : {};
}

export function parseBilibiliVideoUrl(input: string | URL): ActiveVideoDescriptor | null {
  let url: URL;
  try { url = new URL(input); } catch { return null; }
  if (!/(^|\.)bilibili\.com$/i.test(url.hostname)) return null;
  const match = /^\/video\/(BV[a-zA-Z0-9]+|av\d+)(?:\/|$)/.exec(url.pathname)
    ?? /^\/bangumi\/play\/(ep\d+|ss\d+)(?:\/|$)/.exec(url.pathname);
  if (!match?.[1]) return null;
  const rawPart = Number(url.searchParams.get('p') ?? 1);
  const part = Number.isSafeInteger(rawPart) && rawPart > 0 ? rawPart : 1;
  const external_id = match[1];
  return {
    platform: 'bilibili', external_id, part,
    video_key: formatVideoKey('bilibili', external_id, part), url: url.href, title: '',
  };
}

export interface BilibiliPageState {
  descriptor: ActiveVideoDescriptor;
  aid?: number;
  bvid?: string;
  cid?: number;
}

export function resolveBilibiliPageState(input: string | URL, initialState: unknown): BilibiliPageState | null {
  const descriptor = parseBilibiliVideoUrl(input);
  if (!descriptor) return null;
  const state = record(initialState);
  const videoData = record(state.videoData);
  let detail = videoData;
  let page: Record<string, unknown> = {};
  if (/^(ep|ss)/.test(descriptor.external_id)) {
    const episodes = Array.isArray(state.epList) ? state.epList.map(record) : [];
    const episodeId = descriptor.external_id.startsWith('ep') ? Number(descriptor.external_id.slice(2)) : undefined;
    detail = episodes.find(episode => Number(episode.id ?? episode.ep_id) === episodeId) ?? record(state.epInfo);
    if (episodeId && Number(detail.id ?? detail.ep_id) !== episodeId) detail = {};
    const mediaInfo = record(state.mediaInfo);
    if (descriptor.external_id.startsWith('ss') && Number(mediaInfo.season_id) !== Number(descriptor.external_id.slice(2))) detail = {};
  } else {
    const stateId = String(videoData.bvid ?? state.bvid ?? '');
    const stateAid = Number(videoData.aid ?? state.aid);
    const matches = descriptor.external_id.startsWith('BV')
      ? stateId === descriptor.external_id : stateAid === Number(descriptor.external_id.slice(2));
    if (!matches) return { descriptor };
    const pages = Array.isArray(videoData.pages) ? videoData.pages.map(record) : [];
    page = pages.find(item => Number(item.page) === descriptor.part) ?? pages[descriptor.part - 1] ?? {};
    // A missing requested part must never fall back to another part's top-level cid.
    if (pages.length && !Object.keys(page).length) return { descriptor };
  }
  const aid = Number(detail.aid ?? state.aid);
  const cid = Number(page.cid ?? (descriptor.part === 1 || /^(ep|ss)/.test(descriptor.external_id) ? detail.cid : undefined));
  const bvid = String(detail.bvid ?? state.bvid ?? '');
  const duration = Number(page.duration ?? detail.duration);
  const title = String(detail.title ?? record(state.mediaInfo).title ?? '');
  const partTitle = String(page.part ?? detail.long_title ?? '');
  descriptor.title = partTitle && partTitle !== title ? `${title} · ${partTitle}` : title;
  if (Number.isFinite(duration) && duration > 0) descriptor.duration = duration;
  return {
    descriptor,
    aid: Number.isSafeInteger(aid) && aid > 0 ? aid : undefined,
    cid: Number.isSafeInteger(cid) && cid > 0 ? cid : undefined,
    bvid: /^BV[a-zA-Z0-9]+$/.test(bvid) ? bvid : undefined,
  };
}

export interface BilibiliSubtitleTrack {
  lan: string;
  subtitle_url: string;
  isAI: boolean;
}

export function selectBilibiliSubtitle(input: unknown): BilibiliSubtitleTrack | null {
  const root = record(input);
  const data = record(root.data ?? root);
  const tracks = Array.isArray(input) ? input : record(data.subtitle).subtitles;
  if (!Array.isArray(tracks)) return null;
  const normalized = tracks.map(record).filter(track => typeof track.subtitle_url === 'string' && track.subtitle_url)
    .map(track => ({
      lan: String(track.lan ?? ''),
      subtitle_url: String(track.subtitle_url).replace(/^\/\//, 'https://'),
      isAI: String(track.lan ?? '').startsWith('ai-') || Number(track.ai_type ?? 0) > 0,
    }));
  const priority = (track: BilibiliSubtitleTrack) => {
    if (/^zh(?:-|$)/i.test(track.lan) && !track.isAI) return 0;
    if (track.lan === 'ai-zh') return 1;
    return 2;
  };
  return normalized.sort((a, b) => priority(a) - priority(b))[0] ?? null;
}

export function parseBilibiliSubtitles(input: unknown): TranscriptSegmentItem[] {
  const body = record(input).body;
  if (!Array.isArray(body)) return [];
  return body.map(record).flatMap(item => {
    const start = Number(item.from);
    const end = Number(item.to);
    const text = typeof item.content === 'string' ? item.content.replace(/\s+/g, ' ').trim() : '';
    if (!text || !Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end <= start) return [];
    return [{ start_time: start, end_time: end, text }];
  }).sort((a, b) => a.start_time - b.start_time);
}

export function extractBilibiliDashAudio(input: unknown): DashAudioTrackMeta | null {
  const root = record(input);
  const data = record(root.data ?? root.result ?? root);
  const audio = record(data.dash).audio;
  if (!Array.isArray(audio)) return null;
  const tracks = audio.map(record).filter(track => typeof (track.baseUrl ?? track.base_url) === 'string');
  tracks.sort((a, b) => (Number(a.bandwidth) || Infinity) - (Number(b.bandwidth) || Infinity));
  const track = tracks[0];
  if (!track) return null;
  const segmentBase = record(track.SegmentBase ?? track.segment_base);
  const backups = track.backupUrl ?? track.backup_url;
  return {
    url: String(track.baseUrl ?? track.base_url).replace(/^\/\//, 'https://'),
    backupUrls: Array.isArray(backups) ? backups.filter((url): url is string => typeof url === 'string').map(url => url.replace(/^\/\//, 'https://')) : undefined,
    bandwidth: Number(track.bandwidth) || undefined,
    mimeType: typeof (track.mimeType ?? track.mime_type) === 'string' ? String(track.mimeType ?? track.mime_type) : undefined,
    codecs: typeof track.codecs === 'string' ? track.codecs : undefined,
    initRange: typeof (segmentBase.Initialization ?? segmentBase.initialization) === 'string' ? String(segmentBase.Initialization ?? segmentBase.initialization) : undefined,
    indexRange: typeof (segmentBase.indexRange ?? segmentBase.index_range) === 'string' ? String(segmentBase.indexRange ?? segmentBase.index_range) : undefined,
    referer: 'https://www.bilibili.com/',
  };
}
