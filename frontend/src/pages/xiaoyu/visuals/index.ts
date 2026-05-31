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

const RENDERERS: Record<string, React.ComponentType<{ payload: Record<string, unknown> }>> = {
  data_card: DataCardRenderer,
  latex_derivation: LatexRenderer,
  step_solution: StepSolutionRenderer,
  knowledge_map: KnowledgeMapRenderer,
  action_cards: ActionCardsRenderer,
};

export const getVisualRenderer = (type: string) => RENDERERS[type] || null;
