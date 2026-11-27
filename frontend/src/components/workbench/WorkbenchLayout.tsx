import { useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { Books, ChatCircleText, SidebarSimple, Sparkle } from '@phosphor-icons/react';
import { t } from '@/i18n';
import './workbench.css';

export type WorkbenchTab = 'sources' | 'chat' | 'studio';

function PaneResize({ side, width, min, max, onChange }: {
  side: 'left' | 'right';
  width: number;
  min: number;
  max: number;
  onChange: (width: number) => void;
}) {
  const start = useRef({ x: 0, width: 0 });
  const direction = side === 'left' ? 1 : -1;
  const resize = (next: number) => onChange(Math.max(min, Math.min(max, next)));

  return <div className="um-wb-resize" role="separator" tabIndex={0} aria-orientation="vertical"
    aria-label={side === 'left' ? t('调整资料宽度') : t('调整 Studio 宽度')}
    aria-valuemin={min} aria-valuemax={max} aria-valuenow={width}
    onKeyDown={event => {
      const delta = event.key === 'ArrowRight' ? 16 : event.key === 'ArrowLeft' ? -16 : 0;
      if (!delta && event.key !== 'Home' && event.key !== 'End') return;
      event.preventDefault();
      resize(delta ? width + delta * direction : event.key === 'Home' ? min : max);
    }}
    onPointerDown={event => {
      if (event.button !== 0) return;
      event.preventDefault();
      start.current = { x: event.clientX, width: event.currentTarget.parentElement!.getBoundingClientRect().width };
      event.currentTarget.setPointerCapture(event.pointerId);
    }}
    onPointerMove={event => {
      if (event.currentTarget.hasPointerCapture(event.pointerId)) resize(start.current.width + (event.clientX - start.current.x) * direction);
    }}
  />;
}

export function WorkbenchLayout({ sources, children, studio, sourceCount, reading, mobileTab, setMobileTab, leftOpen, setLeftOpen }: {
  sources: ReactNode;
  children: ReactNode;
  studio: ReactNode;
  sourceCount: number;
  reading: boolean;
  mobileTab: WorkbenchTab;
  setMobileTab: (tab: WorkbenchTab) => void;
  leftOpen: boolean;
  setLeftOpen: (open: boolean) => void;
}) {
  const [sourceWidth, setSourceWidth] = useState(296);
  const [readerWidth, setReaderWidth] = useState(420);
  const [rightOpen, setRightOpen] = useState(true);
  const [rightWidth, setRightWidth] = useState(320);
  const leftWidth = reading ? readerWidth : sourceWidth;
  const tabs = [
    { id: 'sources', label: t('资料 ({0})', { 0: sourceCount }), icon: Books },
    { id: 'chat', label: t('对话'), icon: ChatCircleText },
    { id: 'studio', label: 'Studio', icon: Sparkle },
  ] as const;

  return <div className="um-wb-layout" data-tab={mobileTab} data-left={leftOpen} data-right={rightOpen}
    style={{ '--wb-left': `${leftWidth}px`, '--wb-right': `${rightWidth}px` } as CSSProperties}>
    <div className="um-wb-mobile-nav um-wb-segments" role="group" aria-label={t('项目工作台视图')}>
      {tabs.map(({ id, label, icon: Icon }) => <button key={id} type="button" aria-pressed={id === mobileTab}
        onClick={() => setMobileTab(id)}><Icon size={16} />{label}</button>)}
    </div>
    <div className="um-wb-grid">
      <section className="um-wb-pane um-wb-left" aria-label={t('项目资料')}>
        {sources}
        {leftOpen && <PaneResize side="left" width={leftWidth} min={reading ? 300 : 260} max={reading ? 620 : 380} onChange={reading ? setReaderWidth : setSourceWidth} />}
      </section>
      <section className="um-wb-pane um-wb-chat" aria-label={t('项目对话')}>
        <header className="um-wb-pane-header um-wb-chat-header">
          <button type="button" className="um-agent-icon-button" aria-expanded={leftOpen} aria-label={t('资料面板')}
            title={leftOpen ? t('收起资料面板') : t('展开资料面板')} onClick={() => setLeftOpen(!leftOpen)}><SidebarSimple size={18} /></button>
          <h2>{t('对话')}</h2>
          <button type="button" className="um-agent-icon-button" aria-expanded={rightOpen} aria-label={t('Studio 面板')}
            title={rightOpen ? t('收起 Studio') : t('展开 Studio')} onClick={() => setRightOpen(!rightOpen)}><SidebarSimple size={18} className="um-wb-flip" /></button>
        </header>
        {children}
      </section>
      <section className="um-wb-pane um-wb-right" aria-label="Studio">
        {studio}
        {rightOpen && <PaneResize side="right" width={rightWidth} min={280} max={400} onChange={setRightWidth} />}
      </section>
    </div>
  </div>;
}
