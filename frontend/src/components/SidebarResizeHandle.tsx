import { useRef } from 'react';

export function SidebarResizeHandle({ width, onChange, onCommit }: {
  width: number; onChange: (width: number) => void; onCommit: (width: number) => void;
}) {
  const start = useRef({ x: 0, width: 0 });
  const clamp = (value: number) => Math.max(320, Math.min(640, value));
  return <div className="um-right-panel-resize" role="separator" aria-label="调整右侧栏宽度" aria-orientation="vertical" aria-valuemin={320} aria-valuemax={640} aria-valuenow={width} tabIndex={0}
    onKeyDown={event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      onCommit(event.key === 'Home' ? 320 : event.key === 'End' ? 640 : clamp(width + (event.key === 'ArrowLeft' ? 16 : -16)));
    }}
    onPointerDown={event => {
      if (event.button !== 0) return;
      event.preventDefault();
      start.current = { x: event.clientX, width };
      event.currentTarget.setPointerCapture(event.pointerId);
    }}
    onPointerMove={event => {
      if (event.currentTarget.hasPointerCapture(event.pointerId)) onChange(clamp(start.current.width + start.current.x - event.clientX));
    }}
    onPointerUp={event => {
      if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
      onCommit(clamp(start.current.width + start.current.x - event.clientX));
      event.currentTarget.releasePointerCapture(event.pointerId);
    }}
    onPointerCancel={event => {
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        onCommit(width);
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
    }} />;
}
