import { getLocale, t, useLocale } from '@/i18n';
import { useCallback, useContext, useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import api from '@/lib/api';
import { queryClient } from '@/lib/queryClient';
import { formatApiErrorToast } from '@/lib/apiError';
import { learningKey, learningUrl, type ProjectLearning } from '@/lib/projectLearning';
import { useAuthStore } from '@/store/useAuthStore';
import { MarkdownContent } from '@/components/MarkdownContent';
import { WorkspaceActiveContext } from './WorkspaceContext';
import { PracticeQuizCard, type PracticePayload } from '@/pages/xiaoyu/visuals/PracticeQuizCard';

export interface LearningTask {
  is_current?: boolean; stage_id: string;
  id: string; title: string; instructions: string; node_id: string; version_id: number | null;
  purpose?: 'diagnostic' | 'practice' | 'recheck'; source_task_id?: string | null;
  response_type?: 'explanation' | 'calculation' | 'reasoning' | 'case' | 'code'; criteria?: string[]; sources?: string[];
  status: 'ready' | 'processing' | 'completed' | 'partial' | 'failed' | 'unavailable';
  exam_id: number | null; assistance: string; review_due_at: string | null;
  summary: { total_score: number; max_score: number; graded_count: number; total_questions: number; label_source?: string } | null;
  payload: PracticePayload;
}
const purposes = { diagnostic: '起点任务', practice: '学习任务', recheck: '换题检验' };
const responseTypes = { explanation: '解释', calculation: '计算过程', reasoning: '推理', case: '案例分析', code: '代码文本' };
const statuses = { ready: '待作答', processing: '批改中', completed: '已完成本次作答', partial: '批改未全部完成', failed: '批改待重试', unavailable: '内容当前不可用' };

export function LearningTasksPanel({ project, onStudy }: { project: ProjectLearning; onStudy: (text: string) => void }) {
  useLocale();
  const userId = useAuthStore(state => state.user?.id);
  const [searchParams] = useSearchParams();
  const [selected, setSelected] = useState<string | null>(() => searchParams.get('learning_task'));
  const [busy, setBusy] = useState(false);
  const detailRef = useRef<HTMLElement>(null);
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
      toast.success(t('函数基础已接入当前项目，可以从起点检查开始。'));
    } catch (error) { toast.error(formatApiErrorToast(error, t('样板暂时无法接入，请稍后重试。'))); }
    finally { setBusy(false); }
  };
  const tasks = query.data?.tasks || [];
  const task = tasks.find(item => item.id === selected);
  useEffect(() => { detailRef.current?.scrollIntoView({ block: 'start' }); }, [task?.id]);
  return <section className="um-learning-tasks"><h3>{t('学习任务与成果')}</h3>
    {!!project.task_progress?.total && <p role="status">{t('本轮任务')} {project.task_progress.completed}/{project.task_progress.total} {t('已完成作答与评价。')}{!project.teaching_guidance && <>{project.task_progress.feedback} {project.task_progress.next_action}</>}</p>}
    <button className="um-agent-button" disabled={project.status === 'paused' || project.status === 'completed'} onClick={() => onStudy(t('请先读取本项目目标、阶段和已有成果，结合我的基础准备下一项实际学习任务。没有阶段计划时先形成可以开始的一段；没有合适题库时可以准备带明确评价标准的开放任务。先呈现任务等我作答，不替我完成或声称已经掌握。'))}>{t('让小宇安排任务')}</button>
    {!project.plan.stages?.length && !project.instructions.trim() && <details className="um-learning-sample"><summary>{t('体验一个示例：高中数学 · 函数基础')}</summary><p>{t('12 道单选题，涵盖函数概念、函数值、定义域和图像判断。')}</p><button className="um-agent-button" disabled={busy || project.status !== 'preparing'} onClick={() => void setupSample()}>{busy ? t('正在准备…') : t('在当前空项目开始函数基础')}</button></details>}
    {query.isPending && <p role="status">{t('正在读取任务…')}</p>}{query.isError && <p role="alert">{t('任务暂时无法读取。')}<button className="um-learning-text-button" onClick={() => void query.refetch()}>{t('重试')}</button></p>}
    {query.isSuccess && !tasks.length && !!project.plan.stages?.length && <p>{t('暂无学习任务')}</p>}
    {project.teaching_guidance?.task_id && tasks.some(item => item.id === project.teaching_guidance?.task_id) && <button className="um-agent-button" onClick={() => setSelected(project.teaching_guidance?.task_id || null)}>{t('打开建议的任务')}</button>}
    <ol className="um-learning-task-list">{tasks.map(item => <li key={item.id}><div><h4>{item.title}</h4><p>{item.purpose && `${t(purposes[item.purpose])} · `}{t(statuses[item.status])}{item.summary && t(' · {0}{1}/{2} 分', { 0: item.summary.label_source === 'model_rubric_grade' ? t('模型参考评分') + " " : "", 1: item.summary.total_score, 2: item.summary.max_score })}</p>
      {!item.response_type && item.review_due_at && <p className="um-learning-muted">{t('复习建议时间：')}{new Date(item.review_due_at).toLocaleString(getLocale())}</p>}
      {item.version_id !== null && item.version_id !== project.knowledge?.version_id && <p className="um-learning-muted">{t('此前知识版本')}</p>}</div>
      <button className="um-agent-button" aria-expanded={selected === item.id} onClick={() => setSelected(selected === item.id ? null : item.id)}>{selected === item.id ? t('收起任务') : item.exam_id ? t('查看作答与结果') : t('打开任务')}</button>
    </li>)}</ol>
    {task && <LearningTaskDetail project={project} task={task} tasks={tasks} onStudy={onStudy} onSelect={setSelected} refresh={refresh} />}
  </section>;
}

