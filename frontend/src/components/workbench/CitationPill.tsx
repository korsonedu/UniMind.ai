import { useId, useState } from 'react';
import * as HoverCard from '@radix-ui/react-hover-card';
import { ArrowUpRight, Play } from '@phosphor-icons/react';
import { Link } from 'react-router-dom';
import { t } from '@/i18n';
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import type { SourceAnchor, WorkbenchCitation } from '@/types/workbench';
import { formatTimestamp, playbackHref } from './workbenchSourcePresentation';

export function WorkbenchPlaybackLink({ href, children }: { href: string; children: React.ReactNode }) {
  const content = <><Play size={13} weight="fill" aria-hidden />{children}</>;
  return href.startsWith('/')
    ? <Link className="um-wb-play" to={href}>{content}</Link>
    : <a className="um-wb-play" href={href} target="_blank" rel="noopener noreferrer">{content}<ArrowUpRight size={12} aria-hidden /></a>;
}

export function CitationPill({ citation, conversationId, onSelect }: {
  citation: WorkbenchCitation;
  conversationId: string;
  onSelect: (anchor: SourceAnchor) => void;
}) {
  const [open, setOpen] = useState(false);
  const descriptionId = useId();
  const seconds = citation.start_seconds;
  const href = playbackHref(citation.companion_url, seconds, conversationId);
  const locator = citation.line
    ? [citation.page_number && `P.${citation.page_number}`, t('第 {0} 行', { 0: citation.line })].filter(Boolean).join(' · ')
    : seconds === null ? citation.locator_label : formatTimestamp(seconds);
  if (href && seconds !== null && /T\d+$/.test(citation.cite_key)) {
    const label = <><Play size={11} weight="fill" aria-hidden /><span className="um-wb-citation-title">{citation.source_title}</span><span className="um-wb-citation-locator">{locator}</span></>;
    const title = `${citation.source_title} · ${locator}`;
    return href.startsWith('/')
      ? <Link to={href} className="um-wb-citation" title={title}>{label}</Link>
      : <a href={href} className="um-wb-citation" title={title} target="_blank" rel="noopener noreferrer">{label}</a>;
  }

  return <HoverCard.Root open={open} onOpenChange={setOpen} openDelay={160} closeDelay={220}>
    <HoverCard.Trigger asChild>
      <button type="button" className="um-wb-citation" aria-describedby={open ? descriptionId : undefined}
        title={`${citation.source_title} · ${locator}`}
        onClick={() => {
          setOpen(false);
          onSelect({
            sourceId: citation.source_id, chunkId: citation.chunk_id, chunkIndex: citation.chunk_index,
            pageNumber: citation.page_number, slideNumber: citation.slide_number, startSeconds: seconds, quote: citation.quote,
            ...(citation.line && { line: citation.line, chunkLine: citation.chunk_line }),
          });
        }}>
        {seconds === null ? <span className="um-wb-citation-index">{citation.index}</span> : <Play size={11} weight="fill" aria-hidden />}
        <span className="um-wb-citation-title">{citation.source_title}</span>
        <span className="um-wb-citation-locator">{locator}</span>
      </button>
    </HoverCard.Trigger>
    <HoverCard.Portal>
      <HoverCard.Content id={descriptionId} className="um-native-agent um-wb-citation-popover" side="top" align="start" sideOffset={8} collisionPadding={12}>
        <strong>{citation.source_title}</strong>
        <span className="um-wb-muted">{locator}</span>
        {citation.quote && <blockquote>{citation.quote}</blockquote>}
        {href && seconds !== null && <WorkbenchPlaybackLink href={href}>
          {t('去伴学看画面 ({0})', { 0: formatTimestamp(seconds) })}
        </WorkbenchPlaybackLink>}
      </HoverCard.Content>
    </HoverCard.Portal>
  </HoverCard.Root>;
}

export type AssetCitation = { key: string; title: string; href: string } & (
  { kind: 'article' | 'note'; line: number } | { kind: 'video'; seconds: number }
  | { kind: 'web'; line: number; text: string }
);

export function AssetCitationLink({ citation }: { citation: AssetCitation }) {
  const locator = citation.kind === 'video' ? formatTimestamp(citation.seconds) : t('第 {0} 行', { 0: citation.line });
  const title = `${citation.title} · ${locator}`;
  const label = <><span className="um-wb-citation-title">{citation.title}</span><span className="um-wb-citation-locator">{locator}</span></>;
  if (citation.kind === 'web') {
    const text = encodeURIComponent(citation.text.trim()).replaceAll('-', '%2D');
    const href = citation.href.split('#', 1)[0] + '#:~:text=' + text;
    return <Dialog>
      <DialogTrigger asChild><button type="button" title={title} className="um-wb-citation">{label}</button></DialogTrigger>
      <DialogContent>
        <DialogTitle className="pr-8">{citation.title}</DialogTitle>
        <DialogDescription>{locator}</DialogDescription>
        <blockquote data-cited-line={citation.line} className="max-h-[50dvh] overflow-auto whitespace-pre-wrap rounded bg-primary/10 p-3 text-sm">{citation.text}</blockquote>
        <a href={href} target="_blank" rel="noopener noreferrer" className="text-sm text-primary underline">{t('打开原网页')}</a>
      </DialogContent>
    </Dialog>;
  }
  return <Link className="um-wb-citation" to={citation.href} title={title}>{label}</Link>;
}
