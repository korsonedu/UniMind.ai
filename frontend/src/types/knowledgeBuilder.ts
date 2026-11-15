export type BuildArchetype =
  | 'auto'
  | 'institution_mechanism_theory'
  | 'formula_derivation_chain'
  | 'taskflow_diagnostic_tree'
  | 'case_synthesis_deduction';

export type BuildStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';

export interface BuildStats {
  atom_count?: number;
  atom_edge_count?: number;
  block_count?: number;
  module_count?: number;
  layer_count?: number;
  step_count?: number;
  interface_count?: number;
  [key: string]: number | string | undefined;
}

export interface BuildSummary {
  id: string;
  subject: string;
  status: BuildStatus;
  current_stage: string;
  archetype: string;
  dispatch_profile: Record<string, unknown>;
  stats: BuildStats;
  error_message: string;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface TreeModule {
  id: number;
  parent: number | null;
  code: string;
  title: string;
  path: string;
  depth: number;
  order: number;
}

export interface TreeAtomPoint {
  id: number;
  module: number;
  code: string;
  name: string;
  goal_statement: string;
  parent_path: string;
  goal_type: string;
  granularity_minutes: number;
  cognitive_level: string;
  key_elements: string[];
  prerequisites_hint: string[];
  common_misconceptions: string[];
  branch_condition: string;
  order: number;
}

export interface TreeAtomEdge {
  id: number;
  from_atom: number;
  to_atom: number;
  edge_strength: 'strong' | 'weak' | 'contrast' | 'bidirectional';
  relation_label: string;
  rationale: string;
  confidence: number;
  similarity: number;
}

export interface BlockIntraLine {
  from_atom_code: string;
  to_atom_code: string;
  kind: 'progression' | 'contrast';
  reason: string;
}

export interface BlockStepAtom {
  atom: number;
  membership_type: 'core' | 'extension';
  position: number;
}

export interface BlockStep {
  id: number;
  step_index: number;
  step_title: string;
  step_role: string;
  branch_condition: string;
  intra_lines: BlockIntraLine[];
  step_atoms: BlockStepAtom[];
}

export interface BlockNodeShape {
  entry?: boolean;
  overview?: boolean;
  merge?: boolean;
  start?: boolean;
  end?: boolean;
  [key: string]: boolean | undefined;
}

export interface LearningBlock {
  id: number;
  code: string;
  short_title: string;
  narrative_summary: string;
  layer: number;
  contraction_group: string;
  is_entry_block: boolean;
  node_shape: BlockNodeShape;
  order: number;
  steps: BlockStep[];
}

export interface BlockEdge {
  id: number;
  from_block: number;
  to_block: number;
  edge_kind: 'unidirectional' | 'bidirectional';
  directness_score: number;
  hard_constraint_count: number;
  hard_net: number;
  similarity: number;
  is_retained: boolean;
  exclusion_reason: string;
  rationale: string;
}

export interface CrossBlockInterface {
  id: number;
  block_edge: number;
  from_atom: number;
  to_atom: number;
  interface_role: string;
  bridge_explanation: string;
}

export interface KnowledgeTreeBuildDetail extends BuildSummary {
  modules: TreeModule[];
  atoms: TreeAtomPoint[];
  atom_edges: TreeAtomEdge[];
  blocks: LearningBlock[];
  block_edges: BlockEdge[];
  interfaces: CrossBlockInterface[];
}
