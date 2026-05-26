import React, { useState } from 'react';
import { ChevronDown, Check, Loader2, Circle } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { AgentStep } from '@/hooks/useAgentChat';

interface AgentStepCardProps {
  step: AgentStep;
}

export const AgentStepCard: React.FC<AgentStepCardProps> = ({ step }) => {
  const [expanded, setExpanded] = useState(false);

  const icon = step.status === 'done' ? (
    <Check className="h-3.5 w-3.5 text-green-500" />
  ) : step.status === 'calling' ? (
    <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
  ) : (
    <Circle className="h-3.5 w-3.5 text-muted-foreground" />
  );

  const hasDetails = step.args_summary || step.result_summary;

  return (
    <div className={cn(
      "rounded-xl border text-[13px] transition-all",
      step.status === 'calling'
        ? "border-primary/30 bg-primary/5"
        : step.status === 'done'
          ? "border-green-500/20 bg-green-500/5"
          : "border-border bg-muted/50"
    )}>
      <button
        className={cn(
          "w-full flex items-center gap-2.5 px-3.5 py-2.5 text-left",
          hasDetails && "cursor-pointer hover:bg-muted/30",
        )}
        onClick={() => hasDetails && setExpanded(!expanded)}
        disabled={!hasDetails}
      >
        {icon}
        <span className="flex-1 font-medium text-foreground">{step.label}</span>
        {hasDetails && (
          <ChevronDown className={cn(
            "h-3.5 w-3.5 text-muted-foreground transition-transform",
            expanded && "rotate-180",
          )} />
        )}
      </button>

      {expanded && (
        <div className="px-3.5 pb-2.5 space-y-2 border-t border-border/50">
          {step.args_summary && (
            <div className="pt-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">参数</span>
              <pre className="mt-1 text-[12px] text-muted-foreground bg-muted rounded-lg p-2 overflow-x-auto">
                {step.args_summary}
              </pre>
            </div>
          )}
          {step.result_summary && (
            <div>
              <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">结果</span>
              <pre className="mt-1 text-[12px] text-muted-foreground bg-muted rounded-lg p-2 overflow-x-auto max-h-40 overflow-y-auto">
                {step.result_summary}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