export function LearningTaskDetail({ project, task, tasks, onStudy, onSelect, refresh, onClose, active = true }: { active?: boolean; onClose?: () => void; project: ProjectLearning; task: LearningTask; tasks: LearningTask[]; onStudy: (text: string) => void; onSelect: (id: string | null) => void; refresh: () => void }) {
  useLocale();
  const userId = useAuthStore(state => state.user?.id);
  const workspaceActive = useContext(WorkspaceActiveContext);
  return <WorkspaceActiveContext.Provider value={workspaceActive && active}><article className="um-learning-task-detail" aria-label={t('学习任务：{0}', { 0: task.title })}><h4>{task.title}</h4>{task.status === 'unavailable' || (task.is_current === false && !task.exam_id) ? <p>{t('这项任务已停止使用，已有作答继续保留。请从当前学习安排接续。')}</p> : <MarkdownContent content={task.instructions} />}
      {task.status !== 'unavailable' && (task.is_current !== false || !!task.exam_id) && !!task.criteria?.length && <div className="um-learning-task-criteria"><h5>{t('评价标准')}{task.response_type && ` · ${responseTypes[task.response_type]}`}</h5><ol>{task.criteria.map((criterion, index) => <li key={index}><MarkdownContent content={criterion} /></li>)}</ol></div>}
      {task.source_task_id && <button className="um-learning-text-button" disabled={!tasks.some(item => item.id === task.source_task_id)} onClick={() => onSelect(task.source_task_id || null)}>{t('回看关联任务')}</button>}
      {task.status !== 'unavailable' && (task.is_current !== false || !!task.exam_id) && <PracticeQuizCard key={`${userId}:${task.id}`} payload={{ ...task.payload, learning_task_id: task.id, assistance: task.assistance, project_id: project.project_id, conversation_id: project.conversation_id || undefined, response_type: task.response_type, label_source: task.summary?.label_source }} onResult={refresh} />}
      <div className="um-learning-controls"><button className="um-agent-button" onClick={() => onStudy(t('请用任务 read 读取本项目学习任务 {0}“{1}”已评价的真实原作答、标准和反馈，对照标准给我一句具体反馈和下一步。有错误时先解释缺口并安排补救；需要再次检验时关联这个任务并准备不同内容。不要替我作答，不把一次分数、有提示完成或模型评价当成已经掌握；代码未运行时明确说明。', { 0: task.id, 1: task.title }))}>{t('和小宇复盘这次任务')}</button>
        {onClose ? <button className="um-agent-button" onClick={onClose}>{t('回到项目对话')}</button> : <Link to={learningUrl('/xiaoyu', project.project_id, project.conversation_id || undefined)}>{t('回到项目对话')}</Link>}
      </div>
    </article></WorkspaceActiveContext.Provider>;
}
