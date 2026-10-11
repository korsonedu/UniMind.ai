import { useRef, useState } from 'react';

const DEFAULT_WIDTH = 208;
const MIN_WIDTH = 200;
const MAX_WIDTH = 320;

export function useDirectoryWidth() {
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  const [animated, setAnimated] = useState(false);
  const currentWidth = useRef(DEFAULT_WIDTH);
  const lastWidth = useRef(DEFAULT_WIDTH);
  const changeWidth = (value: number) => {
    const next = value < MIN_WIDTH ? 0 : Math.min(MAX_WIDTH, value);
    if (next === currentWidth.current) return;
    setAnimated((next === 0) !== (currentWidth.current === 0));
    currentWidth.current = next;
    if (next) lastWidth.current = next;
    setWidth(next);
  };
  return { width, contentWidth: width || lastWidth.current, animated, changeWidth, toggle: () => changeWidth(width ? 0 : lastWidth.current) };
}

export function DirectoryResizeHandle({ width, onChange, label }: { width: number; onChange: (width: number) => void; label: string }) {
  const start = useRef({ x: 0, width: 0 });
  return <div className="um-directory-resize" role="separator" aria-label={label} aria-orientation="vertical" aria-valuemin={0} aria-valuemax={MAX_WIDTH} aria-valuenow={width} aria-valuetext={width ? `${width} 像素` : '已隐藏'} tabIndex={0}
    onKeyDown={event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      onChange(event.key === 'Home' ? 0 : event.key === 'End' ? MAX_WIDTH : event.key === 'ArrowLeft' ? width - 16 : width ? width + 16 : DEFAULT_WIDTH);
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
    onPointerUp={event => { if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }} />;
}
