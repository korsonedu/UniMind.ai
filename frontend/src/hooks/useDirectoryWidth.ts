import { useEffect, useRef, useState } from 'react';

const DEFAULT_WIDTH = 208;
const MIN_WIDTH = 200;
const MAX_WIDTH = 320;
const COLLAPSE_WIDTH = MIN_WIDTH / 2;
const STIFFNESS = 1200;
const DAMPING = 80;
const MASS = 1;

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
  const frame = useRef<number | null>(null);

  const stop = () => {
    if (frame.current !== null) cancelAnimationFrame(frame.current);
    frame.current = null;
  };

  useEffect(() => stop, []);

  const commit = (next: number, spring: boolean) => {
    stop();
    if (next === currentWidth.current) return;
    setAnimated((next === 0) !== (currentWidth.current === 0));
    if (next >= MIN_WIDTH) setLastWidth(next);
    if (!spring) {
      currentWidth.current = next;
      setWidth(next);
      return;
    }
    let position = currentWidth.current;
    let velocity = 0;
    let last = performance.now();
    const step = (now: number) => {
      const dt = Math.min(0.032, Math.max(0.001, (now - last) / 1000));
      last = now;
      const acceleration = (-STIFFNESS * (position - next) - DAMPING * velocity) / MASS;
      velocity += acceleration * dt;
      position += velocity * dt;
      if (Math.abs(position - next) < 0.4 && Math.abs(velocity) < 6) {
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
  const previewWidth = (value: number) => commit(previewDirectoryWidth(value, collapseThreshold), false);
  return { width, contentWidth: width || lastWidth, animated, changeWidth, previewWidth, toggle: () => changeWidth(width ? 0 : lastWidth) };
}
