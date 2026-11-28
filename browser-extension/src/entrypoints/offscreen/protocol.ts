export const OFFSCREEN_AUDIO_TARGET = 'unimind-offscreen-audio';
export const OFFSCREEN_CLOCK_TARGET = 'unimind-offscreen-clock';
export const OFFSCREEN_STATE_TARGET = 'unimind-offscreen-state';

export interface PlaybackClock {
  video_key: string;
  video_seconds: number;
  paused: boolean;
}

export type AudioDocumentMessage = {
  target: typeof OFFSCREEN_AUDIO_TARGET;
  action: 'start' | 'stop' | 'export';
  tabId: number;
  streamId?: string;
  snapshot?: PlaybackClock;
};

export interface AudioDocumentResponse {
  enabled: boolean;
  error?: string;
  audioBase64?: string;
  clipStartSeconds?: number;
}
