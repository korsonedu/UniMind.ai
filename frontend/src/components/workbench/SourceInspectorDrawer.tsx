import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowUpRight, Spinner } from '@phosphor-icons/react';
import { t } from '@/i18n';
import api from '@/lib/api';
import { sourceIsProcessing, useWorkbenchSourceDetail } from '@/lib/workbenchApi';
import type { ProjectSourceSummary, SourceAnchor } from '@/types/workbench';
import { WorkbenchPlaybackLink } from './CitationPill';
import { findAnchoredChunk, formatTimestamp, sourcePlaybackHref, sourceTypeLabel } from './workbenchSourcePresentation';

function PdfPreview({ path, page, title }: { path: string; page: number; title: string }) {
  const [blobUrl, setBlobUrl] = useState('');
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let objectUrl: string | undefined;
    // The serializer returns a Django-reversed /api path. The authenticated client already prefixes /api.
    api.get<Blob>(path.replace(/^\/api(?=\/)/, ''), { responseType: 'blob', timeout: 120_000, signal: controller.signal }).then(({ data }) => {
      if (controller.signal.aborted) return;
      objectUrl = URL.createObjectURL(data);
      setBlobUrl(objectUrl);
    }).catch(() => {
      if (!controller.signal.aborted) setFailed(true);
    });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path, attempt]);

  if (failed) return <button className="um-agent-button" onClick={() => { setFailed(false); setAttempt(value => value + 1); }}>{t('原文件加载失败，重试')}</button>;
  if (!blobUrl) return <p className="um-wb-muted" role="status">{t('正在打开 PDF…')}</p>;
  const href = `${blobUrl}#page=${page}`;
  return <div className="um-wb-pdf">
    <a href={href} target="_blank" rel="noopener noreferrer">{t('在新窗口打开 PDF')}<ArrowUpRight size={13} /></a>
    <iframe src={href} title={title} />
  </div>;
}

function excerpt(text: string, quote?: string) {
  const offset = quote ? text.indexOf(quote) : -1;
  if (offset < 0 || !quote) return text;
  return <>{text.slice(0, offset)}<mark>{quote}</mark>{text.slice(offset + quote.length)}</>;
}

export function SourceInspectorDrawer({ projectId, activeAnchor, summary, conversationId, onBack }: {
  projectId: number;
  activeAnchor: SourceAnchor;
  summary?: ProjectSourceSummary;
  conversationId: string;
  onBack: () => void;
}) {
  const detail = useWorkbenchSourceDetail(projectId, activeAnchor.sourceId, summary);
  const source = detail.data;
  const [previewAnchor, setPreviewAnchor] = useState<SourceAnchor | null>(null);
  const preview = previewAnchor === activeAnchor;
  const backButton = useRef<HTMLButtonElement>(null);
  const activeChunkRef = useRef<HTMLElement>(null);
  const activeChunk = source && findAnchoredChunk(source.chunks, activeAnchor);
  useEffect(() => { backButton.current?.focus({ preventScroll: true }); }, []);
  useEffect(() => {
    if (!preview) activeChunkRef.current?.scrollIntoView({
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
      block: 'center',
    });
  }, [activeAnchor, activeChunk, preview]);

  const seconds = activeChunk?.start_seconds ?? activeAnchor.startSeconds ?? null;
  const entry = source ?? summary;
  const topPlayback = source && sourcePlaybackHref(source, seconds, conversationId);

  return <>
    <header className="um-wb-pane-header um-wb-reader-back">
      <button ref={backButton} type="button" className="um-agent-button" onClick={onBack}><ArrowLeft size={16} />{t('返回资料列表')}</button>
      {entry && <span className="um-wb-file-type">{sourceTypeLabel(entry)}</span>}
    </header>
    <div className="um-wb-reader-heading">
      <h2>{source?.title ?? summary?.title ?? t('资料原文')}</h2>
      {source?.file_preview_url && source.source_type === 'pdf' && <div className="um-wb-segments" role="group" aria-label={t('PDF 阅读方式')}>
        <button type="button" aria-pressed={!preview} onClick={() => setPreviewAnchor(null)}>{t('文本定位视图')}</button>
        <button type="button" aria-pressed={preview} onClick={() => setPreviewAnchor(activeAnchor)}>{t('原文件预览')}</button>
      </div>}
      {topPlayback && <WorkbenchPlaybackLink href={topPlayback}>
        {seconds === null ? t('去伴学观看') : t('去伴学观看 ({0})', { 0: formatTimestamp(seconds) })}
      </WorkbenchPlaybackLink>}
    </div>
    <div className="um-wb-reader-content">
      {detail.isPending && <p className="um-wb-muted" role="status"><Spinner size={16} className="um-wb-spin" />{t('正在读取资料…')}</p>}
      {detail.isError && <button className="um-agent-button" onClick={() => void detail.refetch()}>{t('资料读取失败，重试')}</button>}
      {preview && source?.file_preview_url
        ? <PdfPreview path={source.file_preview_url} page={activeChunk?.page_number ?? activeAnchor.pageNumber ?? 1} title={source.title} />
        : source && <>
          {sourceIsProcessing(source) && <p className="um-wb-muted" role="status"><Spinner size={16} className="um-wb-spin" />{t('正在解析资料…')}</p>}
          {source.status === 'failed' && <p className="um-wb-error">{source.error_message}</p>}
          {source.status === 'ready' && source.chunks.length === 0 && <p className="um-wb-muted">{t('这份资料暂无可读文本。')}</p>}
          {source.chunks.map(chunk => {
            const selected = chunk.id === activeChunk?.id;
            const stamp = chunk.start_seconds;
            const segmentPlayback = stamp !== null && sourcePlaybackHref(source, stamp, conversationId);
            const notesStart = chunk.anchor_type === 'slide' ? chunk.content.search(/(?:^|\n)\[讲者备注\] /) : -1;
            const content = notesStart < 0 ? chunk.content : chunk.content.slice(0, notesStart);
            const notes = notesStart < 0 ? '' : chunk.content.slice(notesStart).replace(/^\s*\[讲者备注\] /, '');
            const quote = selected ? activeAnchor.quote : undefined;
            return <article key={chunk.id} className="um-wb-chunk" data-highlight={selected || undefined} ref={selected ? activeChunkRef : undefined}>
              <div className="um-wb-chunk-label">
                <span>{stamp === null ? chunk.locator_label : `[${formatTimestamp(stamp)}]`}</span>
                {segmentPlayback && stamp !== null && <WorkbenchPlaybackLink href={segmentPlayback}>{t('去伴学观看 ({0})', { 0: formatTimestamp(stamp) })}</WorkbenchPlaybackLink>}
              </div>
              {chunk.heading && chunk.heading !== chunk.locator_label && <h3>{chunk.heading}</h3>}
              {content && <p>{excerpt(content, quote)}</p>}
              {notes && <aside className="um-wb-slide-notes"><strong>{t('讲者备注')}</strong><p>{excerpt(notes, quote)}</p></aside>}
            </article>;
          })}
        </>}
    </div>
  </>;
}
