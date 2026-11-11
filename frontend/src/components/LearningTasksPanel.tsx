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
      toast.success('函数基础已接入当前项目，可以从起点检查开始。');
    } catch (error) { toast.error(formatApiErrorToast(error, '样板暂时无法接入，请稍后重试。')); }
    finally { setBusy(false); }
  };
  const tasks = query.data?.tasks || [];
  const task = tasks.find(item => item.id === selected);
  useEffect(() => { detailRef.current?.scrollIntoView({ block: 'start' }); }, [task?.id]);
  return <section className="um-learning-tasks"><h3>学习任务与成果</h3>
    <p className="um-learning-muted">实际成果、评价依据和后续安排保留在这个项目。小宇会结合结果调整讲解、补救和再次检验。</p>
    {!!project.task_progress?.total && <p role="status">本轮任务 {project.task_progress.completed}/{project.task_progress.total} 已完成作答与评价。{!project.teaching_guidance && <>{project.task_progress.feedback} {project.task_progress.next_action}</>}</p>}
    <button className="um-agent-button" disabled={project.status === 'paused' || project.status === 'completed'} onClick={() => onStudy('请先读取本项目目标、阶段和已有成果，结合我的基础准备下一项实际学习任务。没有阶段计划时先形成可以开始的一段；没有合适题库时可以准备带明确评价标准的开放任务。先呈现任务等我作答，不替我完成或声称已经掌握。')}>让小宇安排任务</button>
    {!project.plan.stages?.length && !project.instructions.trim() && <details className="um-learning-sample"><summary>体验一个示例：高中数学 · 函数基础</summary><p>函数概念、函数值、定义域和图像判断。每段有起点检查、讲解示例、学习练习与换题再检验。</p><p className="um-learning-muted">原创教学样板，12 道单选题。接入后建立本项目计划，后续可和小宇调整。</p><button className="um-agent-button" disabled={busy || project.status !== 'preparing'} onClick={() => void setupSample()}>{busy ? '正在准备…' : '在当前空项目开始函数基础'}</button></details>}
    {query.isPending && <p role="status">正在读取任务…</p>}{query.isError && <p role="alert">任务暂时无法读取。<button className="um-learning-text-button" onClick={() => void query.refetch()}>重试</button></p>}
    {query.isSuccess && !tasks.length && !!project.plan.stages?.length && <p>还没有任务。可以让小宇围绕当前阶段安排题库练习，或准备带评价标准的开放任务，无需先建立知识地图。</p>}
    {project.teaching_guidance?.task_id && tasks.some(item => item.id === project.teaching_guidance?.task_id) && <button className="um-agent-button" onClick={() => setSelected(project.teaching_guidance?.task_id || null)}>打开建议的任务</button>}
    <ol className="um-learning-task-list">{tasks.map(item => <li key={item.id}><div><h4>{item.title}</h4><p>{item.purpose && `${purposes[item.purpose]} · `}{statuses[item.status]}{item.summary && ` · ${item.summary.label_source === 'model_rubric_grade' ? '模型参考评分 ' : ''}${item.summary.total_score}/${item.summary.max_score} 分`}</p>
      {!item.response_type && item.review_due_at && <p className="um-learning-muted">复习建议时间：{new Date(item.review_due_at).toLocaleString('zh-CN')}</p>}
      {item.version_id !== null && item.version_id !== project.knowledge?.version_id && <p className="um-learning-muted">属于此前知识版本，保留成绩。</p>}</div>
      <button className="um-agent-button" aria-expanded={selected === item.id} onClick={() => setSelected(selected === item.id ? null : item.id)}>{selected === item.id ? '收起任务' : item.exam_id ? '查看作答与结果' : '打开任务'}</button>
    </li>)}</ol>
    {task && <article ref={detailRef} className="um-learning-task-detail" aria-label={`学习任务：${task.title}`}><h4>{task.title}</h4>{task.status === 'unavailable' ? <p>任务内容当前不可用，请和小宇重新安排。</p> : <MarkdownContent content={task.instructions} />}
      {task.status !== 'unavailable' && !!task.criteria?.length && <div className="um-learning-task-criteria"><h5>评价标准{task.response_type && ` · ${responseTypes[task.response_type]}`}</h5><ol>{task.criteria.map((criterion, index) => <li key={index}><MarkdownContent content={criterion} /></li>)}</ol><p className="um-learning-muted">模型将依据这些标准给出参考评价，尚未独立复核。{task.response_type === 'code' && '代码仅作文本审阅，不会执行，不能据此认定测试通过。'}</p></div>}
      {task.source_task_id && <button className="um-learning-text-button" disabled={!tasks.some(item => item.id === task.source_task_id)} onClick={() => setSelected(task.source_task_id || null)}>回看关联任务</button>}
      {task.status !== 'unavailable' && <PracticeQuizCard key={`${userId}:${task.id}`} payload={{ ...task.payload, learning_task_id: task.id, assistance: task.assistance, project_id: project.project_id, conversation_id: project.conversation_id || undefined, response_type: task.response_type, label_source: task.summary?.label_source }} onResult={refresh} />}
      <div className="um-learning-controls"><button className="um-agent-button" onClick={() => onStudy(`请用任务 read 读取本项目学习任务 ${task.id}“${task.title}”已评价的真实原作答、标准和反馈，对照标准给我一句具体反馈和下一步。有错误时先解释缺口并安排补救；需要再次检验时关联这个任务并准备不同内容。不要替我作答，不把一次分数、有提示完成或模型评价当成已经掌握；代码未运行时明确说明。`)}>和小宇复盘这次任务</button>
        <Link to={learningUrl('/xiaoyu', project.project_id, project.conversation_id || undefined)}>回到项目对话</Link>
      </div><p className="um-learning-muted">{task.response_type || task.summary?.label_source === 'model_rubric_grade' ? '模型依据冻结标准评价，尚未独立复核；任务完成不等于已经掌握。' : '单选成绩来自标准答案比对；知识归属与教学顺序仍是教学安排，单次成绩不代表已掌握。'}</p>
    </article>}
  </section>;
}
