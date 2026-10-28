export const STEP_DELAY_MS = 600;

/** 流式文字平滑器：按帧放出累计文本，积压越多追得越快。 */
interface StreamSmootherOptions {
  isActive: () => boolean;
  onUpdate: (text: string) => void;
}

const STREAM_BASE_CPS = 45;
const STREAM_CATCHUP_SECONDS = 0.18;
const STREAM_PAINT_INTERVAL_MS = 32;

export function createStreamSmoother({ isActive, onUpdate }: StreamSmootherOptions) {
  let target = '';
  let shown = 0;
  let carry = 0;
  let frame: number | null = null;
  let lastTick: number | null = null;
  let lastPaint = -Infinity;
  let disposed = false;
  const reduced = typeof window !== 'undefined'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const stop = () => {
    if (frame !== null) {
      cancelAnimationFrame(frame);
      frame = null;
    }
    lastTick = null;
  };

  const paint = () => {
    // 不把 emoji 等代理对截成半个字符。
    if (shown > 0 && shown < target.length) {
      const code = target.charCodeAt(shown - 1);
      if (code >= 0xd800 && code <= 0xdbff) shown += 1;
    }
    if (isActive()) onUpdate(target.slice(0, shown));
  };

  const tick = (now: number) => {
    frame = null;
    if (disposed || !isActive()) return;
    const elapsed = lastTick === null ? 1 / 60 : Math.min((now - lastTick) / 1000, 0.1);
    lastTick = now;
    const backlog = target.length - shown;
    if (backlog <= 0) {
      carry = 0;
      return;
    }
    carry += Math.max(STREAM_BASE_CPS, backlog / STREAM_CATCHUP_SECONDS) * elapsed;
    const step = Math.min(backlog, Math.floor(carry));
    if (step > 0) {
      shown += step;
      carry -= step;
      if (now - lastPaint >= STREAM_PAINT_INTERVAL_MS || shown >= target.length) {
        lastPaint = now;
        paint();
      }
    }
    if (shown < target.length) frame = requestAnimationFrame(tick);
    else carry = 0;
  };

  return {
    /** 传入累计文本，而不是单次增量。 */
    push(text: string) {
      if (disposed || !isActive()) return;
      target = text;
      if (shown > target.length) shown = target.length;
      if (reduced) {
        shown = target.length;
        onUpdate(target);
        return;
      }
      if (shown < target.length && frame === null) frame = requestAnimationFrame(tick);
    },
    /** 立即显示到权威全文并停止。 */
    flush(text?: string) {
      if (disposed) return;
      if (text !== undefined) target = text;
      shown = target.length;
      carry = 0;
      stop();
      if (isActive() && target) onUpdate(target);
    },
    /** 丢弃动画，不写回状态。 */
    dispose() {
      disposed = true;
      stop();
    },
  };
}

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
