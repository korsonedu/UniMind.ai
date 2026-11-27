import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, ArrowRight, BookOpen, CaretDown, Check, Clock, NotePencil, TreeStructure } from '@phosphor-icons/react';
import { Link } from 'react-router-dom';
import { t, useLocale } from '@/i18n';
import type { Message } from '@/hooks/useAgentConversation';
import api from '@/lib/api';
import { queryKeys } from '@/lib/queryKeys';
import { failedLearningTask, findRemedialTask, passedLearningTask, playableLearningTask, type LearningResource, type LearningStage, type LearningTask, type ProjectLearning } from '@/lib/projectLearning';
import type { PracticeResult } from '@/pages/xiaoyu/visuals/PracticeQuizCard';
import type { DshCard } from './DshToolCard';
import { projectCoursePath } from './course/projectCourseLinks';
import { LearningKnowledgeView } from './LearningKnowledgeView';
import { LearningMemorySources } from './LearningMemorySources';
import { LearningTaskDetail } from './LearningTasksPanel';
import type { LearningWorkspace } from './LearningWorkspace';
import { MarkdownContent } from './MarkdownContent';
import { Switch } from './ui/switch';
import '@/styles/learning-workspace.css';
import '@/styles/learning-path-canvas.css';

type StageState = 'passed' | 'current' | 'remediate' | 'upcoming';
type CourseLink = { href: string; title: string; stageId?: string };

const stageLabels = { passed: '已通过', current: '当前阶段', remediate: '待巩固', upcoming: '待学习' };
const taskLabels = { ready: '待作答', processing: '批改中', completed: '已批改', partial: '批改未全部完成', failed: '批改待重试', unavailable: '内容不可用' };
const taskActions = { processing: '查看批改进度', partial: '查看批改情况', failed: '查看批改情况' } as const;
const knowledgeLabels = { supported: '已有支持观察', review: '待复习', recheck: '待换题检验', unassessed: '待检查' };

