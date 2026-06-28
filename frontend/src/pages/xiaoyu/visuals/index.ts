import React from 'react';
import { DataCardRenderer } from './DataCardRenderer';
import { LatexRenderer } from './LatexRenderer';
import { StepSolutionRenderer } from './StepSolutionRenderer';
import { KnowledgeMapRenderer } from './KnowledgeMapRenderer';
import { ActionCardsRenderer } from './ActionCardsRenderer';
import { FunctionGraphRenderer } from './FunctionGraphRenderer';
import { GradingPreviewCard } from '@/components/GradingPreviewCard';
import { StudentReportPreview } from '@/components/StudentReportPreview';

export interface VisualData {
  type: string;
  payload: Record<string, unknown>;
  priority?: 'high' | 'normal' | 'low';
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const RENDERERS: Record<string, React.ComponentType<{ payload: any }>> = {
  data_card: DataCardRenderer,
  latex_derivation: LatexRenderer,
  step_solution: StepSolutionRenderer,
  knowledge_map: KnowledgeMapRenderer,
  action_cards: ActionCardsRenderer,
  function_graph: FunctionGraphRenderer,
  grading_preview: GradingPreviewCard,
  student_report: StudentReportPreview,
};

export const getVisualRenderer = (type: string) => RENDERERS[type] || null;
