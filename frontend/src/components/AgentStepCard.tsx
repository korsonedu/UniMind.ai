import { t, useLocale } from '@/i18n';
import React, { useState, useEffect, useRef } from 'react';
import { Check, Spinner, Circle, X, ArrowRight } from '@phosphor-icons/react';
import { useNavigate } from 'react-router-dom';
import { cn } from '@/lib/utils';
import type { AgentStep } from '@/types/toolRun';
import { ToolStepSphere } from './ToolStepSphere';

/** 计时器：step 从 running 开始计时，进入终态后停止。 */
function useElapsed(status: string) {
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef<number>(0);
  const timerRef = useRef<ReturnType<typeof setInterval>>(undefined);

  useEffect(() => {
    if (status === 'running') {
      startRef.current = Date.now();
      timerRef.current = setInterval(() => setElapsed(Math.floor((Date.now() - startRef.current) / 1000)), 1000);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [status]);

  return elapsed;
}

export const AgentStepCard: React.FC<{ step: AgentStep; compact?: boolean; statusLine?: boolean; live?: boolean }> = React.memo(({ step, compact = false, statusLine = false, live = false }) => {
  useLocale();
  const elapsed = useElapsed(step.status);
  const navigate = useNavigate();

  const mode = /analy[sz]|weak_points|mastery|diagnos|grade/.test(step.name) ? 'analysis' : 'call';
  const icon = statusLine ? (
    <span className="um-agent-step-icon" aria-hidden="true">
      {step.status === 'failed' ? <X size={16} /> : <ToolStepSphere mode={mode} step={step} live={live} />}
    </span>
  ) : step.status === 'succeeded' ? (
    <Check className={cn(compact ? "h-3 w-3" : "h-3.5 w-3.5", "text-emerald-500 um-motion-surface animate-in fade-in duration-[180ms] ease-out")} />
  ) : step.status === 'failed' ? (
    <X className={cn(compact ? "h-3 w-3" : "h-3.5 w-3.5", "text-destructive")} />
  ) : step.status === 'running' ? (
    <Spinner className={cn(compact ? "h-3 w-3" : "h-3.5 w-3.5", "animate-spin text-primary")} />
  ) : (
    <Circle className={cn(compact ? "h-3 w-3" : "h-3.5 w-3.5", "text-muted-foreground/40")} />
  );

  return (
    <div className={statusLine ? 'um-agent-step' : cn(
      "rounded-lg border transition-all duration-[180ms]",
      compact ? "text-[11px]" : "text-[13px]",
      step.status === 'running'
        ? "border-primary/25 bg-primary/[0.04] shadow-[0_0_0_1px] shadow-primary/10 [animation:gentle-breathe_3s_ease-in-out_infinite]"
        : step.status === 'succeeded'
          ? "border-emerald-500/20 bg-emerald-500/[0.04]"
          : step.status === 'failed'
            ? "border-destructive/25 bg-destructive/[0.04]"
          : "border-border/60 bg-muted/30"
    )} data-step-status={statusLine ? step.status : undefined}>
      <div className={statusLine ? 'um-agent-step-row' : cn(
        "flex items-center gap-2",
        compact ? "px-2.5 py-1.5" : "px-3 py-2",
      )}>
        {icon}
        <span className={statusLine ? 'um-agent-step-label' : 'flex-1 font-medium text-foreground'}>{t(step.label)}</span>
        {statusLine && <span className="sr-only">{t(step.status === 'succeeded' ? '已完成' : step.status === 'failed' ? '失败' : step.status === 'running' ? '进行中' : '等待中')}</span>}
        {step.status === 'running' && elapsed >= 3 && (
          <span className="text-[10px] text-muted-foreground/60 font-normal tabular-nums">
            {elapsed >= 60 ? `${Math.floor(elapsed / 60)}m${elapsed % 60}s` : `${elapsed}s`}
          </span>
        )}
        {step.status === 'succeeded' && step.result_summary && (
          <span className={statusLine ? 'um-agent-step-detail' : 'text-[10px] text-muted-foreground/55 font-normal truncate max-w-[120px]'} title={statusLine ? step.result_summary : undefined}>
            {step.result_summary}
          </span>
        )}
        {step.status === 'failed' && step.error?.message && (
          <span className={statusLine ? 'um-agent-step-detail text-destructive' : 'text-[10px] text-destructive/80 font-normal truncate max-w-[160px]'} title={statusLine ? t(step.error.message) : undefined}>
            {t(step.error.message)}
          </span>
        )}
      </div>
      {step.status === 'succeeded' && step.actions && step.actions.length > 0 && (
        <div className={statusLine ? 'flex flex-wrap gap-1 pl-7' : 'flex flex-wrap gap-1 px-3 pb-2'}>
          {step.actions.map((a, i) => (
            <button
              key={i}
              onClick={() => navigate(a.route)}
              className="inline-flex items-center gap-1 text-[11px] font-bold text-primary/70 hover:text-primary transition-colors px-2 py-0.5 rounded-md hover:bg-primary/10"
            >
              {a.label}
              <ArrowRight className="h-3 w-3" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
});

/** 对话流中的独立工具步骤。 */
export const ToolStepMessage: React.FC<{
  step: AgentStep;
  index?: number;
  botGradient?: string;
  statusLine?: boolean;
  live?: boolean;
}> = ({ step, index = 0, statusLine, live }) => statusLine ? <AgentStepCard step={step} statusLine live={live} /> : (
  <div
    className="flex gap-0 w-full um-motion-surface animate-in fade-in duration-[180ms] ease-out"
    style={{ animationDelay: `${Math.min(index * 40, 200)}ms` }}
  >
    <div className="flex flex-col max-w-[85%] items-start">
      <AgentStepCard step={step} compact />
    </div>
  </div>
);
