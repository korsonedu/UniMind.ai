import { t } from '@/i18n';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import api from '@/lib/api';
import { useAuthStore } from '@/store/useAuthStore';
import type { Course } from '@/pages/course-center/types';

export type SavedCourse = Course & { progress: { last_position: number; is_finished: boolean } | null };

export function useSavedCourses(enabled = true) {
  const userId = useAuthStore(state => state.user?.id);
  const client = useQueryClient();
  const queryKey = ['saved-courses', userId];
  const query = useQuery({
    queryKey, enabled: enabled && !!userId,
    queryFn: async ({ signal }) => {
      const courses: SavedCourse[] = [];
      let page = 1, totalPages = 1;
      do {
        const { data } = await api.get('/courses/', { params: { saved: 1, page, page_size: 100, ordering: '-created_at' }, signal });
        courses.push(...data.items);
        totalPages = data.total_pages; page++;
      } while (page <= totalPages);
      return courses;
    },
  });
  const update = useMutation({
    mutationFn: async ({ id, remove }: { id: number; remove: boolean }) => {
      if (remove) await api.delete(`/courses/${id}/watch-later/`);
      else await api.put(`/courses/${id}/watch-later/`);
    },
    onSuccess: async (_, { remove }) => {
      await client.invalidateQueries({ queryKey });
      toast.success(remove ? t('已移除课程') : t('已保存课程'));
    },
    onError: () => { toast.error(t('课程未更新，请重试')); },
  });
  return { ...query, courses: query.data || [], update };
}
