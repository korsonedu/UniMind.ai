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
}

export const useCourseAIStore = create<CourseAIState>((set, get) => ({
  outlineStatus: 'idle',
  outlineItems: [],
  transcriptStatus: 'idle',
  transcriptSegments: [],
  fullText: null,

  fetchOutline: async (courseId) => {
    set({ outlineStatus: 'loading' });
    try {
      const res = await api.get(`/courses/${courseId}/outline/`);
      if (res.data.status === 'completed') {
        set({ outlineItems: res.data.items || [], outlineStatus: 'available' });
      } else if (res.data.status === 'not_available') {
        set({ outlineStatus: 'unavailable' });
      } else {
        set({ outlineStatus: 'loading' });
      }
    } catch {
      set({ outlineStatus: 'unavailable' });
    }
  },

  triggerOutlineGeneration: async (courseId) => {
    set({ outlineStatus: 'loading' });
    try {
      await api.post(`/courses/${courseId}/outline/`);
    } catch {
      set({ outlineStatus: 'unavailable' });
    }
  },

  fetchTranscript: async (courseId) => {
    set({ transcriptStatus: 'loading' });
    try {
      const res = await api.get(`/courses/${courseId}/transcript/`);
      if (res.data.status === 'completed') {
        set({
          transcriptSegments: res.data.segments || [],
          fullText: res.data.full_text,
          transcriptStatus: 'available',
        });
      } else if (res.data.status === 'not_available') {
        set({ transcriptStatus: 'unavailable' });
      } else {
        set({ transcriptStatus: 'loading' });
      }
    } catch {
      set({ transcriptStatus: 'unavailable' });
    }
  },

  triggerTranscription: async (courseId) => {
    set({ transcriptStatus: 'loading' });
    try {
      await api.post(`/courses/${courseId}/transcript/`);
    } catch {
      set({ transcriptStatus: 'unavailable' });
    }
  },

  reset: () =>
    set({
      outlineStatus: 'idle',
      outlineItems: [],
      transcriptStatus: 'idle',
      transcriptSegments: [],
      fullText: null,
    }),
}));
