import { t, useLocale } from '@/i18n';
import { useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useSavedCourses } from '@/hooks/useSavedCourses';
import { learningUrl } from '@/lib/projectLearning';
import { useXiaoYuChat } from '@/pages/xiaoyu/xiaoYuChatContext';
import { playbackTime } from '@/pages/course-center/types';

export function SavedCoursesPanel() {
  useLocale();
  const { chat } = useXiaoYuChat();
  const { pathname } = useLocation();
  const { courses, isPending, isError, refetch, update } = useSavedCourses();
  useEffect(() => { void refetch(); }, [pathname, refetch]);
  return <section className="p-4 overflow-y-auto h-full" aria-label={t('已保存课程')}>
    {isPending ? <p role="status" className="um-course-muted">{t('正在加载已保存课程…')}</p> : isError ? <div role="alert"><p>{t('已保存课程加载失败')}</p><button className="um-course-button" onClick={() => void refetch()}>{t('重试')}</button></div> : !courses.length ? <p className="um-course-muted">{t('在与小宇的对话中保存课程后，可以在这里继续学习。')}</p> : <ul className="divide-y divide-border">{courses.map(course => <li key={course.id} className="py-4 first:pt-0">
      <p className="text-sm font-medium">{course.title}</p>
      <p className="um-course-muted">{[course.subject_name, course.module_name].filter(Boolean).join(' / ') || t('UniMind.ai 课程')}</p>
      <p className="um-course-muted">{course.progress?.is_finished ? t('已看完') : course.progress?.last_position ? t('观看至 {0}', { 0: playbackTime(course.progress.last_position) }) : t('尚未观看')}</p>
      <div className="flex items-center gap-4 mt-3">
        <Link className="um-course-button" to={learningUrl(`/course/${course.id}`, chat.projectId, chat.conversationId)}>{course.progress?.last_position && !course.progress.is_finished ? t('继续观看') : t('观看')}</Link>
        <button className="um-course-text-button" aria-label={t('移除课程：{0}', { 0: course.title })} disabled={update.isPending} onClick={() => update.mutate({ id: course.id, remove: true })}>{t('移除')}</button>
      </div>
    </li>)}</ul>}
  </section>;
}
