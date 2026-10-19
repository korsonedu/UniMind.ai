import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type ExamActivityStatus = 'pending' | 'grading' | 'completed' | 'partial' | 'failed';

export interface ExamActivity {
  examId: number;
  status: ExamActivityStatus;
  total: number;
  graded: number;
  failed: number;
  totalScore: number | null;
  maxScore: number | null;
  href: string;
  createdAt: number;
  expiresAt: number | null;
}

interface StartExamActivity {
  examId: number;
  total: number;
  href?: string;
  status?: ExamActivityStatus;
  graded?: number;
  failed?: number;
  totalScore?: number | null;
  maxScore?: number | null;
}

interface ExamActivityState {
  activities: ExamActivity[];
  start: (activity: StartExamActivity) => void;
  update: (examId: number, patch: Partial<Omit<ExamActivity, 'examId'>>) => void;
  dismiss: (examId: number) => void;
  pruneExpired: () => void;
  clear: () => void;
}

export const isActiveExamStatus = (status: ExamActivityStatus) =>
  status === 'pending' || status === 'grading';

export const isTerminalExamStatus = (status: ExamActivityStatus) =>
  !isActiveExamStatus(status);

export const useExamActivityStore = create<ExamActivityState>()(
  persist(
    (set) => ({
      activities: [],
      start: (activity) => set((state) => {
        const next: ExamActivity = {
          examId: activity.examId,
          status: activity.status ?? 'pending',
          total: activity.total,
          graded: activity.graded ?? 0,
          failed: activity.failed ?? 0,
          totalScore: activity.totalScore ?? null,
          maxScore: activity.maxScore ?? null,
          href: activity.href ?? `/tests/results/${activity.examId}`,
          createdAt: Date.now(),
          expiresAt: isTerminalExamStatus(activity.status ?? 'pending') ? Date.now() + 20000 : null,
        };
        return {
          activities: [next, ...state.activities.filter(item => item.examId !== next.examId)],
        };
      }),
      update: (examId, patch) => set((state) => ({
        activities: state.activities.map((activity) => {
          if (activity.examId !== examId) return activity;
          const merged: ExamActivity = { ...activity, ...patch };
          if (isTerminalExamStatus(merged.status) && merged.expiresAt == null) {
            merged.expiresAt = Date.now() + 20000;
          }
          return merged;
        }),
      })),
      dismiss: (examId) => set((state) => ({
        activities: state.activities.filter(activity => activity.examId !== examId),
      })),
      pruneExpired: () => {
        const now = Date.now();
        set((state) => ({
          activities: state.activities.filter(
            activity => activity.expiresAt == null || activity.expiresAt > now,
          ),
        }));
      },
      clear: () => set({ activities: [] }),
    }),
    {
      name: 'exam-activity-storage',
      version: 1,
      partialize: (state) => ({ activities: state.activities }),
      onRehydrateStorage: () => (state) => {
        state?.pruneExpired();
      },
    },
  ),
);
