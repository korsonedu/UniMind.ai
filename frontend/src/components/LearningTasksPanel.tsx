import { getLocale, t, useLocale } from '@/i18n';
import { useCallback, useContext, useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight } from '@phosphor-icons/react';
import { Link, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import api from '@/lib/api';
import { queryClient } from '@/lib/queryClient';
import { formatApiErrorToast } from '@/lib/apiError';
import { failedLearningTask, findRemedialTask, learningKey, learningUrl, type LearningStudyRequest, type LearningTask, type ProjectLearning } from '@/lib/projectLearning';
import { useAuthStore } from '@/store/useAuthStore';
import { MarkdownContent } from '@/components/MarkdownContent';
import { WorkspaceActiveContext } from './WorkspaceContext';
import { PracticeQuizCard } from '@/pages/xiaoyu/visuals/PracticeQuizCard';

export type { LearningTask } from '@/lib/projectLearning';
const purposes = { diagnostic: '起点任务', practice: '学习任务', recheck: '换题检验' };
const responseTypes = { objective: '选择题', explanation: '解释', calculation: '计算过程', reasoning: '推理', case: '案例分析', code: '代码文本' };
const statuses = { ready: '待作答', processing: '批改中', completed: '已完成本次作答', partial: '批改未全部完成', failed: '批改待重试', unavailable: '内容当前不可用' };

export function LearningTasksPanel({ project, onStudy }: { project: ProjectLearning; onStudy: LearningStudyRequest }) {
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
    <button className="um-agent-button" disabled={project.status === 'paused' || project.status === 'completed'} onClick={() => onStudy(t('帮我安排下一项学习任务'))}>{t('让小宇安排任务')}</button>
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

export function LearningTaskDetail({ project, task, tasks, onStudy, onSelect, refresh, onClose, active = true }: { active?: boolean; onClose?: () => void; project: ProjectLearning; task: LearningTask; tasks: LearningTask[]; onStudy: LearningStudyRequest; onSelect: (id: string | null) => void; refresh: () => void }) {
  useLocale();
  const userId = useAuthStore(state => state.user?.id);
  const workspaceActive = useContext(WorkspaceActiveContext);
  const canAnswer = project.status === 'active' || (project.status === 'preparing' && task.purpose === 'diagnostic');
  const canShowQuiz = task.status !== 'unavailable' && (!!task.exam_id || (task.is_current !== false && canAnswer));
  const needsRepair = task.is_current !== false && project.status === 'active' && failedLearningTask(task);
  const remedialTask = needsRepair ? findRemedialTask(tasks, task) : undefined;
  return <WorkspaceActiveContext.Provider value={workspaceActive && active}><article className="um-learning-task-detail" aria-label={t('学习任务：{0}', { 0: task.title })}><h4>{task.title}</h4>{task.status === 'unavailable' || (task.is_current === false && !task.exam_id) ? <p>{t('这项任务已停止使用，已有作答继续保留。请从当前学习安排接续。')}</p> : <MarkdownContent content={task.instructions} />}
      {task.status !== 'unavailable' && (task.is_current !== false || !!task.exam_id) && !!task.criteria?.length && <div className="um-learning-task-criteria"><h5>{t('评价标准')}{task.response_type && ` · ${responseTypes[task.response_type]}`}</h5><ol>{task.criteria.map((criterion, index) => <li key={index}><MarkdownContent content={criterion} /></li>)}</ol></div>}
      {task.source_task_id && <button className="um-learning-text-button" disabled={!tasks.some(item => item.id === task.source_task_id)} onClick={() => onSelect(task.source_task_id || null)}>{t('回看关联任务')}</button>}
      {task.status !== 'unavailable' && task.is_current !== false && !task.exam_id && !canAnswer && <p>{t('恢复学习后可以继续作答。')}</p>}
      {canShowQuiz && <PracticeQuizCard key={`${userId}:${task.id}`} payload={{ ...task.payload, learning_task_id: task.id, assistance: task.assistance, project_id: project.project_id, conversation_id: project.conversation_id || undefined, response_type: task.response_type, label_source: task.summary?.label_source }} onResult={refresh} />}
      <div className="um-learning-controls">
        {needsRepair && (remedialTask ? <button className="um-agent-button um-agent-button-primary" onClick={() => onSelect(remedialTask.id)}>
          {t('开始补救练习')}<ArrowRight size={16} />
        </button> : <button className="um-agent-button um-agent-button-primary" onClick={() => onStudy(
          t('帮我复盘刚才这道题的错因，并出一道新的补救题再测一次'), { task_id: task.id, stage_id: task.stage_id || undefined })}>
          {t('复盘错因并换题再测')}
        </button>)}
        {task.status === 'completed' && <button className="um-agent-button" onClick={() => onStudy(t('帮我复盘刚才这道题'), { task_id: task.id })}>
          {t(needsRepair && !remedialTask ? '仅复盘错因' : '让小宇复盘')}
        </button>}
        {onClose ? <button className="um-agent-button" onClick={onClose}>{t('返回学习路径')}</button> : <Link to={learningUrl('/xiaoyu', project.project_id, project.conversation_id || undefined)}>{t('回到项目对话')}</Link>}
      </div>
    </article></WorkspaceActiveContext.Provider>;
}
