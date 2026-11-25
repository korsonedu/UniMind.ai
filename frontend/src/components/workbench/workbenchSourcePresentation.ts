import { t } from '@/i18n';
import type { ProjectSourceChunk, ProjectSourceSummary, SourceAnchor } from '@/types/workbench';

export function sourceTypeLabel(source: ProjectSourceSummary) {
  switch (source.source_type) {
    case 'pdf': return 'PDF';
    case 'pptx': return 'PPT';
    case 'docx': return 'Word';
    case 'text': return t('文本');
    case 'web_url': return t('网页');
    case 'course': return t('课程');
    case 'uploaded_media': return source.mime_type.startsWith('audio/') ? t('音频') : t('视频');
    case 'external_video':
      if (source.metadata.platform === 'bilibili') return t('B站');
      if (source.metadata.platform === 'youtube') return 'YouTube';
      return t('外部视频');
  }
}

export function sourceUnitLabel(source: ProjectSourceSummary) {
  const values = { 0: source.unit_count };
  switch (source.source_type) {
    case 'pdf': return t('{0} 页', values);
    case 'pptx': return t('{0} 页 PPT', values);
    case 'uploaded_media':
    case 'external_video': return t('{0} 段字幕', values);
    case 'course': return t(source.duration_seconds > 0 ? '{0} 段字幕' : '{0} 个片段', values);
    default: return t('{0} 个章节', values);
  }
}

export function formatTimestamp(seconds: number) {
  const whole = Math.floor(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`;
}

export function findAnchoredChunk(chunks: ProjectSourceChunk[], anchor: SourceAnchor) {
  return chunks.find(chunk => chunk.id === anchor.chunkId)
    ?? chunks.find(chunk => chunk.chunk_index === anchor.chunkIndex)
    ?? chunks.find(chunk => (anchor.pageNumber != null && chunk.page_number === anchor.pageNumber)
      || (anchor.slideNumber != null && chunk.slide_number === anchor.slideNumber)
      || (anchor.startSeconds != null && chunk.start_seconds != null
        && chunk.start_seconds <= anchor.startSeconds && (chunk.end_seconds ?? chunk.start_seconds) >= anchor.startSeconds));
}

export function playbackHref(base: string | null, seconds: number | null, conversationId?: string) {
  if (!base) return null;
  if (/^\/course\/\d+([?#]|$)/.test(base)) {
    const url = new URL(base, 'https://unimind.invalid');
    if (seconds !== null) url.searchParams.set('t', String(seconds));
    if (conversationId) url.searchParams.set('conversation', conversationId);
    return `${url.pathname}${url.search}${url.hash}`;
  }
  if (!/^https?:\/\//i.test(base)) return null;
  const url = new URL(base);
  if (seconds !== null) {
    const host = url.hostname;
    const stamp = Math.floor(seconds);
    if (host === 'bilibili.com' || host.endsWith('.bilibili.com')) url.searchParams.set('t', String(stamp));
    if (host === 'youtu.be' || host === 'youtube.com' || host.endsWith('.youtube.com')) url.searchParams.set('t', `${stamp}s`);
  }
  return url.href;
}

export function sourcePlaybackHref(source: ProjectSourceSummary, seconds: number | null, conversationId?: string) {
  const { platform, external_id: id, part } = source.metadata;
  if (source.source_type === 'external_video' && id) {
    if (platform === 'bilibili') return playbackHref(`https://www.bilibili.com/video/${encodeURIComponent(id)}?p=${part ?? 1}`, seconds);
    if (platform === 'youtube') return playbackHref(`https://www.youtube.com/watch?v=${encodeURIComponent(id)}`, seconds);
  }
  return playbackHref(source.companion_play_url, seconds, conversationId);
}
