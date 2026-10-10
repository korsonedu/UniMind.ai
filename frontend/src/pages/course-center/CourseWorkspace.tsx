import { useEffect, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { List, X } from '@phosphor-icons/react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useAuthStore } from '@/store/useAuthStore';
import api from '@/lib/api';
import { VideoLesson } from '@/pages/VideoLesson';
import { CourseTree } from './CourseTree';
import { CoursePortal } from './CoursePortal';
import { courseGroups, matchesSearch, type Course, type CourseGrouping, type CourseProgress, type LearningActivity, type WatchLater } from './types';

type ApiCourse = Omit<Course, 'tags'> & { album?: { id: number; name: string }; knowledge_point?: number; tags?: (string | { name: string })[] };
type KnowledgePoint = { id: number; name: string; parent: number | null; children?: KnowledgePoint[] };

export function CourseCenter() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const user = useAuthStore(s => s.user);
  const [courses, setCourses] = useState<Course[]>([]);
  const [kps, setKps] = useState<KnowledgePoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [version, setVersion] = useState(0);
  const [query, setQuery] = useState('');
  const [listOpen, setListOpen] = useState(false);
  const [progress, setProgress] = useState<CourseProgress[]>([]);
  const [progressError, setProgressError] = useState('');
  const [activity, setActivity] = useState<LearningActivity | null>(null);
  const [activityError, setActivityError] = useState('');
  const [queue, setQueue] = useState<WatchLater[]>([]);
  const [queueError, setQueueError] = useState('');
  const [queueLoading, setQueueLoading] = useState(true);
  const [queuePending, setQueuePending] = useState<number[]>([]);
  const [ordering, setOrdering] = useState('sort_order');
  const [kpId, setKpId] = useState('');
  const tags = params.getAll('tag');
  const scope = params.get('scope') || 'all';
  const status = params.get('status') || 'all';
  const filter = params.get('filter') || '';
  const grouping = (params.get('group') || 'subject') as CourseGrouping;
  const manager = user?.role === 'admin' || user?.is_institution_admin;
  const changeFacet = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    next.delete('view');
    if (key === 'scope') { next.delete('filter'); next.delete('tag'); next.delete('status'); setQuery(''); }
    if (value && value !== 'all') next.set(key, value); else next.delete(key);
    navigate(`/courses?${next}`);
  };
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    async function load() {
      try {
        const kpResponse = await api.get('/quizzes/knowledge-points/', { signal: controller.signal });
        const flatten = (items: KnowledgePoint[]): KnowledgePoint[] => items.flatMap(item => [item, ...flatten(item.children || [])]);
        const points = flatten(kpResponse.data);
        setKps(points);
        const subject = (pk?: number) => {
          let node = points.find(item => item.id === pk);
          const seen = new Set<number>();
          while (node?.parent && !seen.has(node.id)) { seen.add(node.id); node = points.find(item => item.id === node!.parent); }
          return node?.name || '';
        };
        const items: Course[] = [];
        let page = 1, totalPages = 1;
        do {
          const response = await api.get('/courses/', { params: { page, page_size: 100, ordering }, signal: controller.signal });
          const data = response.data;
          items.push(...(data.items || data).map((course: ApiCourse) => ({ ...course, description: course.description || '', tags: (course.tags || []).map(tag => typeof tag === 'string' ? tag : tag.name), album_name: course.album?.name || '', subject_name: subject(course.knowledge_point) })));
          totalPages = data.total_pages || 1; page++;
        } while (page <= totalPages && !controller.signal.aborted);
        setCourses(items); setError('');
      } catch { if (!controller.signal.aborted) setError('课程加载失败'); }
      finally { if (!controller.signal.aborted) setLoading(false); }
    }
    void load(); return () => controller.abort();
  }, [version, ordering]);
  useEffect(() => {
    const controller = new AbortController();
    api.get('/courses/learning-progress/', { signal: controller.signal }).then(r => { setProgress(r.data); setProgressError(''); }).catch(() => { if (!controller.signal.aborted) setProgressError('观看记录加载失败'); });
    api.get('/courses/learning-activity/', { signal: controller.signal }).then(r => { setActivity(r.data); setActivityError(''); }).catch(() => { if (!controller.signal.aborted) setActivityError('学习活动加载失败'); });
    setQueueLoading(true);
    api.get('/courses/watch-later/', { signal: controller.signal }).then(r => { setQueue(r.data); setQueueError(''); }).catch(() => { if (!controller.signal.aborted) setQueueError('稍后观看加载失败'); }).finally(() => { if (!controller.signal.aborted) setQueueLoading(false); });
    return () => controller.abort();
  }, [version, id]);
  const queueIds = new Set(queue.map(item => item.course));
  const byProgress = new Map(progress.map(item => [item.course, item]));
  const filtered = courses.filter(course => {
    const record = byProgress.get(course.id);
    const started = !!record && (record.last_position > 0 || record.is_finished);
    return tags.every(tag => course.tags?.includes(tag)) && (!kpId || (course as Course & { knowledge_point?: number }).knowledge_point === Number(kpId)) && (scope !== 'later' || queueIds.has(course.id)) && (scope !== 'learning' || (started && !record?.is_finished)) && (status === 'all' || (status === 'finished' ? record?.is_finished : status === 'learning' ? started && !record?.is_finished : !started));
  });
  const visible = filtered.filter(course => matchesSearch(course, query) && (!filter || courseGroups(course, grouping).includes(filter)));
  const retry = () => setVersion(value => value + 1);
  const open = (course: Course, view = 'overview') => { navigate(`/course/${course.id}${view !== 'overview' ? `?view=${view}` : ''}`); setListOpen(false); };
  const changeQueue = async (course: Course, remove: boolean) => {
    setQueuePending(values => [...values, course.id]);
    try {
      if (remove) { await api.delete(`/courses/${course.id}/watch-later/`); setQueue(values => values.filter(value => value.course !== course.id)); }
      else { const response = await api.put(`/courses/${course.id}/watch-later/`); setQueue(values => [...values.filter(value => value.course !== course.id), response.data]); }
      setQueueError('');
    } catch { setQueueError('稍后观看更新失败'); }
    finally { setQueuePending(values => values.filter(value => value !== course.id)); }
  };
  const directory = <CourseTree courses={courses} treeCourses={filtered} selectedId={id ? Number(id) : undefined} loading={loading} error={error} query={query} grouping={grouping} filter={filter} tag={tags[0] || ''} status={status} scope={scope} onQueryChange={setQuery} onFacet={changeFacet} onFilter={(value, group) => { const next = new URLSearchParams(params); next.set('group', group || grouping); next.set('filter', value); navigate(`/courses?${next}`); setListOpen(false); }} onSelect={open} onRetry={retry} onPublish={manager ? () => navigate('/courses/manage') : undefined}
    extraFilters={<><label className="sr-only" htmlFor="course-kp">知识点筛选</label><select id="course-kp" value={kpId} onChange={e => setKpId(e.target.value)}><option value="">全部知识点</option>{kps.map(kp => <option key={kp.id} value={kp.id}>{kp.name}</option>)}</select><label className="sr-only" htmlFor="course-order">课程排序</label><select id="course-order" value={ordering} onChange={e => setOrdering(e.target.value)}><option value="sort_order">默认排序</option><option value="created_at">时间正序</option><option value="-created_at">时间倒序</option></select><details className="um-course-tag-options"><summary>组合标签{tags.length ? ` · ${tags.length}` : ''}</summary>{[...new Set(courses.flatMap(course => course.tags || []))].map(tag => <label key={tag}><input type="checkbox" checked={tags.includes(tag)} onChange={e => { const next = new URLSearchParams(params); next.delete('tag'); (e.target.checked ? [...tags, tag] : tags.filter(item => item !== tag)).forEach(item => next.append('tag', item)); navigate(`/courses?${next}`); }} />{tag}</label>)}</details></>} />;
  return <div className="um-course-workspace"><aside className="um-course-context" aria-label="课程导航">{directory}</aside><section className="um-course-main" aria-label="课程功能区"><header className="um-course-header"><div className="um-course-header-title"><Dialog.Root open={listOpen} onOpenChange={setListOpen}><Dialog.Trigger asChild><button className="um-course-button um-course-list-toggle"><List size={16} />课程导航</button></Dialog.Trigger><Dialog.Portal><Dialog.Overlay className="um-course-drawer-overlay" /><Dialog.Content className="um-course-drawer"><Dialog.Title className="sr-only">课程导航</Dialog.Title><Dialog.Description className="sr-only">搜索、筛选和选择课程</Dialog.Description><Dialog.Close className="um-course-drawer-close" aria-label="关闭课程导航"><X size={16} /></Dialog.Close>{directory}</Dialog.Content></Dialog.Portal></Dialog.Root>{id ? <button className="um-course-text-button" onClick={() => navigate('/courses')}>学习门户</button> : <span>课程中心</span>}</div>{manager && <button className="um-course-text-button" onClick={() => navigate('/courses/manage')}>管理课程</button>}</header><div className="um-course-main-scroll">{id ? <div className="um-course-detail-player"><VideoLesson /></div> : loading || error ? <div className="um-course-state"><p>{loading ? '正在加载课程…' : error}</p>{error && <button className="um-course-button" onClick={retry}>重试</button>}</div> : <CoursePortal courses={visible} progress={progress} loading={false} error={progressError} activity={activity} activityError={activityError} onRetryActivity={retry} queue={queue} queueLoading={queueLoading} queueError={queueError} queuePending={queuePending} onQueueChange={changeQueue} onRetryQueue={retry} filter={[filter, ...tags, status === 'all' ? '' : status === 'finished' ? '已看完' : status === 'learning' ? '未看完' : '未开始', query].filter(Boolean).join(' / ')} onRetry={retry} onClear={() => { setQuery(''); setKpId(''); navigate('/courses'); }} onOpen={open} />}</div></section></div>;
}
