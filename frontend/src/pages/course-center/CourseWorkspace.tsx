import { t, useLocale } from '@/i18n';
import { learningUrl } from '@/lib/projectLearning';
import { SelectField, SelectOption } from '@/components/ui/select';
import { WorkspaceToolbar } from '@/components/WorkspaceToolbar';
import { RightSidebarLayoutContext } from '@/components/WorkspaceContext';
import { useContext, useEffect, useState, type CSSProperties } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { SidebarSimple, X, CaretDown, MagnifyingGlass, ListBullets } from '@phosphor-icons/react';
import { useIsMobile } from '@/lib/useIsMobile';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import api from '@/lib/api';
import { VideoLesson } from '@/pages/VideoLesson';
import { useDirectoryWidth } from '@/hooks/useDirectoryWidth';
import { DirectoryResizeHandle } from '@/components/DirectoryResizeHandle';
import { WorkspaceTrail } from '@/components/WorkspaceTrail';
import { CourseTree } from './CourseTree';
import { CoursePortal } from './CoursePortal';
import { courseGroups, type Course, type CourseGrouping, type CourseProgress, type LearningActivity, type WatchLater } from './types';

type ApiCourse = Omit<Course, 'tags'> & { album?: { id: number; name: string }; knowledge_point?: number; tags?: (string | { name: string })[] };

