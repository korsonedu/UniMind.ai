import { useEffect, useRef, useState } from 'react';
import { useSystemStore } from '@/store/useSystemStore';

const DEFAULT_WIDTH = 192;
const MIN_WIDTH = 180;
const MAX_WIDTH = 288;
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
  const [collapsed, setCollapsed] = useState(false);
  const currentWidth = useRef(DEFAULT_WIDTH);
  const targetWidth = useRef(DEFAULT_WIDTH);
  const [lastWidth, setLastWidth] = useState(DEFAULT_WIDTH);
  const frame = useRef<number | null>(null);

  const stop = () => {
    if (frame.current !== null) cancelAnimationFrame(frame.current);
    frame.current = null;
  };

  useEffect(() => stop, []);

  const commit = (next: number, spring: boolean) => {
    if (next === targetWidth.current && spring) return;
    stop();
    targetWidth.current = next;
    setCollapsed(next === 0);
    if (next === currentWidth.current) return;
    setAnimated(spring);
    if (next >= MIN_WIDTH) setLastWidth(next);
    if (!spring || useSystemStore.getState().reduceMotion || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      currentWidth.current = next;
      setWidth(next);
      return;
    }
    const initial = currentWidth.current;
    const start = performance.now();
    const step = (now: number) => {
      const progress = Math.min((now - start) / 180, 1);
      const position = next + (initial - next) * (1 - progress) ** 3;
      if (progress === 1 || useSystemStore.getState().reduceMotion || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        currentWidth.current = next;
        setWidth(next);
        frame.current = null;
        return;
      }
      currentWidth.current = position;
      setWidth(position);
      frame.current = requestAnimationFrame(step);
    };
    frame.current = requestAnimationFrame(step);
  };

  const changeWidth = (value: number) => commit(resolveDirectoryWidth(value, collapseThreshold), true);
  const previewWidth = (value: number) => {
    const next = previewDirectoryWidth(value, collapseThreshold);
    commit(next, next === 0);
  };
  return { width, contentWidth: animated ? lastWidth : Math.max(MIN_WIDTH, width || lastWidth), collapsed, animated, changeWidth, previewWidth, toggle: () => changeWidth(collapsed ? lastWidth : 0) };
}
