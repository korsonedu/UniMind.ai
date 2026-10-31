import React from 'react';
import { MarkdownContent } from '@/components/MarkdownContent';

interface StepSolutionPayload {
  title: string;
  steps: Array<{ text: string; latex?: string }>;
}

export const StepSolutionRenderer: React.FC<{ payload: StepSolutionPayload }> = ({ payload }) => {
  if (!Array.isArray(payload.steps)) return null;
  return <div className="um-visual-steps">
    {payload.title && <h3>{payload.title}</h3>}
    <ol className="um-visual-step-list">{payload.steps.map((step, index) => <li key={index}>
      <span className="um-visual-step-number" aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
      <div><p>{step.text}</p>{step.latex && <div className="um-visual-formula"><MarkdownContent content={`$$${step.latex}$$`} /></div>}</div>
    </li>)}</ol>
  </div>;
};
