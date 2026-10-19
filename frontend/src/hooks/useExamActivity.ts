import { useEffect } from 'react';
import { useQueries } from '@tanstack/react-query';

import api from '@/lib/api';
import { queryClient } from '@/lib/queryClient';
import { queryKeys } from '@/lib/queryKeys';
import {
  isActiveExamStatus,
  useExamActivityStore,
  type ExamActivityStatus,
} from '@/store/useExamActivityStore';

interface ExamStatusResponse {
  id: number;
  status: ExamActivityStatus;
  total_questions: number;
  graded_count: number;
  failed_count: number;
  total_score: number;
  max_score: number;
  summary_text: string;
  href: string;
}

const POLL_INTERVAL = 2500;

export function useExamActivity() {
  const activities = useExamActivityStore(state => state.activities);
  const active = activities.filter(activity => isActiveExamStatus(activity.status));

  const results = useQueries({
    queries: active.map(activity => ({
      queryKey: queryKeys.exams.status(activity.examId),
      queryFn: async () => {
        const response = await api.get<ExamStatusResponse>(`/quizzes/exams/${activity.examId}/status/`);
        return response.data;
      },
      enabled: isActiveExamStatus(activity.status),
      staleTime: 0,
      retry: 2,
      refetchInterval: (query: { state: { data?: ExamStatusResponse } }) => {
        const data = query.state.data;
        return data && !isActiveExamStatus(data.status) ? false : POLL_INTERVAL;
      },
    })),
  });

  useEffect(() => {
    results.forEach((result, index) => {
      const activity = active[index];
      if (!activity) return;
      const current = useExamActivityStore.getState().activities.find(
        item => item.examId === activity.examId,
      );
      if (!current) return;

      if (result.data) {
        const data = result.data;
        const changed = current.status !== data.status
          || current.total !== data.total_questions
          || current.graded !== data.graded_count
          || current.failed !== data.failed_count
          || current.totalScore !== data.total_score
          || current.maxScore !== data.max_score;
        if (changed) {
          const wasActive = isActiveExamStatus(current.status);
          useExamActivityStore.getState().update(activity.examId, {
            status: data.status,
            total: data.total_questions,
            graded: data.graded_count,
            failed: data.failed_count,
            totalScore: data.total_score,
            maxScore: data.max_score,
            href: data.href,
          });
          if (wasActive && !isActiveExamStatus(data.status)) {
            void queryClient.invalidateQueries({ queryKey: queryKeys.notifications.unreadCount });
          }
        }
      }

      if (result.isError && (result.failureCount ?? 0) >= 2 && isActiveExamStatus(current.status)) {
        useExamActivityStore.getState().update(activity.examId, {
          status: 'failed',
          failed: current.total,
        });
      }
    });
  }, [active, results]);
}
