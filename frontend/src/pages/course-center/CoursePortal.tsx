import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, Check, Clock as Clock3, CalendarBlank as CalendarDays, Play, Plus, Trophy, X } from '@phosphor-icons/react';
import { toast } from 'sonner';
import api from '@/lib/api';
import { CheckInFireworks } from '@/components/CheckInFireworks';
import { LearningOverview, type DashData } from './LearningOverview';
import { useAuthStore } from '@/store/useAuthStore';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import { LearningCalendar } from './LearningCalendar';
import { dateOffset, learningDuration } from './learningDates';
import { LEARNING_TIME_ZONE, learningDate, playbackTime, type Course, type CourseProgress, type LearningActivity, type WatchLater } from './types';

interface PortalProps {
  courses: Course[];
  progress: CourseProgress[];
  loading: boolean;
  error: string;
  activity: LearningActivity | null;
  activityError: string;
  onRetryActivity: () => void;
  queue: WatchLater[];
  queueLoading: boolean;
  queueError: string;
  queuePending: number[];
  onQueueChange: (course: Course, remove: boolean) => void;
  onRetryQueue: () => void;
  filter: string;
  onRetry: () => void;
  onClear: () => void;
  onOpen: (course: Course, view?: 'overview' | 'video' | 'materials') => void;
}

function progressLabel(record?: CourseProgress) {
  if (!record || (!record.last_position && !record.is_finished)) return '尚未观看';
  if (record.is_finished) return '已看完';
  return record.duration > 0 ? `${Math.min(99, Math.round(record.last_position / record.duration * 100))}% · ${playbackTime(record.last_position)} / ${playbackTime(record.duration)}` : `观看至 ${playbackTime(record.last_position)}`;
}

