import { useRef, useState } from 'react';

const DEFAULT_WIDTH = 208;
const MIN_WIDTH = 200;
const MAX_WIDTH = 320;
const COLLAPSE_WIDTH = MIN_WIDTH / 2;

export function previewDirectoryWidth(value: number, collapseThreshold = COLLAPSE_WIDTH) {
  if (value <= collapseThreshold) return 0;
  return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, value));
}

export function resolveDirectoryWidth(value: number, collapseThreshold = COLLAPSE_WIDTH) {
  if (value <= collapseThreshold) return 0;
  return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, value));
}

export function useDirectoryWidth(collapseThreshold = COLLAPSE_WIDTH) {
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  const [animated, setAnimated] = useState(false);
  const currentWidth = useRef(DEFAULT_WIDTH);
  const [lastWidth, setLastWidth] = useState(DEFAULT_WIDTH);
  const applyWidth = (next: number) => {
    if (next === currentWidth.current) return;
    setAnimated((next === 0) !== (currentWidth.current === 0));
    currentWidth.current = next;
    if (next >= MIN_WIDTH) setLastWidth(next);
    setWidth(next);
  };
  const changeWidth = (value: number) => applyWidth(resolveDirectoryWidth(value, collapseThreshold));
  const previewWidth = (value: number) => applyWidth(previewDirectoryWidth(value, collapseThreshold));
  return { width, contentWidth: width || lastWidth, animated, changeWidth, previewWidth, toggle: () => changeWidth(width ? 0 : lastWidth) };
}
