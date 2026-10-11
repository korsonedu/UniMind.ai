import { useEffect, useState, type FormEvent } from 'react';
import { PencilSimple, Plus } from '@phosphor-icons/react';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Checkbox } from '@/components/ui/checkbox';
import api from '@/lib/api';
import { formatApiErrorToast } from '@/lib/apiError';
import type { Course, CourseProgress } from './types';

interface LearningGoal {
  title: string;
  deadline: string;
  courses: number[];
  completed_courses: number;
  total_courses: number;
  progress_percent: number;
}

export function LearningGoalPanel({ courses, progress, today }: { courses: Course[]; progress: CourseProgress[]; today: string }) {
  const [goal, setGoal] = useState<LearningGoal | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [version, setVersion] = useState(0);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [title, setTitle] = useState('');
  const [deadline, setDeadline] = useState('');
  const [selected, setSelected] = useState<number[]>([]);
  const [search, setSearch] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    api.get<LearningGoal | null>('/courses/learning-goal/', { signal: controller.signal })
      .then(response => { setGoal(response.data); setError(false); })
      .catch(() => { if (!controller.signal.aborted) setError(true); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [progress, version]);
  const edit = () => {
    setTitle(goal?.title || '');
    setDeadline(goal?.deadline || '');
    setSelected(goal?.courses || []);
    setSearch('');
    setOpen(true);
  };
  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (saving || !selected.length) return;
    setSaving(true);
    try {
      const response = await api.put<LearningGoal>('/courses/learning-goal/', { title: title.trim(), deadline, courses: selected });
      setGoal(response.data);
      setOpen(false);
      toast.success('学习目标已保存');
    } catch (err) { toast.error(formatApiErrorToast(err, '目标保存失败，请重试')); }
    finally { setSaving(false); }
  };
  const remaining = goal ? Math.round((Date.parse(goal.deadline) - Date.parse(today)) / 86400000) : 0;
  const deadlineLabel = remaining > 0 ? `距截止 ${remaining} 天` : remaining === 0 ? '今天截止' : `已超过 ${-remaining} 天`;
  const available = courses.filter(course => course.video_file);
  const visible = available.filter(course => course.title.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()));

  return <>
    <section className="um-portal-goal" aria-label="学习目标">
      {loading ? <p className="um-course-muted" role="status">正在读取学习目标…</p> : error ? <><p role="alert">学习目标加载失败</p><button type="button" className="um-course-text-button" onClick={() => setVersion(value => value + 1)}>重试</button></> : goal ? <>
        <div className="um-portal-goal-heading"><div><span className="um-course-muted">学习目标</span><h2>{goal.title}</h2></div><button type="button" className="um-course-text-button" onClick={edit}><PencilSimple size={14} />编辑目标</button></div>
        <div className="um-portal-goal-meta"><p><time dateTime={goal.deadline}>{goal.deadline.replaceAll('-', '/')} 截止</time><span>{deadlineLabel}</span></p><span>{goal.total_courses ? `已看完 ${goal.completed_courses} / ${goal.total_courses} 门` : '目标课程不可用，请编辑'}<strong>{goal.progress_percent}%</strong></span></div>
        <progress value={goal.progress_percent} max={100} aria-label={`${goal.title}完成进度`} />
      </> : <div className="um-portal-goal-empty"><div><h2>学习目标</h2><p className="um-course-muted">选择目标课程与截止日期，进度随课程完成自动更新。</p></div><button type="button" className="um-course-button" onClick={edit}><Plus size={14} />设置目标</button></div>}
    </section>
    <Dialog open={open} onOpenChange={value => { if (!saving) setOpen(value); }}>
      <DialogContent className="um-portal-goal-editor" onInteractOutside={event => { if (saving) event.preventDefault(); }}>
        <DialogTitle>{goal ? '编辑学习目标' : '设置学习目标'}</DialogTitle>
        <DialogDescription>按已看完的课程占比计算进度，截止时间只用于提醒。</DialogDescription>
        <form onSubmit={save}>
          <label className="um-goal-field">目标<input aria-label="目标名称" required maxLength={120} value={title} onChange={event => setTitle(event.target.value)} placeholder="例如：完成金融学基础课程" disabled={saving} /></label>
          <label className="um-goal-field">截止日期<input aria-label="截止日期" required type="date" value={deadline} onChange={event => setDeadline(event.target.value)} disabled={saving} /></label>
          <fieldset disabled={saving}><legend>目标课程<span>已选 {selected.length} 门</span></legend><input aria-label="搜索目标课程" value={search} onChange={event => setSearch(event.target.value)} placeholder="搜索课程" /><div className="um-goal-course-list">{visible.map(course => <label key={course.id}><Checkbox checked={selected.includes(course.id)} onCheckedChange={checked => setSelected(previous => checked ? [...previous, course.id] : previous.filter(id => id !== course.id))} />{course.title}</label>)}{!visible.length && <p className="um-course-muted">{available.length ? '没有匹配的课程' : '暂无可选择的视频课程'}</p>}</div></fieldset>
          <footer><button type="button" className="um-course-button" disabled={saving} onClick={() => setOpen(false)}>取消</button><button type="submit" className="um-course-button um-course-button-primary" disabled={saving || !title.trim() || !selected.length}>{saving ? '保存中…' : '保存目标'}</button></footer>
        </form>
      </DialogContent>
    </Dialog>
  </>;
}