function conversationCourses(messages: Message[], project: ProjectLearning, conversationId: string, tasks: LearningTask[]) {
  const stages = project.plan.stages || [];
  const links = new Map<string, CourseLink>();
  let stageId: string | undefined;
  const add = (url: string, title: string) => {
    const href = projectCoursePath(url, project.project_id, conversationId);
    if (!href || !/^\/course\/\d+/.test(href)) return;
    if (!links.has(href) || (!links.get(href)?.stageId && stageId)) links.set(href, { href, title, stageId });
  };
  for (const message of messages) {
    if (message.role === 'user') {
      const activity = message.metadata?.learning_activity as { stage_id?: string; kind?: string; content?: { id: string }; task_id?: string; task?: { stage_id: string } } | undefined;
      const selected = activity?.stage_id || (activity?.kind === 'stage' ? activity.content?.id : undefined)
        || activity?.task?.stage_id || tasks.find(task => activity?.task_id === task.id)?.stage_id;
      stageId = stages.find(stage => stage.id === selected)?.id;
      continue;
    }
    if (message.visible === false) continue;
    const toolCards = (message.metadata?.dsh_cards as DshCard[] | undefined) || [];
    const step = message.toolStep?.status === 'succeeded' ? message.toolStep : undefined;
    const visuals = step?.visuals?.length ? step.visuals : step?.visual ? [step.visual] : [];
    for (const card of [...toolCards, ...visuals.map(visual => ({ ...visual, tool: step?.name }) as DshCard)]) {
      if (card.type !== 'data_card' || (card.tool !== 'search_courses' && card.tool !== 'search_asr' && !['相关课程', '课程讲稿来源'].includes(String(card.payload.title)))) continue;
      const items = card.payload.items as { label?: string; action_link?: string }[] | undefined;
      for (const item of items || []) if (item.action_link) add(item.action_link, item.label || t('课程片段'));
    }
    for (const match of message.content.matchAll(/\[([^\]]+)\]\(((?:https?:\/\/[^/\s)]+)?\/course\/\d+\/?(?:[?#][^\s)]*)?)\)/g)) add(match[2], match[1]);
  }
  return [...links.values()];
}

function hasSubmittedAnswer(task: LearningTask) {
  return !!task.exam_id || task.status === 'completed';
}

function TaskRow({ task, openTask }: { task: LearningTask; openTask: (id: string) => void }) {
  const status = task.status !== 'completed' ? taskLabels[task.status] : task.purpose === 'diagnostic' ? '摸底已完成' : passedLearningTask(task) ? '已通过' : '未通过';
  return <button type="button" className="um-path-task" onClick={() => openTask(task.id)}>
    <span>{task.title}<small>{task.is_current === false && `${t('旧安排')} · `}{t(status)}{task.status === 'completed' && task.summary?.max_score ? ` · ${task.summary.total_score}/${task.summary.max_score}` : ''}</small></span><ArrowRight size={15} />
  </button>;
}

function CourseLinks({ links }: { links: CourseLink[] }) {
  return <ul className="um-path-links">{links.map(link => <li key={link.href}>
    <Link to={link.href}><BookOpen size={15} /><span>{link.title}</span><ArrowRight size={14} /></Link>
  </li>)}</ul>;
}

function Materials({ resources }: { resources: LearningResource[] }) {
  return resources.map(resource => <details key={resource.id}>
    <summary>{resource.title}</summary><MarkdownContent content={resource.excerpt} />
    {/^https?:\/\//i.test(resource.url) && <a href={resource.url} target="_blank" rel="noreferrer">{t('打开原文')}</a>}
  </details>);
}

function TaskReview({ task, diagnostics, openTask }: { task: LearningTask; diagnostics?: boolean; openTask: (id: string) => void }) {
  const examId = task.exam_id!;
  const result = useQuery({
    queryKey: queryKeys.exams.detail(examId),
    queryFn: ({ signal }) => api.get<PracticeResult>(`/quizzes/exams/${examId}/`, { signal }).then(response => response.data),
    staleTime: 5000,
  });
  const rows = result.data?.results.filter(item => item.status === 'graded' && (diagnostics || item.score < item.max_score)) || [];
  if (!diagnostics && result.isSuccess && !rows.length && !task.source_task_id) return null;
  return <article className="um-path-review">
    <TaskRow task={task} openTask={openTask} />
    {diagnostics && result.data && task.summary?.label_source === 'objective_answer_key' && <p>{t('正确率')} {Math.round(100 * result.data.correct_count / Math.max(1, result.data.total_questions))}%</p>}
    {task.source_task_id && <button className="um-learning-text-button" onClick={() => openTask(task.source_task_id!)}>{t('回看补救前的作答')}</button>}
    {result.isPending && <small role="status">{t('正在读取逐题反馈…')}</small>}
    {result.isError && <button type="button" className="um-learning-text-button" onClick={() => void result.refetch()}>{t('重试读取反馈')}</button>}
    {rows.map(item => <div key={item.position}>
      <strong>{t('第 {0} 题', { 0: item.position })} · {item.score}/{item.max_score}</strong>
      <MarkdownContent content={item.feedback || item.analysis || (item.is_correct ? t('该题已通过') : t('可打开任务查看原作答与解析'))} />
    </div>)}
  </article>;
}

export function LearningPathCanvas({ workspace, messages, conversationId }: {
  workspace: LearningWorkspace; messages: Message[]; conversationId: string;
}) {
  const locale = useLocale();
  const { project, query, taskQuery, tasks, openingProject, busy, view, show, sidebar,
    completedStages, nextStage, allDone, act, ask, openTask, prefill, refresh, setupSample } = workspace;
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [selection, setSelection] = useState<{ projectId: number; versionId: number; nodeId: string }>();
  const [fallbackNow] = useState(() => Date.now());
  const scroll = useRef<HTMLDivElement>(null);
  const returnScroll = useRef(0);
  const taskId = view.kind === 'task' ? view.id : undefined;
  useEffect(() => {
    if (scroll.current) scroll.current.scrollTop = view.kind === 'path' ? returnScroll.current : 0;
    if (view.kind !== 'task') returnScroll.current = 0;
  }, [view.kind, taskId]);
  const openPathTask = (id: string) => {
    returnScroll.current = scroll.current?.scrollTop || 0;
    openTask(id);
  };
  const courses = useMemo(() => project && sidebar.visible ? conversationCourses(messages, project, conversationId, tasks) : [],
    [messages, project, conversationId, tasks, sidebar.visible]);

  if (openingProject || (query.fetchStatus === 'fetching' && !project)) return <p className="um-path-loading" role="status">{t('正在打开学习项目…')}</p>;
  if (query.isError && !project) return <p className="um-path-loading" role="alert">{t('学习安排暂时无法读取。')} <button className="um-agent-button" onClick={() => void query.refetch()}>{t('重试')}</button></p>;
  if (!project || (!project.planning_enabled && view.kind !== 'knowledge')) return <div className="um-path-empty">
    <TreeStructure size={28} /><h2>{t('在项目中制定学习路径')}</h2>
    <p>{t('新建学习项目后，在对话里告诉小宇你想学什么。')}</p>
    <Link className="um-agent-button um-agent-button-primary" to="/xiaoyu?new=project">{t('新建学习项目')}</Link>
    {project && <button className="um-agent-button" onClick={() => show('knowledge')}>{t('查看知识关系')}</button>}
    {project?.memory_connectors &&
      <LearningMemorySources key={`sources:${project.project_id}`} projectId={project.project_id} />
    }
  </div>;

  const versionId = project.knowledge?.version_id;
  const node = selection?.projectId === project.project_id && selection.versionId === versionId
    ? selection.nodeId : project.last_viewed_node?.node_id || '';
  const selectNode = (nodeId: string) => {
    if (!versionId) return;
    setSelection({ projectId: project.project_id, versionId, nodeId });
    if (project.memory_connectors) {
      void api.post(`/ai/projects/${project.project_id}/learning/knowledge/`, {
        action: 'remember_view', version_id: versionId, node_id: nodeId,
      }).catch(() => undefined);
    }
  };
  const stages = project.plan.stages || [];
  const pending = project.pending_plan.plan;
  const proposal = view.kind === 'proposal' && !!pending;
  const visibleStages = proposal ? pending.stages : stages;
  const activeTasks = tasks.filter(task => task.is_current !== false);
  const diagnostics = tasks.filter(task => task.purpose === 'diagnostic' && (task.is_current !== false || task.exam_id));
  const assessed = tasks.filter(task => task.status !== 'unavailable' && task.exam_id && task.summary?.graded_count
    && (task.is_current !== false || (task.purpose === 'diagnostic' && !task.stage_id)));
  const latestDiagnostic = [...diagnostics].reverse().find(task => task.is_current !== false && task.status === 'completed' && task.summary?.max_score);
  const pendingDiagnostic = [...diagnostics].reverse().find(playableLearningTask);
  const startingTask = !pending && !stages.length ? pendingDiagnostic || latestDiagnostic : undefined;
  const submissions = tasks.filter(hasSubmittedAnswer).reverse();
  const otherSubmissions = submissions.filter(task => task.id !== startingTask?.id && !stages.some(stage => stage.id === task.stage_id));
  const plannedGoal = (proposal ? pending.goal : project.plan.goal) || project.instructions.trim();
  const goal = plannedGoal || project.name;
  const generatePath = (task: LearningTask) => ask(t('根据我的摸底结果制定学习路径吧'), { task_id: task.id });
  const unassignedResources = project.resources.filter(resource => !stages.some(stage => stage.sources.includes(resource.id)));
  const newestTasks = [...activeTasks].reverse();
  const stageFailure = (stageId: string) => completedStages.has(stageId) ? undefined :
    newestTasks.find(task => task.stage_id === stageId && failedLearningTask(task));
  const nextFailure = nextStage && stageFailure(nextStage.id);
  const nextTask = nextStage && (nextFailure ? findRemedialTask(activeTasks.filter(task => task.stage_id === nextStage.id), nextFailure) :
    newestTasks.find(task => task.stage_id === nextStage.id && task.purpose !== 'diagnostic' && playableLearningTask(task)));
  const nextTaskIsRemedial = nextTask && (nextFailure || nextTask.purpose === 'recheck' || nextTask.source_task_id);
  const state = (stage: LearningStage): StageState => {
    if (proposal) return 'upcoming';
    if (completedStages.has(stage.id)) return 'passed';
    if (stageFailure(stage.id)) return 'remediate';
    if (stage.id === nextStage?.id && project.status === 'active') return 'current';
    return 'upcoming';
  };
  const requestRemedialTask = (stage: LearningStage, failedTask: LearningTask) => ask(
    t('帮我复盘「{0}」刚做错的题，并出一道新的补救题再测一次', { 0: stage.title }),
    { task_id: failedTask.id, stage_id: stage.id });
  const continueStage = async () => {
    if (!nextStage) return;
    if (nextTask) {
      if (project.current_stage !== nextTask.stage_id && !(await act('focus', { task_id: nextTask.id }))) return;
      openTask(nextTask.id);
    } else if (nextFailure) {
      requestRemedialTask(nextStage, nextFailure);
    } else {
      ask(t('帮我开始「{0}」这一阶段的学习', { 0: nextStage.title }), { stage_id: nextStage.id });
    }
  };
  const serverNow = project.server_time ? Date.parse(project.server_time) : Number.NaN;
  const now = Number.isFinite(serverNow) ? serverNow : fallbackNow;
  const nextReview = activeTasks.map(task => task.review_due_at).filter((date): date is string => !!date && Date.parse(date) > now).sort((a, b) => Date.parse(a) - Date.parse(b))[0];
  const reviewAt = project.status === 'completed' && project.followup_at ? project.followup_at : nextReview || new Date(now + 3 * 86400000).toISOString();
  const reminder = (report = false) => <label className="um-path-reminder">
    {t(report ? '到期主动提醒' : '主动提醒')}
    <Switch checked={project.reminders_enabled && (!report || project.status !== 'completed' || !!project.followup_at)} disabled={busy}
      onCheckedChange={enabled => void act('reminders', { enabled, ...(report ? { review_at: reviewAt } : {}) })} />
  </label>;
  const progressLabel = t('已通过 {0} / {1} 个阶段', { 0: completedStages.size, 1: stages.length });
  const task = tasks.find(item => item.id === taskId);
  const loadingTasks = project.planning_enabled && taskQuery.isPending;
  const report = view.kind === 'report';
  const statusLabel = proposal ? '待确认' : project.status === 'completed' ? '已结项'
    : report ? '待结项' : project.status === 'active' ? '学习中' : project.status === 'paused' ? '已暂停' : '准备中';
  const taskAction = (task: LearningTask, readyLabel: string) =>
    t(task.status === 'processing' || task.status === 'partial' || task.status === 'failed' ? taskActions[task.status] : readyLabel);

  return <section className="um-path-canvas" aria-label={t('学习路径画布')}>
    <div className="um-path-scroll" ref={scroll}>
      {view.kind === 'task' ? <>
        <button className="um-agent-button" onClick={() => show(view.back)}><ArrowLeft size={16} />{t('返回')}</button>
        {task ? <LearningTaskDetail active={sidebar.visible} project={project} task={task} tasks={tasks} refresh={refresh}
          onSelect={id => { if (id) openTask(id); }} onStudy={ask} /> : loadingTasks ? <p role="status">{t('正在读取任务…')}</p> :
          taskQuery.isError ? <p role="alert">{t('任务暂时无法读取。')} <button onClick={() => void taskQuery.refetch()}>{t('重试')}</button></p> : <p>{t('这项任务已不可用。')}</p>}
        {task?.purpose === 'diagnostic' && task.status === 'completed' && project.status === 'preparing' && !pending &&
          <button className="um-agent-button um-agent-button-primary" onClick={() => generatePath(task)}>{t('生成学习路径')}<ArrowRight size={16} /></button>}
        {allDone && <button className="um-agent-button um-agent-button-primary" onClick={() => show('report')}>{t('查看学习成果报告')}<ArrowRight size={16} /></button>}
      </> : view.kind === 'knowledge' ?
        <LearningKnowledgeView project={project} selected={node} onSelect={selectNode} tasks={tasks} tasksLoading={loadingTasks} onStudy={ask} onTask={openTask}
          onBack={() => show(pending ? 'proposal' : 'path')} />
      : <>
        <header className="um-path-overview">
          <div className="um-path-heading">
            <span className="um-path-pill">{t(statusLabel)}</span>
            {!report && goal !== project.name && <span>{project.name}</span>}
          </div>
          <h2>{report ? t('学习成果报告') : goal}</h2>
          {report && <p>{goal}</p>}
          {!proposal && (!report || !!stages.length) && <div className="um-path-progress">
            {!!stages.length && <strong>{progressLabel}</strong>}
            {!report && <button type="button" className="um-path-knowledge-button" onClick={() => show('knowledge')}>
              <TreeStructure size={15} />{t('知识关系')}
            </button>}
            {!!stages.length && <progress value={completedStages.size} max={stages.length} aria-label={progressLabel} />}
          </div>}
        </header>

        {report ? <>
          <section className="um-path-block"><h3>{t('摸底与阶段成果')}</h3>
            {assessed.filter(task => task.purpose === 'diagnostic').map(task => <TaskReview key={task.id} task={task} diagnostics openTask={openTask} />)}
            {!assessed.some(task => task.purpose === 'diagnostic') && <p>{t('本轮没有已评分的摸底小测。')}</p>}
            <ol className="um-path-summary-list">{stages.map(stage => {
              const scores = assessed.filter(task => task.stage_id === stage.id && task.purpose !== 'diagnostic' && task.status === 'completed' && task.summary?.max_score);
              const best = scores.reduce<LearningTask | undefined>((best, task) => !best || task.summary!.total_score / task.summary!.max_score > best.summary!.total_score / best.summary!.max_score ? task : best, undefined);
              return <li key={stage.id}><span>{stage.title}</span><strong>{completedStages.has(stage.id) ? t('已通过') : t(best ? '待巩固' : '暂无通过记录')}{best && ` · ${t('最佳')} ${best.summary!.total_score}/${best.summary!.max_score}`}</strong></li>;
            })}</ol>
          </section>
          <section className="um-path-block"><h3>{t('作答复盘')}</h3>
            {assessed.filter(task => task.purpose !== 'diagnostic' && (task.source_task_id || task.summary!.total_score < task.summary!.max_score)).map(task => <TaskReview key={task.id} task={task} openTask={openTask} />)}
            {!!courses.length && <><h4>{t('回看课程与讲稿片段')}</h4><CourseLinks links={courses} /></>}
            <button className="um-agent-button" onClick={sidebar.openNotes}><NotePencil size={15} />{t('打开笔记')}</button>
          </section>
          <section className="um-path-block"><h3><Clock size={16} />{t('间隔复习')}</h3>
            <p>{nextReview || (project.status === 'completed' && project.followup_at) ? t('建议在 {0} 复测', { 0: new Date(reviewAt).toLocaleString(locale) }) : t('3 天后建议快速复测')}</p>
            {reminder(true)}
            <p>{project.status !== 'completed' ? t('完成目标后，小宇会在新的学习项目中参考本次成果。')
              : project.events.some(event => event.kind === 'complete' && event.content.summary) ? t('本次学习成果已归档，小宇会在后续学习项目中参考这些记录。')
              : t('阶段任务与反馈已保存在项目中，随时可以回来复盘。')}</p>
          </section>
        </> : <>
          {!proposal && !pending && !stages.length && <section className="um-path-block">
            <h3>{t(startingTask ? '起点小测' : '学习目标')}</h3>
            {startingTask ? <TaskRow task={startingTask} openTask={openPathTask} />
              : <p>{t(plannedGoal ? '请小宇根据项目目标准备起点小测或学习路径。' : '告诉小宇你想学什么、准备用在哪里，以及已经会哪些内容。')}</p>}
          </section>}
          {proposal && project.pending_plan.reason && <p className="um-path-reason">{project.pending_plan.reason}</p>}
          {proposal && stages.length > 0 && pending.knowledge_path?.version_id !== project.knowledge?.version_id &&
            <p className="um-path-reason">{t('采用新知识版本后，已提交的作答仍可回看。')}</p>}
          {!!visibleStages.length && <ol className="um-path-stages" role="list" aria-label={t('学习阶段')}>{visibleStages.map((stage, index) => {
            const status = state(stage);
            const stageTasks = activeTasks.filter(task => task.stage_id === stage.id);
            const stagePractice = stageTasks.filter(task => !hasSubmittedAnswer(task));
            const stageSubmissions = submissions.filter(task => task.stage_id === stage.id);
            const latestFailedTask = status === 'remediate' ? stageFailure(stage.id) : undefined;
            const stagePlayableTask = latestFailedTask ? findRemedialTask(stageTasks, latestFailedTask) : undefined;
            const prerequisites = visibleStages.filter(item => stage.prerequisites.includes(item.id));
            const resources = project.resources.filter(resource => stage.sources.includes(resource.id));
            const recommended = courses.filter(link => link.stageId === stage.id);
            const nodes = project.knowledge?.nodes.filter(item => stage.knowledge_nodes?.includes(item.id)) || [];
            const isCurrent = !proposal && stage.id === nextStage?.id && project.status === 'active';
            const canPrepareTask = !isCurrent && project.status === 'active' && !loadingTasks && !taskQuery.isError
              && !(latestFailedTask ? stagePlayableTask : stageTasks.some(playableLearningTask));
            const stageKey = `${proposal}:${stage.id}`;
            const isOpen = expanded[stageKey] ?? (proposal ? index === 0 : isCurrent);
            return <li key={stageKey} className="um-path-stop" data-state={status} data-current={isCurrent}>
              <span className="um-path-stage-number" aria-hidden="true">
                {status === 'passed' ? <Check size={14} weight="bold" /> : index + 1}
              </span>
              <details className="um-path-stage" open={isOpen} onToggle={event => {
                const open = event.currentTarget.open;
                if (open !== isOpen) setExpanded(previous => ({ ...previous, [stageKey]: open }));
              }}>
                <summary aria-current={isCurrent ? 'step' : undefined}>
                  <span className="um-path-stage-heading"><strong>{stage.title}</strong>
                    {!proposal && <small>{t(stageLabels[status])}</small>}
                  </span><CaretDown size={14} />
                </summary>
                <div className="um-path-stage-content">
                  <section><h4>{t('阶段目标')}</h4><MarkdownContent content={stage.outcome} />
                    {!!prerequisites.length && <p className="um-path-muted">{t('先修阶段：{0}', { 0: prerequisites.map(item => item.title).join(locale === 'en' ? ', ' : '、') })}</p>}
                    {!proposal && !!nodes.length && <ul>{nodes.map(item => <li key={item.id}><button className="um-learning-text-button" onClick={() => { selectNode(item.id); show('knowledge'); }}>
                      {item.title} · {t(knowledgeLabels[item.learning_status || 'unassessed'])}</button></li>)}</ul>}
                  </section>
                  {stage.task && <section><h4>{t('学习与练习')}</h4><MarkdownContent content={stage.task} /></section>}
                  {(!!resources.length || !proposal && !!recommended.length) && <section><h4>{t('课程与资料')}</h4>
                    {!proposal && <CourseLinks links={recommended} />}
                    <Materials resources={resources} />
                  </section>}
                  {!proposal && <>
                    {!!stageSubmissions.length && <section><h4>{t('作答记录')}</h4>
                      {stageSubmissions.map(item => <TaskRow key={item.id} task={item} openTask={openPathTask} />)}
                    </section>}
                    {(!!stagePractice.length || canPrepareTask) && <section><h4>{t('练习任务')}</h4>
                      {stagePractice.map(item => <TaskRow key={item.id} task={item} openTask={openPathTask} />)}
                      {canPrepareTask && (latestFailedTask
                        ? <button className="um-agent-button" onClick={() => requestRemedialTask(stage, latestFailedTask)}>{t('复盘并换题再测')}</button>
                        : <button className="um-agent-button" onClick={() => ask(
                          t('帮我为「{0}」准备一道练习题', { 0: stage.title }), { stage_id: stage.id })}>{t('请小宇准备练习')}</button>)}
                    </section>}
                  </>}
                </div>
              </details>
            </li>;
          })}</ol>}
          {!proposal && !!otherSubmissions.length && <details className="um-path-disclosure">
            <summary>{t('其他作答')}<CaretDown size={14} /></summary>
            <div className="um-path-disclosure-items">{otherSubmissions.map(item => <TaskRow key={item.id} task={item} openTask={openPathTask} />)}</div>
          </details>}
          {!proposal && courses.some(link => !link.stageId) && <section className="um-path-block">
            <h3>{t('项目对话中的课程')}</h3><CourseLinks links={courses.filter(link => !link.stageId)} />
          </section>}
          {taskQuery.isError && <p role="alert">{t('任务暂时无法读取。')} <button className="um-agent-button" onClick={() => void taskQuery.refetch()}>{t('重试')}</button></p>}
          {!proposal && <details className="um-path-settings">
            <summary>{t('项目设置')}<CaretDown size={14} /></summary>
            {reminder()}
            {project.status === 'active' && <div className="um-path-actions">
              <button className="um-agent-button" disabled={busy} onClick={() => void act('pause')}>{t('暂停学习')}</button>
              <button className="um-agent-button" onClick={() => show('report')}>{t(allDone ? '查看学习成果报告' : '提前结束学习')}</button>
            </div>}
            {!!unassignedResources.length && <details className="um-path-setting-section">
              <summary>{t('项目资料')}<CaretDown size={14} /></summary>
              <div className="um-path-disclosure-items"><Materials resources={unassignedResources} /></div>
            </details>}
          </details>}
          {!proposal && project.memory_connectors &&
            <LearningMemorySources key={`sources:${project.project_id}`} projectId={project.project_id} />}
          {!proposal && !stages.length && !project.instructions.trim() && <details className="um-path-sample">
            <summary>{t('体验函数基础样板')}</summary><button className="um-agent-button" disabled={busy} onClick={() => void setupSample()}>{t('接入样板')}</button>
          </details>}
        </>}
      </>}
    </div>
    {(view.kind === 'path' || view.kind === 'proposal' || report) && <footer className="um-path-footer">
      {report ? <>
        {project.status === 'completed' ? <button className="um-agent-button" disabled={busy} onClick={() => void act('resume')}>{t('恢复继续学习')}</button> :
          <button className="um-agent-button um-agent-button-primary" disabled={busy || loadingTasks || taskQuery.isError} onClick={() => void act('complete', { review_at: reviewAt })}>{t(allDone ? '确认结项' : '确认结束学习')}<Check size={16} /></button>}
        <button className="um-agent-button" onClick={() => show('path')}>{t(project.status === 'completed' ? '回看路径明细' : '返回路径视图')}</button>
      </> : proposal ? <>
        <button className="um-agent-button um-agent-button-primary" disabled={busy} onClick={() => void act('accept')}>{t(stages.length ? '采用调整' : '采用这条路径')}<ArrowRight size={16} /></button>
        <button className="um-agent-button" onClick={() => prefill(t('我想微调一下学习路径：'))}>{t('微调路径')}</button>
        {!!stages.length && <button className="um-agent-button" disabled={busy} onClick={() => void act('reject')}>{t('保留原安排')}</button>}
      </> : pending ? <button className="um-agent-button um-agent-button-primary" onClick={() => show('proposal')}>{t('查看待确认路径')}<ArrowRight size={16} /></button>
        : project.status === 'completed' || allDone ? <button className="um-agent-button um-agent-button-primary" onClick={() => show('report')}>{t('查看学习成果报告')}<ArrowRight size={16} /></button>
        : project.status === 'paused' ? <button className="um-agent-button um-agent-button-primary" disabled={busy} onClick={() => void act('resume')}>{t('恢复学习')}<ArrowRight size={16} /></button>
        : nextStage ? <button className="um-agent-button um-agent-button-primary" disabled={busy || loadingTasks || taskQuery.isError} onClick={() => void continueStage()}>
          {nextTask ? taskAction(nextTask, nextTaskIsRemedial ? '打开巩固练习' : '打开当前练习')
            : t(nextFailure ? '复盘并换题再测' : '开始本阶段学习')}<ArrowRight size={16} /></button>
        : pendingDiagnostic ? <button className="um-agent-button um-agent-button-primary" onClick={() => openTask(pendingDiagnostic.id)}>{taskAction(pendingDiagnostic, '打开摸底小测')}<ArrowRight size={16} /></button>
        : latestDiagnostic ? <button className="um-agent-button um-agent-button-primary" onClick={() => generatePath(latestDiagnostic)}>{t('生成学习路径')}<ArrowRight size={16} /></button>
        : <button className="um-agent-button um-agent-button-primary" disabled={!!plannedGoal && (loadingTasks || taskQuery.isError)} onClick={() => plannedGoal
          ? ask(t('请根据这个项目的目标和已有学习记录，帮我确定起点和学习路径。')) : prefill(t('我想系统学习'))}>
          {t(plannedGoal ? '请小宇制定路径' : '告诉小宇学习目标')}<ArrowRight size={16} />
        </button>}
    </footer>}
  </section>;
}
