import { t, useLocale } from '@/i18n';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useSavedCourses } from '@/hooks/useSavedCourses';
import { useInstitutionStore } from '@/store/useInstitutionStore';

export function SavableCourseLink({ to, courseId, title, children }: { to: string; courseId: number; title?: string; children: ReactNode }) {
  useLocale();
  const personal = useInstitutionStore(state => !state.loading && !state.hasCourseCatalog && state.hasFeature('course.video'));
  const { courses, isPending, isError, refetch, update } = useSavedCourses(personal);
  const saved = courses.some(course => course.id === courseId);
  if (!personal) return <Link to={to} title={title}>{children}</Link>;
  return <span className="inline-flex max-w-full flex-wrap items-center gap-3 rounded-md border border-border px-3 py-2 my-1 text-sm">
    <Link to={to} title={title}>{children}</Link>
    <button type="button" className="text-xs text-muted-foreground hover:text-foreground" disabled={isPending || update.isPending || saved} onClick={() => { if (isError) void refetch(); else update.mutate({ id: courseId, remove: false }); }}>{isError ? t('重试保存状态') : saved ? t('已保存') : update.isPending ? t('保存中…') : t('保存课程')}</button>
  </span>;
}
