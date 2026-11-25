export type ProjectSourceType = 'pdf' | 'pptx' | 'docx' | 'text' | 'web_url' | 'uploaded_media' | 'course' | 'external_video';
export type ProjectSourceStatus = 'pending' | 'processing' | 'ready' | 'failed';
export type WorkbenchAnchorType = 'page' | 'slide' | 'section' | 'timestamp';

interface ChunkLocator {
  anchor_type: WorkbenchAnchorType;
  locator_label: string;
  heading: string;
  chunk_index: number;
  page_number: number | null;
  slide_number: number | null;
  start_seconds: number | null;
  end_seconds: number | null;
}

export interface ProjectSourceChunk extends ChunkLocator {
  id: number;
  content: string;
  token_estimate: number;
  metadata: Record<string, unknown>;
}

export interface ProjectSourceSummary {
  id: string;
  project_id: number;
  source_type: ProjectSourceType;
  title: string;
  mime_type: string;
  file_size: number;
  source_url: string;
  course_id: number | null;
  companion_course_id: number | null;
  external_key: string;
  status: ProjectSourceStatus;
  error_message: string;
  is_selected: boolean;
  summary: string;
  unit_count: number;
  word_count: number;
  duration_seconds: number;
  metadata: Record<string, unknown> & {
    platform?: string;
    external_id?: string;
    part?: number;
  };
  file_preview_url: string | null;
  companion_play_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectSourceDetail extends ProjectSourceSummary {
  chunks: ProjectSourceChunk[];
}

export interface ProjectSourceCounts {
  project_id: number;
  total_count: number;
  selected_count: number;
  ready_count: number;
}

export interface ProjectSourceList extends ProjectSourceCounts {
  sources: ProjectSourceSummary[];
}

export interface WorkbenchCitation extends ChunkLocator {
  cite_key: string;
  index: number;
  source_id: string;
  source_title: string;
  source_type: ProjectSourceType;
  chunk_id: number;
  quote: string;
  companion_url: string | null;
}

export interface WorkbenchOverview {
  overview: string;
  suggested_questions: string[];
  source_signature: string;
}

export interface SourceAnchor {
  sourceId: string;
  chunkId?: number;
  chunkIndex?: number;
  pageNumber?: number | null;
  slideNumber?: number | null;
  startSeconds?: number | null;
  quote?: string;
}
