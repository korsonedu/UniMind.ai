import type { LearningTask } from '@/components/LearningTasksPanel';
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
  requirements?: Record<string, unknown>;
  id: string;
  subject: string;
  status: BuildStatus;
  can_resume?: boolean;
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

export type AtomDifficultyTier = 'L1' | 'L2' | 'L3';

export interface AtomDifficultyInfo {
  tier: AtomDifficultyTier;
  label: string;
  shortLabel: string;
}

export interface BlockDifficultySummary {
  L1: number;
  L2: number;
  L3: number;
}

export interface EnsureBlockProjectResponse {
  project_id: number;
  conversation_id: string | null;
  bot_id: number | null;
  project_name: string;
  status: 'active' | 'preparing' | 'paused' | 'completed';
  block_id: number;
  atom_id: number | null;
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
  difficulty_tier?: AtomDifficultyTier;
  difficulty_label?: string;
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
  resources?: BlockResourceItem[];
  difficulty_summary?: BlockDifficultySummary;
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
  region_pref?: 'cn' | 'intl';
  modules: TreeModule[];
  atoms: TreeAtomPoint[];
  atom_edges: TreeAtomEdge[];
  blocks: LearningBlock[];
  block_edges: BlockEdge[];
  interfaces: CrossBlockInterface[];
}

export type KnowledgeTreeBuildSummary = BuildSummary;
export type IntakeMode = 'card' | 'chat';
export interface IntakeCardOption { value: string; label: string; description: string }
export interface IntakeCard {
  id: string; dimension: 'goal' | 'scope' | 'depth' | 'prior_knowledge'; title: string; question: string;
  multi_select: boolean; options: IntakeCardOption[]; allow_custom: boolean;
}
export interface DiagnosticProbeQuestion {
  id: string; question_id: number | null; kp_id: number | null; topic: string; stem: string;
  options: { key: string; label: string }[]; correct_answer: string; explanation: string;
  source: 'question_bank' | 'ai_probe'; signed_payload: string;
}
export interface CatalogModule { code: string; name: string; level: string }
export interface CatalogEdge { source: string; target: string; edge_type: string }
export interface CatalogMatchSummary {
  matched_subject: string | null; existing_modules: CatalogModule[]; module_count: number; kp_count: number; edge_count: number;
  existing_edges: CatalogEdge[];
  assessed_kp_count: number; avg_mastery: number; mastered_topics: string[]; weak_topics: string[]; needs_diagnostic: boolean;
}
export interface BaselineSummary {
  answered_count: number; correct_count: number; accuracy: number; known_topics: string[]; gap_topics: string[];
  self_report: string; entry_strategy: string; assessed_kp_count: number; avg_mastery: number;
  mastered_topics: string[]; weak_topics: string[];
  results: { id: string; selected_answer: string; correct: boolean; correct_answer: string; explanation: string }[];
}
export interface RequirementsDraft extends Record<string, unknown> {
  learning_goal: string; recommended_archetype: BuildArchetype; scope_inclusions: string[]; scope_exclusions: string[];
  depth_preference: string; learner_background: string; baseline_summary: BaselineSummary;
  suggested_entry_topics: string[]; seed_modules: CatalogModule[]; seed_edges: CatalogEdge[];
}
export interface IntakeRequestPayload {
  subject: string; mode: IntakeMode; messages?: { role: 'user' | 'assistant'; content: string }[];
  card_answers?: Record<string, { selected: string[]; custom: string }>; self_report?: string;
  diagnostic_questions?: DiagnosticProbeQuestion[]; diagnostic_answers?: Record<string, string>;
}
export interface IntakeResponsePayload {
  subject: string; mode: IntakeMode; catalog_match: CatalogMatchSummary; needs_diagnostic: boolean;
  cards: IntakeCard[]; diagnostic_questions: DiagnosticProbeQuestion[]; assistant_reply: string;
  requirements_draft: RequirementsDraft; ready_to_build: boolean;
}

export type BlockQuizMode = 'objective' | 'challenge';
export type AssetTrack = 'spine' | 'spotlight' | 'wiki';
export type AssetSourceKind = 'course' | 'library' | 'web' | 'bilibili' | 'github' | 'wikipedia' | 'youtube' | 'marketplace';
export type PedagogicalRole = '' | 'series_episode' | 'concept_intuition' | 'core_derivation' | 'worked_example' | 'wiki_reference';

