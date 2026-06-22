import React from 'react';
import { MarkdownContent } from '@/components/MarkdownContent';

interface StepSolutionPayload {
  title: string;
  steps: Array<{ text: string; latex?: string }>;
}

export const StepSolutionRenderer: React.FC<{ payload: StepSolutionPayload }> = ({ payload }) => {
  if (!Array.isArray(payload.steps)) return null;
  return (
    <div className="p-5 space-y-5">
      {payload.title && (
        <h3 className="text-[15px] font-semibold tracking-tight text-foreground">{payload.title}</h3>
      )}
      <div className="space-y-4">
        {payload.steps.map((step, i) => (
          <div key={i} className="space-y-1.5">
            <div className="flex items-baseline gap-2">
              <span className="text-[11px] font-medium text-foreground/30 tabular-nums">{String(i + 1).padStart(2, '0')}</span>
              <p className="text-[13px] text-foreground/80 leading-relaxed">{step.text}</p>
            </div>
            {step.latex && (
              <div className="ml-6 py-1.5">
                <Markdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                  {`$$${step.latex}$$`}
                </Markdown>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
