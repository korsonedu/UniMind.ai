import React from 'react';
import { DataCardRenderer } from './DataCardRenderer';
import { LatexRenderer } from './LatexRenderer';
import { StepSolutionRenderer } from './StepSolutionRenderer';
import { KnowledgeMapRenderer } from './KnowledgeMapRenderer';
import { ActionCardsRenderer } from './ActionCardsRenderer';

export interface VisualData {
  type: string;
  payload: Record<string, unknown>;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const RENDERERS: Record<string, React.ComponentType<{ payload: any }>> = {
  data_card: DataCardRenderer,
  latex_derivation: LatexRenderer,
  step_solution: StepSolutionRenderer,
  knowledge_map: KnowledgeMapRenderer,
  action_cards: ActionCardsRenderer,
};

export const getVisualRenderer = (type: string) => RENDERERS[type] || null;
