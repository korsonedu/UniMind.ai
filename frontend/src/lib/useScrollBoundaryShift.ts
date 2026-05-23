import { useEffect, useRef } from 'react';

/**
 * 滚动边界物理位移 — 当弹窗内滚动区域到达边界时，继续滚动会让
 * 整个容器产生微小的位移，松手后弹性回弹，模拟真实物理惯性。
 *
 * 用法：在 DialogContent / SheetContent 等固定定位容器上调用，
 * 传入容器 ref 和基准 transform（如居中用的 translate）。
 */
export function useScrollBoundaryShift(
  containerRef: React.RefObject<HTMLElement | null>,
  baseTransform = 'translate(-50%, -50%)',
  maxShift = 6,
) {
  const currentShift = useRef(0);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let targetShift = 0;
    let rafId = 0;
    let resetTimer: ReturnType<typeof setTimeout>;

    const applyTransform = (shift: number) => {
      if (shift === 0) {
        container.style.transform = '';
        return;
      }
      container.style.transform = `${baseTransform} translateY(${shift}px)`;
    };

    const spring = () => {
      const diff = targetShift - currentShift.current;
      if (Math.abs(diff) < 0.03) {
        currentShift.current = targetShift;
        applyTransform(currentShift.current);
        return; // spring settled
      }
      currentShift.current += diff * 0.28;
      applyTransform(currentShift.current);
      rafId = requestAnimationFrame(spring);
    };

    const startSpring = () => {
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(spring);
    };

    const scheduleReset = () => {
      clearTimeout(resetTimer);
      resetTimer = setTimeout(() => {
        targetShift = 0;
        startSpring();
      }, 150);
    };

    const isScrollable = (el: HTMLElement): boolean => {
      const overflowY = window.getComputedStyle(el).overflowY;
      return overflowY === 'auto' || overflowY === 'scroll';
    };

    const atBoundary = (el: HTMLElement, deltaY: number): boolean => {
      if (deltaY > 0) {
        return el.scrollTop + el.clientHeight >= el.scrollHeight - 1;
      }
      return el.scrollTop <= 0;
    };

    const handleWheel = (e: WheelEvent) => {
      // walk up from event target to find a scrollable ancestor inside the container
      let el = e.target as HTMLElement | null;
      while (el && el !== container.parentElement) {
        if (el !== container && isScrollable(el) && el.scrollHeight > el.clientHeight) {
          if (atBoundary(el, e.deltaY)) {
            // at boundary → physical shift + block body scroll-through
            e.preventDefault();
            const delta = Math.min(maxShift, Math.abs(e.deltaY) * 0.18);
            targetShift = e.deltaY > 0 ? -delta : delta;
            scheduleReset();
            startSpring();
            return;
          }
          // scrollable has room → let it scroll naturally, don't block
          return;
        }
        el = el.parentElement;
      }
      // no scrollable element found → block scroll from reaching body
      e.preventDefault();
    };

    // Touch support for mobile
    let touchStartY = 0;
    let lastTouchY = 0;

    const handleTouchStart = (e: TouchEvent) => {
      touchStartY = e.touches[0].clientY;
      lastTouchY = touchStartY;
    };

    const handleTouchMove = (e: TouchEvent) => {
      const touchY = e.touches[0].clientY;
      const deltaY = lastTouchY - touchY; // + = content scrolling down
      lastTouchY = touchY;

      let el = e.target as HTMLElement | null;
      while (el && el !== container.parentElement) {
        if (el !== container && isScrollable(el) && el.scrollHeight > el.clientHeight) {
          if (atBoundary(el, deltaY)) {
            e.preventDefault();
            const delta = Math.min(maxShift, Math.abs(deltaY) * 0.4);
            targetShift = deltaY > 0 ? -delta : delta;
            startSpring();
            return;
          }
          return;
        }
        el = el.parentElement;
      }
      // no scrollable element inside container → block touch scroll from reaching body
      e.preventDefault();
    };

    const handleTouchEnd = () => {
      targetShift = 0;
      startSpring();
    };

    container.addEventListener('wheel', handleWheel);
    container.addEventListener('touchstart', handleTouchStart, { passive: true });
    container.addEventListener('touchmove', handleTouchMove);
    container.addEventListener('touchend', handleTouchEnd, { passive: true });

    return () => {
      container.removeEventListener('wheel', handleWheel);
      container.removeEventListener('touchstart', handleTouchStart);
      container.removeEventListener('touchmove', handleTouchMove);
      container.removeEventListener('touchend', handleTouchEnd);
      cancelAnimationFrame(rafId);
      clearTimeout(resetTimer);
      container.style.transform = '';
    };
  }, [containerRef, baseTransform, maxShift]);
}
