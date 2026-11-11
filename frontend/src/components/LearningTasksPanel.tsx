import { useCallback, useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import api from '@/lib/api';
import { queryClient } from '@/lib/queryClient';
import { formatApiErrorToast } from '@/lib/apiError';
import { learningKey, learningUrl, type ProjectLearning } from '@/lib/projectLearning';
import { useAuthStore } from '@/store/useAuthStore';
import { MarkdownContent } from '@/components/MarkdownContent';
import { PracticeQuizCard, type PracticePayload } from '@/pages/xiaoyu/visuals/PracticeQuizCard';

interface LearningTask {
  id: string; title: string; instructions: string; node_id: string; version_id: number;
  status: 'ready' | 'processing' | 'completed' | 'partial' | 'failed' | 'unavailable';
  exam_id: number | null; assistance: string; review_due_at: string | null;
  summary: { total_score: number; max_score: number; graded_count: number; total_questions: number } | null;
  payload: PracticePayload;
}
const statuses = { ready: '待作答', processing: '批改中', completed: '已完成本次作答', partial: '批改未全部完成', failed: '批改待重试', unavailable: '内容当前不可用' };

export function LearningTasksPanel({ project, onStudy }: { project: ProjectLearning; onStudy: (text: string) => void }) {
  const userId = useAuthStore(state => state.user?.id);
  const [searchParams] = useSearchParams();
  const [selected, setSelected] = useState<string | null>(() => searchParams.get('learning_task'));
  const [busy, setBusy] = useState(false);
  const detailRef = useRef<HTMLElement>(null);
  useEffect(() => { detailRef.current?.scrollIntoView({ block: 'start' }); }, [selected]);
  const url = `/ai/projects/${project.project_id}/learning/tasks/`;
  const key = ['learning-tasks', userId, project.project_id];
  const query = useQuery({ queryKey: key,
    queryFn: ({ signal }) => api.get<{ tasks: LearningTask[] }>(url, { signal }).then(response => response.data),
    refetchInterval: query => query.state.data?.tasks.some(task => task.status === 'processing') ? 2500 : false,
  });
  const refresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['learning-tasks', userId, project.project_id] });
    void queryClient.invalidateQueries({ queryKey: learningKey(userId, project.project_id) });
  }, [userId, project.project_id]);
  const setupSample = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await api.post(url, { action: 'sample' });
      refresh();
      toast.success('函数基础已接入当前项目，可以从起点检查开始。');
    } catch (error) { toast.error(formatApiErrorToast(error, '样板暂时无法接入，请稍后重试。')); }
    finally { setBusy(false); }
  };
  const tasks = query.data?.tasks || [];
  const task = tasks.find(item => item.id === selected);
  return <section className="um-learning-tasks"><h3>学习任务与成果</h3>
    <p className="um-learning-muted">实际作答、正式评分和复习记录保留在这个项目。小宇会结合结果调整讲解与下一步。</p>
    {!!project.task_progress?.total && <p role="status">本轮任务 {project.task_progress.completed}/{project.task_progress.total} 已完成。{project.task_progress.feedback} {project.task_progress.next_action}</p>}
    {!project.plan.stages?.length && !project.instructions.trim() && <div className="um-learning-sample"><h4>高中数学 · 函数基础</h4><p>函数概念、函数值、定义域和图像判断。每段有起点检查、讲解示例、学习练习与换题再检验。</p><p className="um-learning-muted">原创教学样板，12 道单选题。接入后建立本项目计划，后续可和小宇调整。</p><button className="um-agent-button" disabled={busy || project.status !== 'preparing'} onClick={() => void setupSample()}>{busy ? '正在准备…' : '在当前空项目开始函数基础'}</button></div>}
    {query.isPending && <p role="status">正在读取任务…</p>}{query.isError && <p role="alert">任务暂时无法读取。<button className="um-learning-text-button" onClick={() => void query.refetch()}>重试</button></p>}
    {query.isSuccess && !tasks.length && !!project.plan.stages?.length && <p>还没有正式任务。可以让小宇查找当前内容范围内的题目，按本项目知识节点安排练习。</p>}
    <ol className="um-learning-task-list">{tasks.map(item => <li key={item.id}><div><h4>{item.title}</h4><p>{statuses[item.status]}{item.summary && ` · ${item.summary.total_score}/${item.summary.max_score} 分`}</p>
      {item.review_due_at && <p className="um-learning-muted">复习建议时间：{new Date(item.review_due_at).toLocaleString('zh-CN')}</p>}
      {item.version_id !== project.knowledge?.version_id && <p className="um-learning-muted">属于此前知识版本，保留成绩。</p>}</div>
      <button className="um-agent-button" aria-expanded={selected === item.id} onClick={() => setSelected(selected === item.id ? null : item.id)}>{selected === item.id ? '收起任务' : item.exam_id ? '查看作答与结果' : '打开任务'}</button>
    </li>)}</ol>
    {task && <article ref={detailRef} className="um-learning-task-detail" aria-label={`学习任务：${task.title}`}><h4>{task.title}</h4>{task.status === 'unavailable' ? <p>任务内容当前不可用，请和小宇重新安排。</p> : <MarkdownContent content={task.instructions} />}
      {task.status !== 'unavailable' && <PracticeQuizCard key={`${userId}:${task.id}`} payload={{ ...task.payload, learning_task_id: task.id, assistance: task.assistance, project_id: project.project_id, conversation_id: project.conversation_id || undefined }} onResult={refresh} />}
      <div className="um-learning-controls"><button className="um-agent-button" onClick={() => onStudy(`请读取本项目学习任务 ${task.id}“${task.title}”的实际结果，给我一句具体反馈和下一步。有错误时先讲清原因，再安排不同题目重新检验；不要替我作答或把有提示完成当成独立掌握。`)}>和小宇复盘这次任务</button>
        <Link to={learningUrl('/xiaoyu', project.project_id, project.conversation_id || undefined)}>回到项目对话</Link>
      </div><p className="um-learning-muted">成绩来自标准答案比对；知识归属与教学顺序仍是教学安排，单次成绩不代表已掌握。</p>
    </article>}
  </section>;
}
