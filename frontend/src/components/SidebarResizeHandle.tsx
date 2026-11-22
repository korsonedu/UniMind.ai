import { t, useLocale } from '@/i18n';
import { useEffect, useRef } from 'react';
import { clampSidebarWidth, fullscreenSnapThreshold, MIN_SIDEBAR_WIDTH, sidebarDragPreview, type SidebarDragPreview } from '@/lib/rightSidebarLayout';

type DragSession = {
  x: number;
  width: number;
  lastSplitWidth: number;
  pointerId: number;
  handle: HTMLDivElement;
};

export function SidebarResizeHandle({ width, splitWidth, containerWidth, fullscreen, preview, onPreview, onCommit, onCollapse }: {
  width: number;
  splitWidth: number;
  containerWidth: number;
  fullscreen: boolean;
  preview: SidebarDragPreview | null;
  onPreview: (preview: SidebarDragPreview | null) => void;
  onCommit: (width: number, fullscreen: boolean) => void;
  onCollapse: () => void;
}) {
  useLocale();
  const drag = useRef<DragSession | null>(null);

  useEffect(() => {
    const cancel = () => {
      const session = drag.current;
      if (!session) return;
      drag.current = null;
      onPreview(null);
      if (session.handle.hasPointerCapture(session.pointerId)) session.handle.releasePointerCapture(session.pointerId);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || !drag.current) return;
      event.preventDefault();
      event.stopPropagation();
      cancel();
    };
    window.addEventListener('keydown', onKeyDown, true);
    window.addEventListener('blur', cancel);
    return () => {
      window.removeEventListener('keydown', onKeyDown, true);
      window.removeEventListener('blur', cancel);
      cancel();
    };
  }, [onPreview]);

  const toggleFullscreen = () => onCommit(splitWidth, !fullscreen);
  return <div className="um-right-panel-resize" role="separator" aria-controls="um-right-panel" aria-label={t('调整右侧栏宽度')} aria-orientation="vertical" aria-valuemin={0} aria-valuemax={containerWidth} aria-valuenow={width} aria-valuetext={fullscreen && !preview ? t('全屏展开') : t('{0} 像素', { 0: Math.round(width) })} tabIndex={0} data-snap={preview?.snap ?? undefined}
    onDoubleClick={toggleFullscreen}
    onKeyDown={event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End', 'Enter'].includes(event.key) || drag.current) return;
      event.preventDefault();
      if (event.key === 'Enter' || event.key === 'End') { toggleFullscreen(); return; }
      const next = event.key === 'Home' ? MIN_SIDEBAR_WIDTH : (fullscreen ? containerWidth : splitWidth) + (event.key === 'ArrowLeft' ? 24 : -24);
      const nextFullscreen = event.key === 'ArrowLeft' && next > fullscreenSnapThreshold(containerWidth);
      onCommit(nextFullscreen ? splitWidth : clampSidebarWidth(next, containerWidth), nextFullscreen);
    }}
    onPointerDown={event => {
      if (event.button !== 0 || drag.current) return;
      event.preventDefault();
      event.currentTarget.focus({ preventScroll: true });
      drag.current = { x: event.clientX, width: fullscreen ? containerWidth : width, lastSplitWidth: splitWidth, pointerId: event.pointerId, handle: event.currentTarget };
      event.currentTarget.setPointerCapture(event.pointerId);
      onPreview({ width: fullscreen ? containerWidth : width, snap: null });
    }}
    onPointerMove={event => {
      const session = drag.current;
      if (!session || session.pointerId !== event.pointerId) return;
      const next = sidebarDragPreview(session.width + session.x - event.clientX, containerWidth);
      onPreview(next);
    }}
    onPointerUp={event => {
      const session = drag.current;
      if (!session || session.pointerId !== event.pointerId) return;
      const next = sidebarDragPreview(session.width + session.x - event.clientX, containerWidth);
      drag.current = null;
      onPreview(null);
      event.currentTarget.releasePointerCapture(event.pointerId);
      if (next.snap === 'collapse') onCollapse();
      else onCommit(next.snap === 'fullscreen' ? session.lastSplitWidth : clampSidebarWidth(next.width, containerWidth), next.snap === 'fullscreen');
    }}
    onLostPointerCapture={() => {
      if (!drag.current) return;
      drag.current = null;
      onPreview(null);
    }}
    onPointerCancel={event => {
      if (drag.current?.pointerId !== event.pointerId) return;
      drag.current = null;
      onPreview(null);
      if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    }}>
    {preview?.snap && <span className="um-right-panel-snap-tip" role="status">{preview.snap === 'fullscreen' ? t('松开全屏展开') : t('松开收起右侧栏')}</span>}
  </div>;
}
