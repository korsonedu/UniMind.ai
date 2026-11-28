import { useLayoutEffect, useRef } from 'react';
import { t } from '@/i18n';

export function CitationLines({ content, line }: { content: string; line: number | null }) {
  const target = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    target.current?.scrollIntoView({ block: 'center' });
  }, [content, line]);

  return <div className="my-4 whitespace-pre-wrap break-words text-sm leading-relaxed" aria-label={t('原文')}>
    {content.split(/\r\n|\r|\n/).map((text, index) => {
      const number = index + 1;
      const cited = number === line;
      return <div key={number} ref={cited ? target : undefined} data-cited-line={cited ? number : undefined}
        className={cited ? 'flex rounded bg-primary/15' : 'flex'}>
        <span className="w-12 shrink-0 select-none pr-3 text-right tabular-nums text-muted-foreground">{number}</span>
        <span>{text || '\u00a0'}</span>
      </div>;
    })}
  </div>;
}
