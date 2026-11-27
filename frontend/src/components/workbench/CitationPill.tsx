import { useId, useState } from 'react';
import * as HoverCard from '@radix-ui/react-hover-card';
import { ArrowUpRight, Play } from '@phosphor-icons/react';
import { Link } from 'react-router-dom';
import { t } from '@/i18n';
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
  const locator = seconds === null ? citation.locator_label : formatTimestamp(seconds);

  return <HoverCard.Root open={open} onOpenChange={setOpen} openDelay={160} closeDelay={220}>
    <HoverCard.Trigger asChild>
      <button type="button" className="um-wb-citation" aria-describedby={open ? descriptionId : undefined}
        title={`${citation.source_title} · ${locator}`}
        onClick={() => {
          setOpen(false);
          onSelect({
            sourceId: citation.source_id, chunkId: citation.chunk_id, chunkIndex: citation.chunk_index,
            pageNumber: citation.page_number, slideNumber: citation.slide_number, startSeconds: seconds, quote: citation.quote,
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
        <span className="um-wb-muted">{citation.locator_label}</span>
        {citation.quote && <blockquote>{citation.quote}</blockquote>}
        {href && seconds !== null && <WorkbenchPlaybackLink href={href}>
          {t('去伴学看画面 ({0})', { 0: formatTimestamp(seconds) })}
        </WorkbenchPlaybackLink>}
      </HoverCard.Content>
    </HoverCard.Portal>
  </HoverCard.Root>;
}
