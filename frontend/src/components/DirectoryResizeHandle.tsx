import { useRef } from 'react';

const DEFAULT_WIDTH = 208;

const MAX_WIDTH = 320;

export function DirectoryResizeHandle({ width, onChange, onCommit, label }: { width: number; onChange: (width: number) => void; onCommit?: (width: number) => void; label: string }) {
  const start = useRef({ x: 0, width: 0 });
  return <div className="um-directory-resize" role="separator" aria-label={label} aria-orientation="vertical" aria-valuemin={0} aria-valuemax={MAX_WIDTH} aria-valuenow={width} aria-valuetext={width ? `${width} 像素` : '已隐藏'} tabIndex={0}
    onKeyDown={event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      (onCommit || onChange)(event.key === 'Home' ? 0 : event.key === 'End' ? MAX_WIDTH : event.key === 'ArrowLeft' ? width - 16 : width ? width + 16 : DEFAULT_WIDTH);
    }}
    onPointerDown={event => {
      if (event.button !== 0) return;
      event.preventDefault();
      start.current = { x: event.clientX, width };
      event.currentTarget.setPointerCapture(event.pointerId);
    }}
    onPointerMove={event => {
      if (event.currentTarget.hasPointerCapture(event.pointerId)) onChange(start.current.width + event.clientX - start.current.x);
    }}
    onPointerUp={event => {
      if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
      onCommit?.(start.current.width + event.clientX - start.current.x);
      event.currentTarget.releasePointerCapture(event.pointerId);
    }} />;
}
