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

const POLL_INITIAL = 5000;
const POLL_MAX = 60000;
const _pollTimers = new Map<string, ReturnType<typeof setTimeout>>();
const _pollIntervals = new Map<string, number>();

// Reset all poll intervals when tab becomes visible
if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      _pollIntervals.clear();
    }
  });
}

export const useCourseAIStore = create<CourseAIState>((set, get) => ({
  outlineStatus: 'idle',
  outlineItems: [],
  transcriptStatus: 'idle',
  transcriptSegments: [],
  fullText: null,

  fetchOutline: async (courseId) => {
    const key = `outline_${courseId}`;
    // Clear any existing poll for this outline
    if (_pollTimers.has(key)) {
      clearTimeout(_pollTimers.get(key));
      _pollTimers.delete(key);
    }

    set({ outlineStatus: 'loading' });
    try {
      const res = await api.get(`/courses/${courseId}/outline/`);
      if (res.data.status === 'completed') {
        set({ outlineItems: res.data.items || [], outlineStatus: 'available' });
      } else if (res.data.status === 'not_available') {
        set({ outlineStatus: 'unavailable' });
      } else {
        // Still processing — keep loading and start polling with exponential backoff
        set({ outlineStatus: 'loading' });
        const doPoll = async () => {
          if (document.visibilityState === 'hidden') {
            const nextTimer = setTimeout(doPoll, _pollIntervals.get(key) || POLL_INITIAL);
            _pollTimers.set(key, nextTimer);
            return;
          }
          try {
            const pollRes = await api.get(`/courses/${courseId}/outline/`);
            if (pollRes.data.status === 'completed') {
              _pollTimers.delete(key);
              _pollIntervals.delete(key);
              set({ outlineItems: pollRes.data.items || [], outlineStatus: 'available' });
              return;
            } else if (pollRes.data.status === 'failed') {
              _pollTimers.delete(key);
              _pollIntervals.delete(key);
              set({ outlineStatus: 'unavailable' });
              return;
            }
            // Still processing — reset interval on success
            _pollIntervals.set(key, POLL_INITIAL);
          } catch {
            console.error('Outline poll failed');
            // Backoff
            const prev = _pollIntervals.get(key) || POLL_INITIAL;
            _pollIntervals.set(key, Math.min(prev * 2, POLL_MAX));
          }
          const nextTimer = setTimeout(doPoll, _pollIntervals.get(key) || POLL_INITIAL);
          _pollTimers.set(key, nextTimer);
        };
        const timer = setTimeout(doPoll, POLL_INITIAL);
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
    if (_pollTimers.has(key)) {
      clearTimeout(_pollTimers.get(key));
      _pollTimers.delete(key);
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
        // Still processing — keep loading and start polling with exponential backoff
        set({ transcriptStatus: 'loading' });
        const doPoll = async () => {
          if (document.visibilityState === 'hidden') {
            const nextTimer = setTimeout(doPoll, _pollIntervals.get(key) || POLL_INITIAL);
            _pollTimers.set(key, nextTimer);
            return;
          }
          try {
            const pollRes = await api.get(`/courses/${courseId}/transcript/`);
            if (pollRes.data.status === 'completed') {
              _pollTimers.delete(key);
              _pollIntervals.delete(key);
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
              return;
            } else if (pollRes.data.status === 'failed') {
              _pollTimers.delete(key);
              _pollIntervals.delete(key);
              set({ transcriptStatus: 'unavailable' });
              return;
            }
            // Still processing — reset interval on success
            _pollIntervals.set(key, POLL_INITIAL);
          } catch {
            console.error('Transcript poll failed');
            // Backoff
            const prev = _pollIntervals.get(key) || POLL_INITIAL;
            _pollIntervals.set(key, Math.min(prev * 2, POLL_MAX));
          }
          const nextTimer = setTimeout(doPoll, _pollIntervals.get(key) || POLL_INITIAL);
          _pollTimers.set(key, nextTimer);
        };
        const timer = setTimeout(doPoll, POLL_INITIAL);
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
        clearTimeout(timer);
        _pollTimers.delete(key);
      }
      _pollIntervals.delete(key);
    }
  },

  /** Clear all poll timers — call on app-level cleanup only, not per-course unmount */
  clearAllTimers: () => {
    _pollTimers.forEach((timer) => clearTimeout(timer));
    _pollTimers.clear();
    _pollIntervals.clear();
  },
}));
