import { t, useLocale } from '@/i18n';
import { Navigate, useParams, useSearchParams } from 'react-router-dom';
import { WorkspaceToolbar } from '@/components/WorkspaceToolbar';
import { WorkspaceTrail } from '@/components/WorkspaceTrail';
import { useSavedCourses } from '@/hooks/useSavedCourses';
import { learningUrl } from '@/lib/projectLearning';
import { VideoLesson } from '@/pages/VideoLesson';

export function SavedCourses() {
  useLocale();
  const { id } = useParams();
  const [params] = useSearchParams();
  const { courses, isPending, isError, refetch, update } = useSavedCourses(!!id);
  const path = (url: string) => learningUrl(url, Number(params.get('project')) || null, params.get('conversation') || undefined);
  if (!id) return <Navigate replace to={path('/xiaoyu?panel=saved-courses')} />;
  const selected = courses.find(course => course.id === Number(id));
  return <section className="um-course-main flex-1 min-w-0 h-full" aria-label={t('已保存课程')}>
    <WorkspaceToolbar className="um-course-header"><WorkspaceTrail title={id ? selected?.title || t('课程') : t('已保存课程')} crumbs={[{ label: t('小宇'), to: path('/xiaoyu') }, ...(id ? [{ label: t('已保存课程'), to: path('/courses') }] : [])]} /></WorkspaceToolbar>
    <div className="um-course-main-scroll">
      <div className="um-course-detail-player"><VideoLesson isFavorite={!!selected} favoritePending={isPending || isError || update.isPending} onFavoriteChange={() => update.mutate({ id: Number(id), remove: !!selected })} />{isError && <p role="alert" className="p-4">{t('保存状态加载失败，')}<button className="um-course-text-button" onClick={() => void refetch()}>{t('重试')}</button></p>}</div>
    </div>
  </section>;
}