export interface PublicAssetSegment {
  index: number;
  title: string;
  url: string;
  locator: string;
  summary: string;
}

export interface PublicAssetCatalogItem {
  id: number;
  subject: string;
  title: string;
  url: string;
  source_kind: AssetSourceKind;
  asset_track: AssetTrack;
  pedagogical_role: string;
  region_scope: 'cn' | 'intl' | 'global';
  description: string;
  topic_keywords: string[];
  segments: PublicAssetSegment[];
  created_at: string;
}

export interface WikiCandidateItem {
  title: string;
  url: string;
  summary: string;
  source_kind: 'wikipedia';
  asset_track: 'wiki';
  pedagogical_role: string;
  locator: string;
  region_scope: 'cn' | 'intl' | 'global';
}

export interface TreePublicAssetsResponse {
  region_pref: 'cn' | 'intl';
  catalog_assets: PublicAssetCatalogItem[];
  marketplace_listings: { id: number; title: string; description: string; content_type: string; subject: string }[];
  albums: { id: number; name: string; description: string; course_count: number }[];
  wiki_candidates: WikiCandidateItem[];
  mounted_summary: { spine_count: number; spotlight_count: number; wiki_count: number };
}

export interface TreePublicAssetImportPayload {
  url?: string;
  title?: string;
  asset_track?: AssetTrack;
  pedagogical_role?: string;
  outline_text?: string;
  public_asset_id?: number;
  marketplace_listing_id?: number;
  album_id?: number;
  target_block_id?: number;
  target_atom_id?: number;
}

export interface BlockResourceItem {
  id: number; block: number; step: number | null; atom: number | null;
  source_kind: AssetSourceKind; title: string; url: string; excerpt: string;
  course_id: number | null; library_resource_id: number | null; created_at: string;
  asset_track?: AssetTrack; pedagogical_role?: string; locator?: string;
  region_scope?: 'cn' | 'intl' | 'global'; public_asset?: number | null; marketplace_listing_id?: number | null;
  origin?: 'auto' | 'manual';
  match_method?: string;
  match_score?: number;
  upvotes?: number;
  downvotes?: number;
  user_vote?: 1 | -1 | 0;
}
export interface BlockResourceVotePayload {
  action: 'vote';
  resource_id: number;
  vote: 1 | -1 | 0;
  dismiss?: boolean;
}
export interface TreeAutoDiscoverResponse {
  mounted_count: number;
  discovered_assets_count?: number;
  reused_concept_count?: number;
  asset_track: AssetTrack;
  mounted_summary?: { spine_count: number; spotlight_count: number; wiki_count: number };
  resources: BlockResourceItem[];
}
export interface BlockResourcePayload {
  url?: string; course_id?: number; library_resource_id?: number;
  step_id?: number | null; atom_id?: number | null; save_to_library?: boolean;
  asset_track?: AssetTrack; pedagogical_role?: string; locator?: string;
  public_asset_id?: number; marketplace_listing_id?: number;
}
export interface BlockResourceUpdatePayload {
  resource_id: number; block_id?: number; step_id?: number | null; atom_id?: number | null;
  asset_track?: AssetTrack; pedagogical_role?: string; locator?: string;
}
export interface BlockResourcesResponse {
  region_pref?: 'cn' | 'intl';
  resources: BlockResourceItem[];
  internal_candidates: (BlockResourcePayload & { source_kind: 'course' | 'library'; title: string; url: string; excerpt: string })[];
  web_candidates: { title: string; url: string; summary: string }[];
  wiki_candidates?: WikiCandidateItem[];
  catalog_candidates?: PublicAssetCatalogItem[];
}
export interface BlockAssessment {
  id: number; block_id: number; mode: BlockQuizMode; complete: boolean; passed: boolean; accuracy: number | null;
  items: { task_id: string; atom_id: number; atom_name: string; membership_type: 'core' | 'extension'; q_type: 'objective' | 'subjective'; task: LearningTask }[];
}
