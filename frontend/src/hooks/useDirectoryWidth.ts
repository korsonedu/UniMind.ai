import { useEffect, useRef, useState } from 'react';

const DEFAULT_WIDTH = 192;
const MIN_WIDTH = 180;
const MAX_WIDTH = 288;
const COLLAPSE_WIDTH = MIN_WIDTH / 2;
const STIFFNESS = 1200;
const DAMPING = 80;

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
    if (!spring || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      currentWidth.current = next;
      setWidth(next);
      return;
    }
    const initial = currentWidth.current;
    const start = performance.now();
    const root = Math.sqrt(DAMPING * DAMPING - 4 * STIFFNESS);
    const slow = (-DAMPING + root) / 2;
    const fast = (-DAMPING - root) / 2;
    const step = (now: number) => {
      const t = (now - start) / 1000;
      const position = next + (initial - next) * (fast * Math.exp(slow * t) - slow * Math.exp(fast * t)) / (fast - slow);
      if (Math.abs(position - next) < 0.4) {
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
