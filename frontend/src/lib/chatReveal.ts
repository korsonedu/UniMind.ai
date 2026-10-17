export const STEP_DELAY_MS = 600;

interface RevealQueueOptions {
  delayMs?: number;
  isActive: () => boolean;
  onReveal: (id: string) => void;
}

/** 每次请求独立的显示队列，避免旧请求清理新请求的定时器。 */
export function createRevealQueue({
  delayMs = STEP_DELAY_MS,
  isActive,
  onReveal,
}: RevealQueueOptions) {
  let shownCount = 0;
  const timers = new Set<ReturnType<typeof setTimeout>>();

  return {
    schedule(id: string, position: number) {
      if (!isActive()) return;
      const delay = Math.max(0, position - shownCount) * delayMs;
      const timer = setTimeout(() => {
        timers.delete(timer);
        if (!isActive()) return;
        shownCount = Math.max(shownCount, position + 1);
        onReveal(id);
      }, delay);
      timers.add(timer);
    },
    dispose() {
      timers.forEach(clearTimeout);
      timers.clear();
    },
  };
}
