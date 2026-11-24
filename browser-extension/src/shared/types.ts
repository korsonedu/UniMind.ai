export type VideoPlatform = 'bilibili' | 'youtube' | 'generic';

export type TranscriptSource =
  | 'platform_cc'
  | 'platform_ai_subtitle'
  | 'dash_range_asr'
  | 'tab_capture_asr'
  | 'none';

export interface TranscriptSegmentItem {
  start_time: number;
  end_time: number;
  text: string;
}

export interface VisualFrameSnapshot {
  video_seconds: number;
  image: string;
}

export interface VideoVisualPayload {
  current: VisualFrameSnapshot;
  previous?: VisualFrameSnapshot;
}

export interface DashAudioTrackMeta {
  url: string;
  backupUrls?: string[];
  bandwidth?: number;
  mimeType?: string;
  codecs?: string;
  initRange?: string;
  indexRange?: string;
  referer?: string;
}

export interface ActiveVideoDescriptor {
  platform: VideoPlatform;
  external_id: string;
  part: number;
  video_key: string;
  url: string;
  title: string;
  duration?: number;
  has_native_subtitle?: boolean;
}

export interface ExternalVideoContextPayload {
  platform: VideoPlatform;
  external_id: string;
  part: number;
  url: string;
  title: string;
  video_seconds: number;
  transcript_source: TranscriptSource;
  segments: TranscriptSegmentItem[];
  visual?: VideoVisualPayload;
  integration_hooks: {
    knowledge_tree_id: number | string | null;
    knowledge_node_id: number | string | null;
    memory_event_target: string | null;
  };
}

export interface VideoRectInfo {
  x: number;
  y: number;
  width: number;
  height: number;
  devicePixelRatio: number;
  viewportWidth: number;
  viewportHeight: number;
}

export interface PageCollectSnapshot {
  descriptor: ActiveVideoDescriptor;
  video_seconds: number;
  paused: boolean;
  transcript_source: TranscriptSource;
  segments: TranscriptSegmentItem[];
  dash_audio?: DashAudioTrackMeta | null;
  direct_visual?: VideoVisualPayload | null;
  cors_fallback_rect?: VideoRectInfo | null;
  previous_frame?: VisualFrameSnapshot | null;
}

export interface CaptureContextResult {
  ok: boolean;
  context: ExternalVideoContextPayload | null;
  descriptor: ActiveVideoDescriptor | null;
  warnings: string[];
}