export function CourseCenter() {
  useLocale();
  const { id } = useParams();
  const isPhone = useIsMobile();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const projectId = Number(params.get('project')) || null;
  const conversationId = params.get('conversation') || undefined;
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [version, setVersion] = useState(0);
  const [query, setQuery] = useState('');
  const [listOpen, setListOpen] = useState(false);
  const directoryWidth = useDirectoryWidth();
  const { fullscreen: rightSidebarFullscreen, exitFullscreen } = useContext(RightSidebarLayoutContext);
  const directoryHidden = directoryWidth.collapsed || rightSidebarFullscreen;
  const [progress, setProgress] = useState<CourseProgress[]>([]);
  const [progressError, setProgressError] = useState('');
  const [activity, setActivity] = useState<LearningActivity | null>(null);
  const [activityError, setActivityError] = useState('');
  const [queue, setQueue] = useState<WatchLater[]>([]);
  const [queueError, setQueueError] = useState('');
  const [queueLoading, setQueueLoading] = useState(true);
  const [queuePending, setQueuePending] = useState<number[]>([]);
  const [ordering, setOrdering] = useState('sort_order');
  const tags = params.getAll('tag');
  const scope = params.get('scope') || 'all';
  const status = params.get('status') || 'all';
  const filter = params.get('filter') || '';
  const grouping = (params.get('group') || 'module') as CourseGrouping;
  const changeFacet = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    next.delete('view');
    if (key === 'scope') next.delete('status');
    if (value && value !== 'all') next.set(key, value); else next.delete(key);
    navigate(`/courses?${next}`);
  };
  const [loadingKey, setLoadingKey] = useState(`${version}:${ordering}`);
  if (loadingKey !== `${version}:${ordering}`) {
    setLoadingKey(`${version}:${ordering}`);
    setLoading(true);
  }

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const items: Course[] = [];
        let page = 1, totalPages = 1;
        do {
          const response = await api.get('/courses/', { params: { page, page_size: 100, ordering }, signal: controller.signal });
          const data = response.data;
          items.push(...(data.items || data).map((course: ApiCourse) => ({ ...course, description: course.description || '', tags: (course.tags || []).map(tag => typeof tag === 'string' ? tag : tag.name), album_name: course.album?.name || '' })));
          totalPages = data.total_pages || 1; page++;
        } while (page <= totalPages && !controller.signal.aborted);
        setCourses(items); setError('');
      } catch { if (!controller.signal.aborted) setError(t('课程加载失败')); }
      finally { if (!controller.signal.aborted) setLoading(false); }
    }
    void load(); return () => controller.abort();
  }, [version, ordering]);
  const [queueKey, setQueueKey] = useState(`${version}:${id}`);
  if (queueKey !== `${version}:${id}`) { setQueueKey(`${version}:${id}`); setQueueLoading(true); }
  useEffect(() => {
    const controller = new AbortController();
    api.get('/courses/learning-progress/', { signal: controller.signal }).then(r => { setProgress(r.data); setProgressError(''); }).catch(() => { if (!controller.signal.aborted) setProgressError(t('观看记录加载失败')); });
    api.get('/courses/learning-activity/', { signal: controller.signal }).then(r => { setActivity(r.data); setActivityError(''); }).catch(() => { if (!controller.signal.aborted) setActivityError(t('学习活动加载失败')); });
    api.get('/courses/watch-later/', { signal: controller.signal }).then(r => { setQueue(r.data); setQueueError(''); }).catch(() => { if (!controller.signal.aborted) setQueueError(t('稍后观看加载失败')); }).finally(() => { if (!controller.signal.aborted) setQueueLoading(false); });
    return () => controller.abort();
  }, [version, id]);
  const queueIds = new Set(queue.map(item => item.course));
  const byProgress = new Map(progress.map(item => [item.course, item]));
  const filtered = courses.filter(course => {
    const record = byProgress.get(course.id);
    const started = !!record && (record.last_position > 0 || record.is_finished);
    return tags.every(tag => course.tags?.includes(tag)) && (scope !== 'later' || queueIds.has(course.id)) && (scope !== 'learning' || (started && !record?.is_finished)) && (status === 'all' || (status === 'finished' ? record?.is_finished : status === 'learning' ? started && !record?.is_finished : !started));
  });
  const visible = filtered.filter(course => !filter || courseGroups(course, grouping).includes(filter));
  const matchingFilter = courses.find(course => courseGroups(course, grouping).includes(filter));
  const filterLabel = !filter ? '' : grouping === 'module' ? matchingFilter?.module_name || t('待归类') : grouping === 'album' ? matchingFilter?.album_name || t('专辑') : filter;
  const selectedCourse = id ? courses.find(course => course.id === Number(id)) : undefined;
  const retry = () => setVersion(value => value + 1);
  const resetFilters = () => { setOrdering('sort_order'); navigate(learningUrl('/courses', projectId, conversationId)); };
  const open = (course: Course, view = 'overview') => { navigate(learningUrl(`/course/${course.id}${view !== 'overview' ? `?view=${view}` : ''}`, projectId, conversationId)); setListOpen(false); };
  const changeQueue = async (course: Course, remove: boolean) => {
    setQueuePending(values => [...values, course.id]);
    try {
      if (remove) { await api.delete(`/courses/${course.id}/watch-later/`); setQueue(values => values.filter(value => value.course !== course.id)); }
      else { const response = await api.put(`/courses/${course.id}/watch-later/`); setQueue(values => [...values.filter(value => value.course !== course.id), response.data]); }
      setQueueError('');
    } catch { setQueueError(t('稍后观看更新失败')); }
    finally { setQueuePending(values => values.filter(value => value !== course.id)); }
  };
  const directory = <CourseTree courses={courses} treeCourses={visible} selectedId={id ? Number(id) : undefined} loading={loading} error={error} query={query} grouping={grouping} filter={filter} tag={tags[0] || ''} status={status} scope={scope} filtersActive={!!(tags.length || filter || status !== 'all' || scope !== 'all' || ordering !== 'sort_order')} onResetFilters={resetFilters} onQueryChange={setQuery} onFacet={changeFacet} onFilter={(value, group) => { const next = new URLSearchParams(params); next.set('group', group || grouping); next.set('filter', value); navigate(`/courses?${next}`); setListOpen(false); }} onSelect={open} onRetry={retry}
    extraFilters={<label>{t('课程排序')}<SelectField value={ordering} onValueChange={value => setOrdering(value)}><SelectOption value="sort_order">{t('默认排序')}</SelectOption><SelectOption value="created_at">{t('时间正序')}</SelectOption><SelectOption value="-created_at">{t('时间倒序')}</SelectOption></SelectField></label>} />;
  const directoryDrawer = (
    <Dialog.Root open={listOpen} onOpenChange={setListOpen}>
      {!isPhone && (
        <Dialog.Trigger asChild>
          <button className="um-course-button um-course-list-toggle" aria-label={t('课程导航')}><SidebarSimple size={16} />{t('课程导航')}</button>
        </Dialog.Trigger>
      )}
      <Dialog.Portal>
        <Dialog.Overlay className="um-course-drawer-overlay" />
        <Dialog.Content className="um-course-drawer">
          <Dialog.Title className="sr-only">{t('课程导航')}</Dialog.Title>
          <Dialog.Description className="sr-only">{t('搜索、筛选和选择课程')}</Dialog.Description>
          <Dialog.Close className="um-course-drawer-close" aria-label={t('关闭课程导航')}><X size={17} /></Dialog.Close>
          {directory}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
  return <div className="um-course-workspace" data-directory-animated={directoryWidth.animated || undefined} style={{ '--um-directory-width': `${directoryWidth.width}px`, '--um-directory-content-width': `${directoryWidth.contentWidth}px` } as CSSProperties}><aside className="um-course-context" aria-label={t('课程导航')}><div className="um-course-directory-content um-directory-content" aria-hidden={directoryWidth.collapsed || undefined} inert={directoryWidth.collapsed}>{directory}</div><DirectoryResizeHandle width={directoryWidth.width} onChange={directoryWidth.previewWidth} onCommit={directoryWidth.changeWidth} label={t('调整课程导航宽度')} /></aside><section className="um-course-main" aria-label={t('课程功能区')}><WorkspaceToolbar className={`um-course-header${isPhone ? ' um-course-phone-header' : ''}`}><div className="um-course-header-title">
    {isPhone ? (
      id ? (
        <>
          <span className="um-m-lesson-toolbar-title">{selectedCourse?.title || t('课程')}</span>
          <button type="button" className="um-agent-icon-button um-course-phone-action" aria-label={t('课程导航')} onClick={() => setListOpen(true)}><ListBullets size={18} /></button>
        </>
      ) : (
        <>
          <button type="button" className="um-mobile-header-title um-m-header-switcher um-course-phone-switcher" aria-label={t('课程导航')} onClick={() => setListOpen(true)}>
            <span>{filterLabel || t('课程')}</span>
            <CaretDown size={13} weight="regular" className="um-m-header-caret" />
          </button>
          <button type="button" className="um-agent-icon-button um-course-phone-action" aria-label={t('搜索课程')} onClick={() => setListOpen(true)}><MagnifyingGlass size={18} /></button>
        </>
      )
    ) : (
      <>
        <button className="um-course-directory-toggle" onClick={() => {
          if (rightSidebarFullscreen) {
            exitFullscreen();
            if (directoryWidth.collapsed) directoryWidth.expand();
          } else directoryWidth.toggle();
        }} aria-label={directoryHidden ? t('展开课程导航') : t('收起课程导航')} title={directoryHidden ? t('展开课程导航') : t('收起课程导航')} aria-expanded={!directoryHidden}><SidebarSimple size={18} /></button>
        <WorkspaceTrail title={id ? selectedCourse?.title || t('课程') : t('学习门户')} crumbs={[{ label: t('课程'), to: learningUrl('/courses', projectId, conversationId) }, ...(id ? [selectedCourse?.subject_name, selectedCourse?.module_name].filter(Boolean).map(label => ({ label: label! })) : [])]} />
      </>
    )}
    {directoryDrawer}
  </div></WorkspaceToolbar><div className="um-course-main-scroll">{id ? <div className="um-course-detail-player"><VideoLesson key={id} isFavorite={!!selectedCourse && queueIds.has(selectedCourse.id)} favoritePending={queueLoading || !selectedCourse || queuePending.includes(selectedCourse.id)} onFavoriteChange={selectedCourse ? () => { void changeQueue(selectedCourse, queueIds.has(selectedCourse.id)); } : undefined} /></div> : loading || error ? <div className="um-course-state"><p>{loading ? t('正在加载课程…') : error}</p>{error && <button className="um-course-button" onClick={retry}>{t('重试')}</button>}</div> : <CoursePortal courses={visible} progress={progress} loading={false} error={progressError} activity={activity} activityError={activityError} onRetryActivity={retry} queue={queue} queueLoading={queueLoading} queueError={queueError} queuePending={queuePending} onQueueChange={changeQueue} onRetryQueue={retry} filter={[filterLabel, ...tags, status === 'all' ? '' : status === 'finished' ? t('已看完') : status === 'learning' ? t('未看完') : t('未开始')].filter(Boolean).join(' / ')} onRetry={retry} onClear={resetFilters} onOpen={open} />}</div></section></div>;
}
