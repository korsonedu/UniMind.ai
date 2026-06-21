import { create } from 'zustand';
import api from '@/lib/api';

export interface OutlineItem {
  title: string;
  timestamp: number;
  description: string;
  index: number;
}

export interface TranscriptSegment {
  start: number;
  end: number;
  text: string;
  index: number;
}

interface CourseAIState {
  outlineStatus: 'idle' | 'loading' | 'available' | 'unavailable';
  outlineItems: OutlineItem[];
  transcriptStatus: 'idle' | 'loading' | 'available' | 'unavailable';
  transcriptSegments: TranscriptSegment[];
  fullText: string | null;
  fetchOutline: (courseId: number) => Promise<void>;
  triggerOutlineGeneration: (courseId: number) => Promise<void>;
  fetchTranscript: (courseId: number) => Promise<void>;
  triggerTranscription: (courseId: number) => Promise<void>;
  reset: () => void;
  /** 清除指定课程的轮询定时器（组件卸载时调用） */
  clearCourseTimers: (courseId: number) => void;
  /** 清除全部轮询定时器（仅应用级清理） */
  clearAllTimers: () => void;
}

const POLL_INTERVAL = 5000;
const _pollTimers = new Map<string, ReturnType<typeof setInterval>>();

export const useCourseAIStore = create<CourseAIState>((set, get) => ({
  outlineStatus: 'idle',
  outlineItems: [],
  transcriptStatus: 'idle',
  transcriptSegments: [],
  fullText: null,

  fetchOutline: async (courseId) => {
    const key = `outline_${courseId}`;
    // Clear any existing poll for this outline
    const timers = _pollTimers;
    if (timers.has(key)) {
      clearInterval(timers.get(key));
      timers.delete(key);
    }

    set({ outlineStatus: 'loading' });
    try {
      const res = await api.get(`/courses/${courseId}/outline/`);
      if (res.data.status === 'completed') {
        set({ outlineItems: res.data.items || [], outlineStatus: 'available' });
      } else if (res.data.status === 'not_available') {
        set({ outlineStatus: 'unavailable' });
      } else {
        // Still processing — keep loading and start polling
        set({ outlineStatus: 'loading' });
        const timer = setInterval(async () => {
          try {
            const pollRes = await api.get(`/courses/${courseId}/outline/`);
            if (pollRes.data.status === 'completed') {
              clearInterval(timer);
              _pollTimers.delete(key);
              set({ outlineItems: pollRes.data.items || [], outlineStatus: 'available' });
            } else if (pollRes.data.status === 'failed') {
              clearInterval(timer);
              _pollTimers.delete(key);
              set({ outlineStatus: 'unavailable' });
            }
          } catch {
            console.error('Outline poll failed');
            clearInterval(timer);
            _pollTimers.delete(key);
            set({ outlineStatus: 'unavailable' });
          }
        }, POLL_INTERVAL);
        _pollTimers.set(key, timer);
      }
    } catch {
      console.error('Fetch outline failed');
      set({ outlineStatus: 'unavailable' });
    }
  },

  triggerOutlineGeneration: async (courseId) => {
    set({ outlineStatus: 'loading' });
    try {
      await api.post(`/courses/${courseId}/outline/`);
      // 等后端启动后开始轮询
      setTimeout(() => get().fetchOutline(courseId), 2000);
    } catch {
      console.error('Trigger outline generation failed');
      set({ outlineStatus: 'unavailable' });
    }
  },

  fetchTranscript: async (courseId) => {
    const key = `transcript_${courseId}`;
    const timers = _pollTimers;
    if (timers.has(key)) {
      clearInterval(timers.get(key));
      timers.delete(key);
    }

    set({ transcriptStatus: 'loading' });
    try {
      const res = await api.get(`/courses/${courseId}/transcript/`);
      if (res.data.status === 'completed') {
        const segments = (res.data.segments || []).map((s: any) => ({
          start: s.start_time ?? s.start ?? 0,
          end: s.end_time ?? s.end ?? 0,
          text: s.text ?? '',
          index: s.index ?? 0,
        }));
        set({
          transcriptSegments: segments,
          fullText: res.data.full_text,
          transcriptStatus: 'available',
        });
      } else if (res.data.status === 'not_available') {
        set({ transcriptStatus: 'unavailable' });
      } else {
        // Still processing — keep loading and start polling
        set({ transcriptStatus: 'loading' });
        const timer = setInterval(async () => {
          try {
            const pollRes = await api.get(`/courses/${courseId}/transcript/`);
            if (pollRes.data.status === 'completed') {
              clearInterval(timer);
              _pollTimers.delete(key);
              const pollSegments = (pollRes.data.segments || []).map((s: any) => ({
                start: s.start_time ?? s.start ?? 0,
                end: s.end_time ?? s.end ?? 0,
                text: s.text ?? '',
                index: s.index ?? 0,
              }));
              set({
                transcriptSegments: pollSegments,
                fullText: pollRes.data.full_text,
                transcriptStatus: 'available',
              });
            } else if (pollRes.data.status === 'failed') {
              clearInterval(timer);
              _pollTimers.delete(key);
              set({ transcriptStatus: 'unavailable' });
            }
          } catch {
            console.error('Transcript poll failed');
            clearInterval(timer);
            _pollTimers.delete(key);
            set({ transcriptStatus: 'unavailable' });
          }
        }, POLL_INTERVAL);
        _pollTimers.set(key, timer);
      }
    } catch {
      console.error('Fetch transcript failed');
      set({ transcriptStatus: 'unavailable' });
    }
  },

  triggerTranscription: async (courseId) => {
    set({ transcriptStatus: 'loading' });
    try {
      await api.post(`/courses/${courseId}/transcript/`);
      // 等后端启动后开始轮询
      setTimeout(() => get().fetchTranscript(courseId), 2000);
    } catch {
      console.error('Trigger transcription failed');
      set({ transcriptStatus: 'unavailable' });
    }
  },

  reset: () => {
    set({
      outlineStatus: 'idle',
      outlineItems: [],
      transcriptStatus: 'idle',
      transcriptSegments: [],
      fullText: null,
    });
  },

  /** Clear poll timers for a specific course */
  clearCourseTimers: (courseId: number) => {
    const outlineKey = `outline_${courseId}`;
    const transcriptKey = `transcript_${courseId}`;
    for (const key of [outlineKey, transcriptKey]) {
      const timer = _pollTimers.get(key);
      if (timer) {
        clearInterval(timer);
        _pollTimers.delete(key);
      }
    }
  },

  /** Clear all poll timers — call on app-level cleanup only, not per-course unmount */
  clearAllTimers: () => {
    _pollTimers.forEach((timer) => clearInterval(timer));
    _pollTimers.clear();
  },
}));
