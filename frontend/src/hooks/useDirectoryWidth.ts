import { useRef, useState } from 'react';

const DEFAULT_WIDTH = 208;
const MIN_WIDTH = 200;
const MAX_WIDTH = 320;

export function useDirectoryWidth() {
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  const [animated, setAnimated] = useState(false);
  const currentWidth = useRef(DEFAULT_WIDTH);
  const [lastWidth, setLastWidth] = useState(DEFAULT_WIDTH);
  const changeWidth = (value: number) => {
    const next = value < MIN_WIDTH ? 0 : Math.min(MAX_WIDTH, value);
    if (next === currentWidth.current) return;
    setAnimated((next === 0) !== (currentWidth.current === 0));
    currentWidth.current = next;
    if (next) setLastWidth(next);
    setWidth(next);
  };
  return { width, contentWidth: width || lastWidth, animated, changeWidth, toggle: () => changeWidth(width ? 0 : lastWidth) };
}
