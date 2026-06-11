import React, { useState, useEffect, useRef } from 'react';
import { Check, Spinner, Circle } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';
import type { AgentStep } from '@/hooks/useAgentChat';

/** 计时器：step 从 calling 开始计时，done 后停止。 */
function useElapsed(status: string) {
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef<number>(0);
  const timerRef = useRef<ReturnType<typeof setInterval>>(undefined);

  useEffect(() => {
    if (status === 'calling') {
      startRef.current = Date.now();
      timerRef.current = setInterval(() => setElapsed(Math.floor((Date.now() - startRef.current) / 1000)), 1000);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [status]);

  return elapsed;
}

export const AgentStepCard: React.FC<{ step: AgentStep; compact?: boolean }> = React.memo(({ step, compact = false }) => {
  const elapsed = useElapsed(step.status);

  const icon = step.status === 'done' ? (
    <Check className={cn(compact ? "h-3 w-3" : "h-3.5 w-3.5", "text-emerald-500 animate-in zoom-in duration-300")} />
  ) : step.status === 'calling' ? (
    <Spinner className={cn(compact ? "h-3 w-3" : "h-3.5 w-3.5", "animate-spin text-primary")} />
  ) : (
    <Circle className={cn(compact ? "h-3 w-3" : "h-3.5 w-3.5", "text-muted-foreground/40")} />
  );

  return (
    <div className={cn(
      "rounded-lg border transition-all duration-300",
      compact ? "text-[11px]" : "text-[13px]",
      step.status === 'calling'
        ? "border-primary/25 bg-primary/[0.04] shadow-[0_0_0_1px] shadow-primary/10 [animation:gentle-breathe_3s_ease-in-out_infinite]"
        : step.status === 'done'
          ? "border-emerald-500/20 bg-emerald-500/[0.04]"
          : "border-border/60 bg-muted/30"
    )}>
      <div className={cn(
        "flex items-center gap-2",
        compact ? "px-2.5 py-1.5" : "px-3 py-2",
      )}>
        {icon}
        <span className="flex-1 font-medium text-foreground">{step.label}</span>
        {step.status === 'calling' && elapsed >= 3 && (
          <span className="text-[10px] text-muted-foreground/60 font-normal tabular-nums">
            {elapsed >= 60 ? `${Math.floor(elapsed / 60)}m${elapsed % 60}s` : `${elapsed}s`}
          </span>
        )}
        {step.status === 'done' && step.result_summary && (
          <span className="text-[10px] text-muted-foreground/50 font-normal truncate max-w-[120px]">
            {step.result_summary}
          </span>
        )}
      </div>
    </div>
  );
});

/** 独立工具步骤气泡 — 与 ChatBubble 同布局，内嵌 AgentStepCard。 */
export const ToolStepMessage: React.FC<{
  step: AgentStep;
  index?: number;
  botGradient?: string;
}> = ({ step, index = 0, botGradient = 'from-amber-500 to-orange-500' }) => (
  <div
    className="flex gap-0 w-full animate-in fade-in slide-in-from-bottom-1 duration-300"
    style={{ animationDelay: `${Math.min(index * 40, 200)}ms` }}
  >
    <div className="flex flex-col max-w-[85%] items-start">
      <AgentStepCard step={step} compact />
    </div>
  </div>
);