export function CoursePortal({ courses, progress, loading, error, activity, activityError, onRetryActivity, queue, queueLoading, queueError, queuePending, onQueueChange, onRetryQueue, filter, onRetry, onClear, onOpen }: PortalProps) {
  const name = useAuthStore(state => state.user?.nickname || state.user?.username || '同学');
  const features = useInstitutionStore(state => state.features);
  const hasReport = features.includes('full.report');
  const [now, setNow] = useState(() => new Date());
  const [tab, setTab] = useState('unfinished');
  const [dash, setDash] = useState<DashData | null>(null);
  const [dashError, setDashError] = useState(false);
  const [checkingIn, setCheckingIn] = useState(false);
  const [checkInBurst, setCheckInBurst] = useState(0);
  const [dashboardVersion, setDashboardVersion] = useState(0);
  useEffect(() => {
    if (!hasReport) { setDash(null); setDashError(false); return; }
    const controller = new AbortController();
    api.get<DashData>('/ai/dashboard/', { signal: controller.signal })
      .then(response => { setDash(response.data); setDashError(false); })
      .catch(() => { if (!controller.signal.aborted) setDashError(true); });
    return () => controller.abort();
  }, [dashboardVersion, hasReport]);
  const handleCheckIn = async () => {
    if (checkingIn || !dash || dashError || dash.stats.today_checked_in) return;
    setCheckingIn(true);
    try {
      const response = await api.post<{ created: boolean }>('/users/me/checkin/');
      if (response.data.created) { setCheckInBurst(value => value + 1); toast.success('今日打卡成功'); }
      setDash(previous => previous ? { ...previous, stats: { ...previous.stats, today_checked_in: true } } : previous);
      setDashboardVersion(value => value + 1);
    } catch { toast.error('打卡失败，请重试'); }
    finally { setCheckingIn(false); }
  };
  useEffect(() => { const timer = window.setInterval(() => setNow(new Date()), 60000); return () => window.clearInterval(timer); }, []);
  const today = learningDate(now);
  const hour = Number(new Intl.DateTimeFormat('en-GB', { timeZone: LEARNING_TIME_ZONE, hour: 'numeric', hourCycle: 'h23' }).format(now));
  const greeting = hour < 6 ? '夜深了' : hour < 12 ? '早上好' : hour < 18 ? '下午好' : '晚上好';
  const byCourse = new Map(courses.map(course => [course.id, course]));
  const byProgress = new Map(progress.map(record => [record.course, record]));
  const videoCourses = courses.filter(course => course.video_file);
  const recent = progress.filter(record => byCourse.get(record.course)?.video_file && (record.last_position > 0 || record.is_finished)).sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''));
  const unfinished = recent.filter(record => !record.is_finished);
  const completed = recent.filter(record => record.is_finished);
  const lastRecord = unfinished[0] || recent[0];
  const lastCourse = lastRecord && byCourse.get(lastRecord.course);
  const queued = queue.filter(item => byCourse.get(item.course)?.video_file).map(item => byCourse.get(item.course)!);
  const queueIds = new Set(queue.map(item => item.course));
  const nextCourses = videoCourses.filter(course => !queueIds.has(course.id) && !byProgress.get(course.id)?.is_finished && !byProgress.get(course.id)?.last_position);
  const activityDays = useMemo(() => {
    const courseIds = new Set(courses.map(course => course.id));
    return activity?.days.filter(day => courseIds.has(day.course)) || [];
  }, [activity, courses]);
  const totals = activity?.totals.filter(item => byCourse.has(item.course)) || [];
  const activeDates = new Set(activityDays.filter(day => day.watched_seconds > 0 || day.completions > 0).map(day => day.date));
  const weekDays = Array.from({ length: 7 }, (_, index) => dateOffset(today, -index)).filter(date => activeDates.has(date)).length;
  let streak = 0;
  let date = activeDates.has(today) ? today : dateOffset(today, -1);
  while (activeDates.has(date)) { streak++; date = dateOffset(date, -1); }
  const seconds = totals.reduce((sum, item) => sum + item.watched_seconds, 0);
  const earned = totals.reduce((sum, item) => sum + item.elo_earned, 0);
  const recentEarned = activityDays.filter(day => day.date >= dateOffset(today, -6) && day.date <= today).reduce((sum, day) => sum + day.elo_earned, 0);
  const selectedCourses = tab === 'all' ? courses : tab === 'unfinished' ? unfinished.map(record => byCourse.get(record.course)!) : tab === 'watched' ? recent.map(record => byCourse.get(record.course)!) : queued;
  const upcoming = [...queued, ...nextCourses].filter(course => course.id !== lastCourse?.id).slice(0, 3);
  const activityUnavailable = !activity || !!activityError;
  const queueDisabled = (course: Course) => queueLoading || !!queueError || queuePending.includes(course.id);
  const queueButton = (course: Course) => <button type="button" className="um-portal-icon-button" disabled={queueDisabled(course)} aria-label={`${queueIds.has(course.id) ? '移出稍后观看' : '加入稍后观看'}：${course.title}`} title={queueIds.has(course.id) ? '移出稍后观看' : '加入稍后观看'} onClick={() => onQueueChange(course, queueIds.has(course.id))}>{queueIds.has(course.id) ? <Check size={16} /> : <Plus size={16} />}</button>;

  return <div className="um-course-content um-course-portal">
    <CheckInFireworks burst={checkInBurst} />
    <header className="um-portal-welcome"><div><h1>{greeting}，{name}</h1><time dateTime={today}>{new Intl.DateTimeFormat('zh-CN', { timeZone: LEARNING_TIME_ZONE, month: 'long', day: 'numeric', weekday: 'long' }).format(now)}</time></div>{hasReport && <div className="um-portal-checkin"><span className="um-course-muted">{dash && !dashError ? `连续打卡 ${dash.stats.checkin_streak} 天` : '每日打卡'}</span><button type="button" className="um-course-button" onClick={handleCheckIn} disabled={checkingIn || !dash || dashError || dash.stats.today_checked_in}>{checkingIn ? '打卡中…' : dash?.stats.today_checked_in ? '已打卡' : '今日打卡'}</button></div>}</header>
    {hour < 6 && <p className="mb-5 text-xs italic text-muted-foreground">明天的你委托我提醒：现在已经是明天了。</p>}
    {filter && <div className="um-portal-filter"><span>当前范围：{filter}</span><button type="button" className="um-course-text-button" onClick={onClear}>清除筛选<X size={13} /></button></div>}
    <div className="um-portal-upper">
      <section className="um-portal-card um-course-resume" aria-label="上次观看"><div className="um-portal-resume-label"><Play size={15} fill="currentColor" /><h2>{lastRecord?.is_finished ? '上次观看' : '继续学习'}</h2></div>{loading ? <p role="status" className="um-course-muted">正在读取观看记录…</p> : error ? <div><p role="alert">{error}</p><button type="button" className="um-course-button" onClick={onRetry}>重试观看记录</button></div> : lastCourse && lastRecord ? <><h3>{lastCourse.title}</h3><p className="um-course-muted">{progressLabel(lastRecord)}</p>{!lastRecord.is_finished && lastRecord.duration > 0 && <progress value={lastRecord.last_position} max={Math.max(lastRecord.duration, lastRecord.last_position)} aria-label={`${lastCourse.title}观看进度`} />}<div className="um-portal-resume-actions"><button type="button" className="um-course-button um-course-button-primary" onClick={() => onOpen(lastCourse, 'video')}><Play size={14} fill="currentColor" />{lastRecord.is_finished ? '重新观看' : '继续观看'}</button><button type="button" className="um-course-text-button" onClick={() => onOpen(lastCourse)}>课程详情<ArrowUpRight size={14} /></button></div></> : <><h3>开始学习</h3><p className="um-course-muted">暂无观看记录</p>{videoCourses[0] && <button type="button" className="um-course-button um-course-button-primary" onClick={() => onOpen(videoCourses[0], 'video')}>开始学习</button>}</>}</section>
      <section className="um-portal-card um-portal-next" aria-label="接下来做什么"><div className="um-course-section-heading"><h2>接下来做什么</h2><span className="um-course-muted">{queued.length ? '稍后观看优先' : '按课程目录'}</span></div><ul>{upcoming.map(course => <li key={course.id}><button type="button" className="um-course-course-link" onClick={() => onOpen(course, 'video')}>{course.title}</button>{queueButton(course)}</li>)}</ul>{!upcoming.length && <p className="um-course-muted">暂无待看的课程，可以从课程目录继续选择。</p>}{dash && dash.reviews.due_count > 0 && <Link className="um-portal-review" to="/tests">还有 {dash.reviews.due_count} 题待复习<ArrowUpRight size={14} /></Link>}</section>
    </div>
    <section className="um-portal-card um-portal-overview" aria-label="听课表现"><div className="um-course-section-heading"><h2>听课表现</h2></div><dl className="um-portal-metrics">
      <div><dt><CalendarDays size={16} />学习频率</dt><dd>{activityUnavailable ? '—' : weekDays}<small> / 7 天</small></dd><p>{activityUnavailable ? '—' : `连续 ${streak} 天`}</p></div>
      <div><dt><Clock3 size={16} />观看时长</dt><dd className="um-portal-duration">{activityUnavailable ? '—' : learningDuration(seconds)}</dd></div>
      <div><dt><Check size={16} />已看完</dt><dd>{loading || error ? '—' : completed.length}<small> 门</small></dd><p>{unfinished.length} 门未看完</p></div>
      <div><dt><Trophy size={16} />听课获得 ELO</dt><dd>{activityUnavailable ? '—' : `+${recentEarned}`}</dd><p>近 7 天 · 累计 +{activityUnavailable ? '—' : earned}</p></div>
    </dl></section>
    {activityError ? <section className="um-portal-card"><h2>学习活动</h2><p role="alert">{activityError}</p><button type="button" className="um-course-button" onClick={onRetryActivity}>重试学习活动</button></section> : activity ? <LearningCalendar today={today} days={activityDays} courses={courses} /> : <section className="um-portal-card"><h2>学习活动</h2><p role="status" className="um-course-muted">正在读取学习活动…</p></section>}
    <section className="um-portal-card um-portal-library" aria-label="我的课程"><div className="um-course-section-heading"><h2>我的课程</h2><div className="um-segmented" role="group" aria-label="观看分类"><button type="button" aria-pressed={tab === 'all'} onClick={() => setTab('all')}>全部 <span>{courses.length}</span></button><button type="button" aria-pressed={tab === 'unfinished'} onClick={() => setTab('unfinished')}>未看完 <span>{loading || error ? '—' : unfinished.length}</span></button><button type="button" aria-pressed={tab === 'watched'} onClick={() => setTab('watched')}>已看过 <span>{loading || error ? '—' : recent.length}</span></button><button type="button" aria-pressed={tab === 'later'} onClick={() => setTab('later')}>稍后观看 <span>{queueLoading || queueError ? '—' : queued.length}</span></button></div></div>
      {queueError && <div className="um-portal-error"><p role="alert">{queueError}</p><button type="button" className="um-course-text-button" onClick={onRetryQueue}>重试稍后观看</button></div>}
      {tab === 'later' && !queueLoading && !queueError && queued.length > 0 && <p className="mb-3 text-xs italic text-muted-foreground">薛定谔的知识：在做题之前，你既会又不会。</p>}
      {tab === 'later' && queueLoading ? <p role="status" className="um-course-muted">正在读取稍后观看…</p> : tab !== 'later' && tab !== 'all' && (loading || error) ? <p className="um-course-muted">{loading ? '正在读取观看记录…' : '重试观看记录后可查看。'}</p> : <><ul className="um-portal-video-list">{selectedCourses.map(course => <li key={course.id}><div className="um-portal-video-glyph" aria-hidden="true"><Play size={15} /></div><div className="um-portal-video-info"><button type="button" className="um-course-course-link" onClick={() => onOpen(course, course.video_file ? 'video' : 'materials')}>{course.title}</button><p>{loading || error ? '—' : progressLabel(byProgress.get(course.id))}</p><div className="um-course-material-links">{course.courseware && <a href={course.courseware} target="_blank" rel="noopener noreferrer">教学课件</a>}{course.reference_materials && <a href={course.reference_materials} target="_blank" rel="noopener noreferrer">参考资料</a>}</div></div>{tab === 'later' ? <button type="button" className="um-portal-icon-button" aria-label={`移出稍后观看：${course.title}`} disabled={queueDisabled(course)} onClick={() => onQueueChange(course, true)}><X size={15} /></button> : course.video_file ? queueButton(course) : null}<button type="button" className="um-course-button" onClick={() => onOpen(course, course.video_file ? 'video' : 'materials')}>{!course.video_file ? '资料' : byProgress.get(course.id)?.is_finished ? '重看' : '观看'}</button></li>)}</ul>{!selectedCourses.length && <p className="um-portal-empty">{tab === 'all' ? '当前范围没有课程' : tab === 'unfinished' ? '暂无未看完视频' : tab === 'watched' ? '暂无观看记录' : '暂无稍后观看'}</p>}{tab === 'later' && !queueLoading && !queueError && queue.length === 0 && <p className="text-xs italic text-muted-foreground">这里还没有“收藏了就等于学会了”的知识。</p>}</>}
    </section>
    {hasReport && <LearningOverview data={dash} error={dashError} onRetry={() => setDashboardVersion(value => value + 1)} />}
    <nav className="um-portal-tools" aria-label="学习快捷入口"><Link to="/xiaoyu">小宇 Agent<ArrowUpRight size={14} /></Link>{features.includes('quiz.exam') && <Link to="/tests">题库练习<ArrowUpRight size={14} /></Link>}{features.includes('faq.system') && <Link to="/qa">答疑中心<ArrowUpRight size={14} /></Link>}{features.includes('study.room') && <Link to="/study">自习室<ArrowUpRight size={14} /></Link>}</nav>
  </div>;
}
