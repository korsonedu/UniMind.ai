import { getLocale, t, useLocale } from '@/i18n';
import { useCallback, useContext, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, ArrowRight, BookOpen, ChatCircle, TreeStructure, ListBullets, Files, ClockCounterClockwise } from '@phosphor-icons/react';
import { toast } from 'sonner';
import api from '@/lib/api';
import { normalizeApiError } from '@/lib/apiError';
import { learningKey, useProjectLearning, type ProjectLearning } from '@/lib/projectLearning';
import { queryClient } from '@/lib/queryClient';
import { useAuthStore } from '@/store/useAuthStore';
import { useXiaoYuChat } from '@/pages/xiaoyu/xiaoYuChatContext';
import { ProjectChatSidebarContext } from './WorkspaceContext';
import type { AgentWorkspace } from './NativeAgentShell';
import { LearningTaskDetail, type LearningTask } from './LearningTasksPanel';
import { LearningKnowledgeView } from './LearningKnowledgeView';
import { LearningLibraryPanel } from './LearningLibraryPanel';
import { MarkdownContent } from './MarkdownContent';
import { Switch } from './ui/switch';
import '@/styles/project-learning.css';
import '@/styles/learning-workspace.css';

type View = 'chat' | 'task' | 'knowledge' | 'path' | 'resources' | 'records' | 'proposal';
interface Selection { view: View; task: string | null; node: string; returnView: View; }
const empty: Selection = { view: 'chat', task: null, node: '', returnView: 'records' };
const navigation = [
  { view: 'chat' as const, title: '对话', icon: ChatCircle },
  { view: 'path' as const, title: '学习路径', icon: ListBullets },
  { view: 'knowledge' as const, title: '知识关系', icon: TreeStructure },
  { view: 'resources' as const, title: '项目资料', icon: Files },
  { view: 'records' as const, title: '任务记录', icon: ClockCounterClockwise },
];
const guidanceLabels = { inactive: '当前安排', start: '了解起点', awaiting: '正在评价', retry: '评价待恢复', remediate: '需要补救', recheck: '需要再次检查', continue: '继续学习', review: '约定复习' };

