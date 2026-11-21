import { t, useLocale } from '@/i18n';
import { useRef } from 'react';

export function SidebarResizeHandle({ width, maxWidth = 640, onChange, onCommit, onCollapse }: {
  width: number; maxWidth?: number; onChange: (width: number) => void; onCommit: (width: number) => void; onCollapse: () => void;
}) {
  useLocale();
  const start = useRef({ x: 0, width: 0 });
  const clamp = (value: number) => Math.max(320, Math.min(maxWidth, value));
  return <div className="um-right-panel-resize" role="separator" aria-label={t('调整右侧栏宽度')} aria-orientation="vertical" aria-valuemin={320} aria-valuemax={maxWidth} aria-valuenow={width} tabIndex={0}
    onKeyDown={event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      onCommit(event.key === 'Home' ? 320 : event.key === 'End' ? maxWidth : clamp(width + (event.key === 'ArrowLeft' ? 16 : -16)));
    }}
    onPointerDown={event => {
      if (event.button !== 0) return;
      event.preventDefault();
      start.current = { x: event.clientX, width };
      event.currentTarget.setPointerCapture(event.pointerId);
    }}
    onPointerMove={event => {
      if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
      const next = start.current.width + start.current.x - event.clientX;
      if (next <= 160) {
        event.currentTarget.releasePointerCapture(event.pointerId);
        onCollapse();
      } else onChange(clamp(next));
    }}
    onPointerUp={event => {
      if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
      const next = start.current.width + start.current.x - event.clientX;
      event.currentTarget.releasePointerCapture(event.pointerId);
      if (next <= 160) onCollapse();
      else onCommit(clamp(next));
    }}
    onPointerCancel={event => {
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        onCommit(width);
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
    }} />;
}
