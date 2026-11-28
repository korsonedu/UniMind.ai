import { useEffect, useRef } from 'react';
import type { AgentStep } from '@/types/toolRun';

import { drawToolStepSphere, TOOL_STEP_ANIMATION_MS, type ToolStepMode } from '@/lib/toolStepSphere';

const clampProgress = (value: number) => Math.min(1, Math.max(0, value));
const shownSteps = new WeakSet<AgentStep>();

export function ToolStepSphere({ mode, step, live }: { mode: ToolStepMode; step: AgentStep; live: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const progress = useRef<number | null>(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;

    const root = document.documentElement;
    const pixels = Math.round(24 * Math.min(window.devicePixelRatio || 1, 2));
    canvas.width = canvas.height = pixels;
    const { status } = step;
    // A short tool may finish before the message queue reveals its row.
    const start = progress.current ?? (status === 'succeeded' && (!live || shownSteps.has(step)) ? 1 : 0);
    progress.current = start;
    if (status === 'succeeded') shownSteps.add(step);
    let frame = 0;
    let startedAt: number | undefined;
    const remaining = (1 - start) * TOOL_STEP_ANIMATION_MS;
    // Finish the visible motion promptly even when the tool returns early.
    const duration = status === 'succeeded' ? Math.min(remaining, 850) : remaining;
    const paint = () => {
      if (root.dataset.reduceMotion === 'true') {
        cancelAnimationFrame(frame);
        progress.current = 1;
      }
      drawToolStepSphere(ctx, pixels / 2, mode, progress.current ?? start, root.classList.contains('dark'));
    };
    const tick = (time: number) => {
      startedAt ??= time;
      progress.current = start + (1 - start) * clampProgress((time - startedAt) / duration);
      paint();
      if (progress.current < 1) frame = requestAnimationFrame(tick);
    };

    const observer = new MutationObserver(paint);
    observer.observe(root, { attributes: true, attributeFilter: ['class', 'data-reduce-motion'] });
    paint();
    if (duration > 0 && progress.current < 1 && (status === 'running' || status === 'succeeded')) {
      frame = requestAnimationFrame(tick);
    }
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [mode, step, live]);

  return <canvas ref={ref} className="um-agent-thinking-icon" data-tool-sphere={mode} aria-hidden="true" />;
}