export function useLearningWorkspace() {
  useLocale();
  const { chat, openingProject, openProject } = useXiaoYuChat();
  const { open: openProjectChat } = useContext(ProjectChatSidebarContext);
  const userId = useAuthStore(state => state.user?.id);
  const [params, setParams] = useSearchParams();
  const storageKey = `unimind:learning-view:${userId}:${chat.projectId}`;
  const [selection, setSelection] = useState<Selection>(() => {
    let saved = empty;
    try { saved = { ...empty, ...JSON.parse(sessionStorage.getItem(storageKey) || 'null') }; } catch { /* Use the current project default. */ }
    const requested = params.get('learning_task');
    const requestedView = params.get('learning_view');
    return requested ? { ...saved, view: 'task', task: requested } : requestedView === 'knowledge' || requestedView === 'proposal' ? { ...saved, view: requestedView } : saved;
  });
  const [discussion, setDiscussion] = useState<{ scope: string; title: string; payload: Record<string, unknown> | null } | null>(null);
  const discussionRef = useRef<Record<string, unknown> | undefined>(undefined);
  const [history, setHistory] = useState(false);
  const [resourceId, setResourceId] = useState('');
  const [stageId, setStageId] = useState('');
  const [busy, setBusy] = useState(false);
  const query = useProjectLearning(chat.projectId);
  const project = query.data;
  const tasksQuery = useQuery({ queryKey: ['learning-tasks', userId, chat.projectId], enabled: !!userId && !!chat.projectId && !!project?.planning_enabled,
    queryFn: ({ signal }) => api.get<{ tasks: LearningTask[] }>(`/ai/projects/${chat.projectId}/learning/tasks/`, { signal }).then(r => r.data),
    refetchInterval: q => q.state.data?.tasks.some(task => task.status === 'processing') ? 2500 : false });
  const projectsQuery = useQuery({ queryKey: ['learning-project-picker', userId], enabled: !!userId && !chat.projectId && selection.view !== 'chat',
    queryFn: ({ signal }) => api.get<{ id: number; name: string }[]>('/ai/projects/', { signal }).then(r => r.data) });
  const tasks = tasksQuery.data?.tasks || [];
  const task = tasks.find(item => item.id === selection.task);
  const guidance = project?.teaching_guidance;
  const mainTask = tasks.find(item => item.id === guidance?.task_id);
  const taskRoot = (id: string | undefined) => {
    let current = tasks.find(item => item.id === id);
    while (current?.source_task_id) {
      const parent = tasks.find(item => item.id === current?.source_task_id);
      if (!parent) break;
      current = parent;
    }
    return current?.id;
  };
  const onMainline = !!task && task.is_current !== false && task.stage_id === project?.current_stage
    && taskRoot(task.id) === taskRoot(project?.focus_task_id || mainTask?.id);
  const stages = project?.plan.stages || [];
  const stage = stages.find(item => item.id === (stageId || project?.current_stage)) || stages[0];
  const currentStage = stages.find(item => item.id === project?.current_stage);
  const viewedNode = project?.knowledge?.nodes.find(item => item.id === selection.node) || project?.knowledge?.nodes.find(item => currentStage?.knowledge_nodes?.includes(item.id)) || project?.knowledge?.nodes[0];
  const resource = project?.resources.find(item => item.id === resourceId) || project?.resources[0];
  const scope = selection.view === 'task' ? `task:${task?.id}` : selection.view === 'knowledge' ? `node:${project?.knowledge?.version_id}:${viewedNode?.id}` : selection.view === 'path' ? `stage:${stage?.id}` : selection.view === 'resources' ? `resource:${resource?.id}` : 'chat';
  const implicitDiscussion = selection.view === 'task' && task ? { title: task.title, payload: { task_id: task.id } } : selection.view === 'knowledge' && viewedNode ? { title: viewedNode.title, payload: { node_id: viewedNode.id, version_id: project?.knowledge?.version_id } } : selection.view === 'path' && stage ? { title: stage.title, payload: { stage_id: stage.id } } : selection.view === 'resources' && resource ? { title: resource.title, payload: { resource_id: resource.id } } : null;
  const currentDiscussion = discussion?.scope === scope ? discussion : implicitDiscussion;
  useLayoutEffect(() => { discussionRef.current = undefined; }, [scope]);
  const getExtraPayload = useCallback(() => {
    const payload = discussionRef.current || currentDiscussion?.payload;
    return payload ? { learning_activity: payload } : {};
  }, [currentDiscussion]);
  const active = project?.status === 'active';
  const refresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: learningKey(userId, chat.projectId) });
    void queryClient.invalidateQueries({ queryKey: ['learning-tasks', userId, chat.projectId] });
  }, [userId, chat.projectId]);
  useEffect(() => { sessionStorage.setItem(storageKey, JSON.stringify(selection)); }, [storageKey, selection]);
  const requestedTask = params.get('learning_task');
  const requestedView = params.get('learning_view');
  const requestKey = requestedTask || requestedView;
  const [handledRequest, setHandledRequest] = useState(requestKey);
  if (requestKey !== handledRequest) {
    setHandledRequest(requestKey);
    if (requestKey) setSelection(previous => requestedTask ? { ...previous, view: 'task', task: requestedTask } : { ...previous, view: requestedView === 'proposal' ? 'proposal' : 'knowledge' });
  }
  useEffect(() => {
    if ((!requestedTask && requestedView !== 'knowledge' && requestedView !== 'proposal') || openingProject || (params.get('project') && Number(params.get('project')) !== chat.projectId)) return;
    const next = new URLSearchParams(params); next.delete('learning_task'); next.delete('learning_view');
    setParams(next, { replace: true });
  }, [params, requestedTask, requestedView, setParams, openingProject, chat.projectId]);
  const context = (title: string, payload?: Record<string, unknown>) => {
    discussionRef.current = payload;
    setDiscussion({ scope, title, payload: payload || null });
  };
  const clearDiscussion = () => { discussionRef.current = undefined; setDiscussion(null); };
  const show = (view: View) => { if (view !== 'chat') openProjectChat(); clearDiscussion(); setSelection(previous => ({ ...previous, view })); };
  const openTask = (id: string, returnView: View = selection.view) => {
    clearDiscussion();
    setSelection(previous => ({ ...previous, view: 'task', task: id, returnView: returnView === 'task' ? previous.returnView : returnView }));
  };
  const ask = (text: string, payload?: Record<string, unknown>) => {
    if (chat.loading) { toast.info(t('小宇正在处理上一条消息，请稍后继续。')); return; }
    if (payload) context(currentDiscussion?.title || t('当前学习内容'), payload);
    chat.doSend(text, true);
  };
  const act = async (action: string, extra: Record<string, unknown> = {}) => {
    if (!project || busy) return false;
    setBusy(true);
    try {
      const { data } = await api.patch<ProjectLearning>(`/ai/projects/${project.project_id}/learning/`, { action, revision: project.revision, ...extra });
      queryClient.setQueryData(learningKey(userId, project.project_id), data);
      refresh(); return true;
    } catch (error) { toast.error(normalizeApiError(error, t('学习安排未更新，请重试。')).message); refresh(); return false; }
    finally { setBusy(false); }
  };
  const continueLearning = async () => {
    if (!project) return;
    if (project.status === 'paused' || project.status === 'completed') { await act('resume'); return; }
    if (mainTask) {
      if (project.focus_task_id !== mainTask.id && !(await act('focus', { task_id: mainTask.id }))) return;
      openTask(mainTask.id); return;
    }
    ask(t('请读取本项目当前学习主线与已有成果，接续当前阶段。已有待答或复测任务时直接使用；否则结合当前缺口准备具体任务。请先呈现任务，等我实际作答。'));
  };
  const setupSample = async () => {
    if (!project || busy) return;
    setBusy(true);
    try { await api.post(`/ai/projects/${project.project_id}/learning/tasks/`, { action: 'sample' }); refresh(); }
    catch (error) { toast.error(normalizeApiError(error, t('样板暂时无法接入。')).message); }
    finally { setBusy(false); }
  };
  const activityOpen = selection.view !== 'chat';
  const primaryLabel = project?.status === 'paused' || project?.status === 'completed' ? t('恢复学习') : mainTask ? guidance?.status === 'remediate' ? mainTask.summary ? t('复盘这次作答') : t('开始补救任务') : guidance?.status === 'awaiting' ? t('查看评价进度') : t('继续当前任务') : project?.status === 'preparing' ? t('和小宇明确起点') : t('请小宇接续');
  const header = project ? <header className="um-learning-work-header">
    <div className="um-learning-work-status"><div><strong>{project.name}</strong><span>{project.planning_enabled ? project.status === 'paused' ? t('已暂停') : project.status === 'completed' ? t('已结束') : t(guidanceLabels[guidance?.status || 'start']) : t('自由对话')}</span></div><p title={project.plan.goal || project.instructions}>{project.plan.goal || project.instructions || t('从当前的问题开始')}</p>{project.planning_enabled && <><p>{t('当前阶段：')}{currentStage?.title || t('起点待了解')}</p><p className="um-learning-work-next" title={guidance?.next_action}><span>{t('下一步')}</span><strong>{mainTask?.title || guidance?.next_action || t('和小宇了解起点')}</strong></p></>}</div>
    {project.planning_enabled && !(selection.view === 'task' && mainTask?.id === task?.id) && <button className="um-agent-button um-agent-button-primary" disabled={busy || openingProject} onClick={() => void continueLearning()}>{primaryLabel}<ArrowRight size={15} /></button>}
    <nav aria-label={t('项目学习视图')}>{navigation.map(item => <button key={item.view} aria-pressed={selection.view === item.view} onClick={() => show(item.view)}><item.icon size={16} />{t(item.title)}</button>)}</nav>
    {project.pending_plan.plan && <button className="um-work-pending" onClick={() => show('proposal')}>{t('有学习范围调整待确认')} <ArrowRight size={14} /></button>}
  </header> : selection.view !== 'chat' ? <header className="um-learning-work-header"><strong>{t('选择一个学习项目')}</strong><button className="um-agent-button" onClick={() => show('chat')}>{t('回到对话')}</button></header> : null;
  const activity = <div className="um-learning-activity-body">
    {!chat.projectId ? <section className="um-work-empty"><BookOpen size={30} /><h2>{t('从已有项目继续')}</h2><p>{t('选择项目后查看它的学习安排与知识关系。')}</p>{projectsQuery.data?.map(item => <button className="um-agent-button" key={item.id} onClick={() => void openProject(item.id)}>{item.name}</button>)}<Link to="/xiaoyu?new=project">{t('创建学习项目')}</Link></section>
      : openingProject || query.isPending ? <p role="status">{t('正在读取当前项目…')}</p> : query.isError || !project ? <p role="alert">{t('项目暂时无法读取。')}<button onClick={() => void query.refetch()}>{t('重试')}</button></p> : <>
      <div className="um-work-view" hidden={selection.view !== 'task'}>
        <header className="um-work-section-heading"><button className="um-agent-button" onClick={() => show(selection.returnView)}><ArrowLeft size={15} />{t('返回')}{t(navigation.find(item => item.view === selection.returnView)?.title || '任务记录')}</button>
          {task?.is_current !== false && task && active && !onMainline && <button className="um-agent-button" disabled={busy} onClick={() => void act('focus', { task_id: task.id })}>{t('改为本次学习')}</button>}</header>
        {task && !onMainline && <p className="um-work-scope">{t('正在查看其他任务，当前学习主线保持不变。')}</p>}
        {tasksQuery.isPending ? <p role="status">{t('正在读取任务…')}</p> : tasksQuery.isError ? <p role="alert">{t('任务无法读取。')}<button onClick={() => void tasksQuery.refetch()}>{t('重试')}</button></p> : !task ? <p>{t('这项任务不在当前项目中，或已不可用。')}</p> : <LearningTaskDetail active={selection.view === 'task'} project={project} task={task} tasks={tasks} refresh={refresh} onSelect={id => id && openTask(id)} onClose={() => show('chat')} onStudy={() => ask(t('请读取当前查看任务已评价的原作答、标准和反馈，只用两小段说明具体卡点和接下来的一项行动。已有适合的补救或复测任务时直接接续；没有时再关联原任务准备不同内容，等待我实际作答。'), { task_id: task.id })} />}
      </div>
      <div className="um-work-view" hidden={selection.view !== 'knowledge'}><LearningKnowledgeView project={project} selected={selection.node} onSelect={id => { clearDiscussion(); setSelection(previous => ({ ...previous, node: id })); }} tasks={tasks} tasksLoading={tasksQuery.isPending} onStudy={ask} onTask={id => openTask(id, 'knowledge')} /></div>
      <div className="um-work-view" hidden={selection.view !== 'path'}><h2>{t('学习路径')}</h2><p>{t('当前：')}{currentStage?.title || t('起点待了解')}{t('。查看其他阶段不会改变学习主线。')}</p><div className="um-work-master-detail"><nav aria-label={t('学习阶段')}>{stages.map((item, index) => <button key={item.id} aria-pressed={item.id === stage?.id} onClick={() => { clearDiscussion(); setStageId(item.id); }}><span>{index + 1}</span>{item.title}{item.id === project.current_stage && <small>{t('当前')}</small>}</button>)}</nav><section>{stage ? <><h3>{stage.title}</h3><p>{stage.outcome}</p><p>{stage.task}</p><p>{t('前置：')}{stage.prerequisites.map(id => stages.find(item => item.id === id)?.title || id).join('、') || t('无')}</p>{tasks.filter(item => item.stage_id === stage.id && item.is_current !== false).map(item => <button className="um-agent-button" key={item.id} onClick={() => openTask(item.id, 'path')}>{item.title}</button>)}</> : <><p>{t('先与小宇明确可以开始的一段学习。')}</p>{project.planning_enabled && !project.instructions.trim() && <button className="um-agent-button" disabled={busy} onClick={() => void setupSample()}>{t('体验函数基础样板')}</button>}</>}</section></div><details className="um-work-preferences"><summary>{t('项目安排')}</summary><label>{t('主动提醒')}<Switch checked={project.reminders_enabled} disabled={busy || !project.planning_enabled} onCheckedChange={enabled => void act('reminders', { enabled })} /></label>{project.planning_enabled && <button className="um-agent-button" disabled={busy || project.status === 'preparing'} onClick={() => void act(active ? 'pause' : 'resume')}>{active ? t('暂停学习') : t('恢复学习')}</button>}{active && <button className="um-agent-button" disabled={busy} onClick={() => void act('complete')}>{t('结束当前目标')}</button>}</details></div>
      <div className="um-work-view" hidden={selection.view !== 'records'}><div className="um-work-section-heading"><h2>{history ? t('历史版本任务') : t('当前任务记录')}</h2><button className="um-agent-button" onClick={() => setHistory(value => !value)}>{history ? t('查看当前版本') : t('查看历史版本')}</button></div>{tasksQuery.isPending && <p role="status">{t('正在读取任务…')}</p>}{tasksQuery.isError && <p role="alert">{t('记录无法读取。')}<button onClick={() => void tasksQuery.refetch()}>{t('重试')}</button></p>}<div className="um-work-task-directory">{tasks.filter(item => history ? item.is_current === false : item.is_current !== false).map(item => <button key={item.id} onClick={() => openTask(item.id, 'records')}><strong>{item.title}</strong><span>{item.is_current === false && !item.exam_id ? t('此版本已停止使用') : item.summary ? t('{0}/{1} 分{2}', { 0: item.summary.total_score, 1: item.summary.max_score, 2: item.summary.label_source === 'model_rubric_grade' ? t(' · 模型参考评价') : '' }) : item.status === 'ready' ? t('待作答') : item.status === 'processing' ? t('评价中') : t('评价未完成')}<ArrowRight size={15} /></span></button>)}</div>{!tasks.some(item => history ? item.is_current === false : item.is_current !== false) && <p>{history ? t('暂无历史版本任务。') : t('当前安排尚未准备学习任务，可以请小宇接续。')}</p>}</div>
      <div className="um-work-view" hidden={selection.view !== 'resources'}><h2>{t('项目资料')}</h2><div className="um-work-master-detail"><nav aria-label={t('项目资料目录')}>{project.resources.map(item => <button key={item.id} aria-pressed={item.id === resource?.id} onClick={() => { clearDiscussion(); setResourceId(item.id); }}>{item.title}</button>)}</nav><section>{resource ? <><h3>{resource.title}</h3><p>{resource.source_kind === 'block_resource_excerpt' ? t('资源摘要快照，未读取完整原文或视频字幕') : resource.source_kind === 'generated_graph' ? t('AI 生成结构快照，尚未核验教材依据') : resource.source_kind === 'unimind_original' ? t('原创内容快照') : t('已读取资料')} · {new Date(resource.read_at).toLocaleDateString(getLocale())}</p><MarkdownContent content={resource.excerpt} />{!['unimind_original', 'generated_graph'].includes(resource.source_kind || '') && <a href={resource.url} target="_blank" rel="noreferrer">{t('打开原文')}</a>}</> : <p>{t('还没有项目资料，可以在对话中补充学习来源。')}</p>}</section></div><details><summary>{t('跨项目资料与方法复用')}</summary><LearningLibraryPanel project={project} onStudy={ask} /></details></div>
      <div className="um-work-view" hidden={selection.view !== 'proposal'}><h2>{t(stages.length ? '学习安排调整' : '确认学习路径')}</h2>{project.pending_plan.plan ? <><p>{project.pending_plan.reason}</p><dl className="um-work-change-summary"><dt>{t('目标')}</dt><dd>{project.pending_plan.plan.goal}</dd><dt>{t('学习范围')}</dt><dd>{project.pending_plan.knowledge?.targets.join('、') || t('按阶段安排')}</dd><dt>{t('学习深度')}</dt><dd>{project.pending_plan.knowledge?.depth === 'transfer' ? t('迁移应用') : t('理解与应用')}</dd></dl><h3>{t('阶段变化')}</h3><p>{project.pending_plan.plan.stages.filter(item => !stages.some(old => old.id === item.id && old.title === item.title && old.outcome === item.outcome)).map(item => item.title).join('、') || t('阶段内容保持不变')}{stages.some(old => !project.pending_plan.plan!.stages.some(item => item.id === old.id)) && t('；部分原阶段将移出当前安排')}</p>{!!stages.length && <><h3>{t('对当前任务的影响')}</h3><p>{project.pending_plan.plan.knowledge_path?.version_id !== project.knowledge?.version_id || (mainTask && !project.pending_plan.plan.stages.some(item => item.id === mainTask.stage_id)) ? t('原任务进入历史，未提交任务停止作答；草稿保留用于回看。需要为新安排准备任务。') : t('当前任务与作答记录保留，调整不会自动完成任务。')}</p>{project.pending_plan.plan.knowledge_path?.version_id !== project.knowledge?.version_id && <p>{t('已有作答保留在原版本，新版本暂不继承这些观察。旧版未提交任务将停止作答，草稿保留用于回看。')}</p>}</>}<details><summary>{t('查看调整后的阶段')}</summary>{project.pending_plan.plan.stages.map(item => <p key={item.id}>{item.title}：{item.outcome}</p>)}</details><div className="um-work-actions"><button className="um-agent-button um-agent-button-primary" disabled={busy} onClick={async () => { if (await act('accept')) show('path'); }}>{t(stages.length ? '采用调整' : '采用这条路径')}</button><button className="um-agent-button" disabled={busy} onClick={async () => { if (await act('reject')) show('chat'); }}>{t('保留原安排')}</button></div></> : <p>{t('当前没有待确认的调整。')}</p>}</div>
    </>}
  </div>;
  return { workspace: { active: activityOpen, activityKey: selection.view, header, activity, chatContext: currentDiscussion?.payload ? <div className="um-work-chat-context"><span>{t('正在讨论：')}{currentDiscussion.title}</span><button aria-label={t('取消当前内容引用')} onClick={() => context('')}>{t('取消引用')}</button></div> : activityOpen ? <div className="um-work-chat-context">{t('小宇 · 当前项目对话')}</div> : null } satisfies AgentWorkspace, getExtraPayload, openLearning: () => show(project?.planning_enabled ? 'path' : 'knowledge') };
}
