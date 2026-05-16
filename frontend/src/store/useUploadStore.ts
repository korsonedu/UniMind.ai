import { create } from 'zustand';

export interface UploadTask {
  id: string;
  fileName: string;
  progress: number; // 0-100
  status: 'uploading' | 'processing' | 'completed' | 'failed' | 'cancelled';
  error?: string;
  controller: AbortController;
}

interface UploadState {
  tasks: UploadTask[];
  addTask: (task: UploadTask) => void;
  updateProgress: (id: string, progress: number) => void;
  setStatus: (id: string, status: UploadTask['status'], error?: string) => void;
  cancelTask: (id: string) => void;
  removeTask: (id: string) => void;
}

export const useUploadStore = create<UploadState>((set, get) => ({
  tasks: [],

  addTask: (task) =>
    set((s) => ({ tasks: [...s.tasks, task] })),

  updateProgress: (id, progress) =>
    set((s) => ({
      tasks: s.tasks.map((t) => (t.id === id ? { ...t, progress } : t)),
    })),

  setStatus: (id, status, error) =>
    set((s) => ({
      tasks: s.tasks.map((t) => (t.id === id ? { ...t, status, error } : t)),
    })),

  cancelTask: (id) => {
    const task = get().tasks.find((t) => t.id === id);
    if (task) task.controller.abort();
    set((s) => ({
      tasks: s.tasks.map((t) =>
        t.id === id ? { ...t, status: 'cancelled' as const } : t,
      ),
    }));
  },

  removeTask: (id) =>
    set((s) => ({ tasks: s.tasks.filter((t) => t.id !== id) })),
}));
