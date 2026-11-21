import { useEffect, useId, useMemo, useRef, useState } from 'react';
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
import { LearningLibraryPanel } from './LearningLibraryPanel';
import { LearningTaskDetail } from './LearningTasksPanel';
import type { LearningWorkspace } from './LearningWorkspace';
import { MarkdownContent } from './MarkdownContent';
import { Switch } from './ui/switch';
import '@/styles/learning-workspace.css';
import '@/styles/learning-path-canvas.css';

type StageState = 'passed' | 'current' | 'remediate' | 'upcoming';
type CourseLink = { href: string; title: string; stageId?: string };

const stageLabels = { passed: '已攻克', current: '进行中', remediate: '补救中', upcoming: '待学习' };
const taskLabels = { ready: '待作答', processing: '批改中', completed: '已批改', partial: '批改未全部完成', failed: '批改待重试', unavailable: '内容不可用' };
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

function StageGraph({ stages, state, select }: {
  stages: LearningStage[]; state: (stage: LearningStage) => StageState; select: (id: string) => void;
}) {
  const id = useId();
  const rows: LearningStage[][] = [];
  const depth = new Map<string, number>();
  for (const stage of stages) {
    const level = Math.max(0, ...stage.prerequisites.map(parent => (depth.get(parent) ?? -1) + 1));
    depth.set(stage.id, level);
    (rows[level] ??= []).push(stage);
  }
  const width = Math.max(360, ...rows.map(row => row.length * 116));
  const positions = new Map(rows.flatMap((row, y) => row.map((stage, x) => [stage.id, {
    x: width * (x + 0.5) / row.length, y: 22 + y * 54, width: Math.min(162, width / row.length - 12),
  }] as const)));
  return <div className="um-path-graph">
    <svg viewBox={`0 0 ${width} ${rows.length * 54 - 8}`} style={{ minWidth: Math.min(width, 480) }}
      role="group" aria-label={t('学习阶段前置关系')}>
      <defs><marker id={id} markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0 0L6 3L0 6Z" fill="context-stroke" /></marker></defs>
      {stages.flatMap(stage => stage.prerequisites.map(prerequisite => {
        const from = positions.get(prerequisite);
        if (!from) return null;
        const to = positions.get(stage.id)!;
        const mid = (from.y + to.y) / 2;
        const unlocked = stage.prerequisites.every(parent => stages.some(item => item.id === parent && state(item) === 'passed'));
        return <path className="um-path-edge" data-unlocked={unlocked} key={`${prerequisite}:${stage.id}`} markerEnd={`url(#${id})`}
          d={`M${from.x} ${from.y + 14} C${from.x} ${mid} ${to.x} ${mid} ${to.x} ${to.y - 16}`} />;
      }))}
      {stages.map(stage => {
        const position = positions.get(stage.id)!;
        const status = state(stage);
        const maxChars = Math.floor((position.width - 20) / 12);
        const title = [...stage.title].length > maxChars ? [...stage.title].slice(0, maxChars - 1).join('') + '…' : stage.title;
        return <g className="um-path-node" data-state={status} role="button" tabIndex={0} key={stage.id}
          aria-label={`${stage.title} · ${t(stageLabels[status])}`} onClick={() => select(stage.id)}
          onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(stage.id); } }}>
          <title>{stage.title}</title>
          <rect x={position.x - position.width / 2} y={position.y - 14} width={position.width} height="28" rx="8" />
          <text x={position.x} y={position.y} dominantBaseline="central" textAnchor="middle">{status === 'passed' ? '✓ ' : ''}{title}</text>
        </g>;
      })}
    </svg>
  </div>;
}

function TaskRow({ task, openTask }: { task: LearningTask; openTask: (id: string) => void }) {
  const status = task.status !== 'completed' ? taskLabels[task.status] : task.purpose === 'diagnostic' ? '摸底已完成' : passedLearningTask(task) ? '已通过' : '未通过';
  return <button type="button" className="um-path-task" onClick={() => openTask(task.id)}>
    <span>{task.title}<small>{t(status)}{task.summary?.max_score ? ` · ${task.summary.total_score}/${task.summary.max_score}` : ''}</small></span><ArrowRight size={15} />
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
  const [node, setNode] = useState('');
  const [highlightedStage, setHighlightedStage] = useState('');
  const [library, setLibrary] = useState(false);
  const [fallbackNow] = useState(() => Date.now());
  const scroll = useRef<HTMLDivElement>(null);
  const stageCards = useRef(new Map<string, HTMLDetailsElement>());
  const taskId = view.kind === 'task' ? view.id : undefined;
  useEffect(() => { if (scroll.current) scroll.current.scrollTop = 0; }, [view.kind, taskId]);
  const courses = useMemo(() => project && sidebar.visible ? conversationCourses(messages, project, conversationId, tasks) : [],
    [messages, project, conversationId, tasks, sidebar.visible]);

  if (openingProject || (query.fetchStatus === 'fetching' && !project)) return <p className="um-path-loading" role="status">{t('正在打开学习项目…')}</p>;
  if (query.isError && !project) return <p className="um-path-loading" role="alert">{t('学习安排暂时无法读取。')} <button className="um-agent-button" onClick={() => void query.refetch()}>{t('重试')}</button></p>;
  if (!project || (!project.planning_enabled && view.kind !== 'knowledge')) return <div className="um-path-empty">
    <TreeStructure size={28} /><h2>{t('在项目中制定学习路径')}</h2>
    <p>{t('新建学习项目后，在对话里告诉小宇你想学什么。')}</p>
    <Link className="um-agent-button um-agent-button-primary" to="/xiaoyu?new=project">{t('新建学习项目')}</Link>
    {project && <button className="um-agent-button" onClick={() => show('knowledge')}>{t('查看知识关系')}</button>}
  </div>;

  const stages = project.plan.stages || [];
  const pending = project.pending_plan.plan;
  const proposal = view.kind === 'proposal' && !!pending;
  const visibleStages = proposal ? pending.stages : stages;
  const activeTasks = tasks.filter(task => task.is_current !== false);
  const diagnostics = tasks.filter(task => task.purpose === 'diagnostic' && (task.is_current !== false || task.exam_id));
  const assessed = tasks.filter(task => task.status !== 'unavailable' && task.exam_id && task.summary?.graded_count
    && (task.is_current !== false || (task.purpose === 'diagnostic' && !task.stage_id)));
  const latestDiagnostic = [...diagnostics].reverse().find(task => task.status === 'completed' && task.summary?.max_score);
  const pendingDiagnostic = [...diagnostics].reverse().find(task => ['ready', 'processing', 'failed', 'partial'].includes(task.status));
  const diagnosticIds = new Set(diagnostics.map(task => task.id));
  const diagnosticRequest = project.events.find(event => event.kind === 'task' && diagnosticIds.has(String(event.content.task_id)))?.source?.text;
  const goal = (proposal ? pending.goal : project.plan.goal) || project.instructions || diagnosticRequest || project.name;
  const unassignedResources = project.resources.filter(resource => !stages.some(stage => stage.sources.includes(resource.id)));
  const newestTasks = [...activeTasks].reverse();
  const stageFailure = (stageId: string) => completedStages.has(stageId) ? undefined :
    newestTasks.find(task => task.stage_id === stageId && failedLearningTask(task));
  const nextFailure = nextStage && stageFailure(nextStage.id);
  const nextTask = nextStage && (nextFailure ? findRemedialTask(activeTasks.filter(task => task.stage_id === nextStage.id), nextFailure) :
    newestTasks.find(task => task.stage_id === nextStage.id && playableLearningTask(task)));
  const nextTaskIsRemedial = nextTask && (nextFailure || nextTask.purpose === 'recheck' || nextTask.source_task_id);
  const state = (stage: LearningStage): StageState => {
    if (!proposal && completedStages.has(stage.id)) return 'passed';
    if (!proposal && stageFailure(stage.id)) return 'remediate';
    if (!proposal && stage.id === nextStage?.id && project.status === 'active') return 'current';
    if (proposal && diagnostics.some(task => task.stage_id === stage.id && passedLearningTask(task))) return 'passed';
    return 'upcoming';
  };
  const selectStage = (stageId: string) => {
    setHighlightedStage(stageId);
    setExpanded(previous => ({ ...previous, [stageId]: true }));
    stageCards.current.get(stageId)?.scrollIntoView({ block: 'nearest' });
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
  const percent = stages.length ? Math.round(100 * completedStages.size / stages.length) : 0;
  const progressLabel = t('{0}/{1} 阶段已攻克 · {2}%', { 0: completedStages.size, 1: stages.length, 2: percent });
  const task = tasks.find(item => item.id === taskId);
  const loadingTasks = project.planning_enabled && taskQuery.isPending;
  const report = view.kind === 'report';
  const statusLabel = proposal ? '待确认' : report || project.status === 'completed' ? (project.status === 'completed' ? '目标已完成' : '待结项')
    : project.status === 'active' ? '学习中' : project.status === 'paused' ? '已暂停' : '目标与起点';

  return <section className="um-path-canvas" aria-label={t('学习路径画布')}>
    <div className="um-path-scroll" ref={scroll}>
      {view.kind === 'task' ? <>
        <button className="um-agent-button" onClick={() => show(view.back)}><ArrowLeft size={16} />{t('返回')}</button>
        {task ? <LearningTaskDetail active={sidebar.visible} project={project} task={task} tasks={tasks} refresh={refresh}
          onSelect={id => { if (id) openTask(id); }} onStudy={ask} /> : loadingTasks ? <p role="status">{t('正在读取任务…')}</p> :
          taskQuery.isError ? <p role="alert">{t('任务暂时无法读取。')} <button onClick={() => void taskQuery.refetch()}>{t('重试')}</button></p> : <p>{t('这项任务已不可用。')}</p>}
        {task?.purpose === 'diagnostic' && task.status === 'completed' && project.status === 'preparing' && !pending &&
          <button className="um-agent-button um-agent-button-primary" onClick={() => ask(t('根据我的摸底结果制定学习路径吧'), { task_id: task.id })}>{t('生成学习路径')}<ArrowRight size={16} /></button>}
        {allDone && <button className="um-agent-button um-agent-button-primary" onClick={() => show('report')}>{t('查看学习成果报告')}<ArrowRight size={16} /></button>}
      </> : view.kind === 'knowledge' ? <>
        <button className="um-agent-button" onClick={() => show(pending ? 'proposal' : 'path')}><ArrowLeft size={16} />{t('返回学习路径')}</button>
        <LearningKnowledgeView project={project} selected={node} onSelect={setNode} tasks={tasks} tasksLoading={loadingTasks} onStudy={ask} onTask={openTask} />
      </> : <>
        <header className="um-path-overview">
          <div className="um-path-heading"><span>{project.name}</span><span className="um-path-pill" data-status={project.status}>{t(statusLabel)}</span></div>
          <h2>{report ? t('学习成果总结报告') : goal}</h2>
          {report && <p>{goal}</p>}
          {proposal && latestDiagnostic && <span className="um-path-pill">{t('摸底')} · {latestDiagnostic.summary!.total_score}/{latestDiagnostic.summary!.max_score}</span>}
          {!proposal && !!stages.length && <div className="um-path-progress"><progress value={completedStages.size} max={stages.length} aria-label={progressLabel} /><strong>{progressLabel}</strong></div>}
          {!report && visibleStages.length > 0 && <StageGraph stages={visibleStages} state={state} select={selectStage} />}
        </header>

        {report ? <>
          <section className="um-path-block"><h3>{t('摸底与阶段成果')}</h3>
            {assessed.filter(task => task.purpose === 'diagnostic').map(task => <TaskReview key={task.id} task={task} diagnostics openTask={openTask} />)}
            {!assessed.some(task => task.purpose === 'diagnostic') && <p>{t('本轮没有已评分的摸底小测。')}</p>}
            <ol className="um-path-summary-list">{stages.map(stage => {
              const scores = assessed.filter(task => task.stage_id === stage.id && task.purpose !== 'diagnostic');
              const best = scores.reduce<LearningTask | undefined>((best, task) => !best || task.summary!.total_score / task.summary!.max_score > best.summary!.total_score / best.summary!.max_score ? task : best, undefined);
              return <li key={stage.id}><span>{stage.title}</span><strong>{completedStages.has(stage.id) ? t('已攻克') : t('待通过')}{best && ` · ${t('最佳')} ${best.summary!.total_score}/${best.summary!.max_score}`}</strong></li>;
            })}</ol>
          </section>
          <section className="um-path-block"><h3>{t('核心突破与错因复盘')}</h3>
            {completedStages.size > 0 && <ul className="um-path-summary-list">{stages.filter(stage => completedStages.has(stage.id)).map(stage =>
              <li key={stage.id}><strong>{stage.title}</strong><MarkdownContent content={stage.outcome} /></li>)}</ul>}
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
          {!proposal && !stages.length && <section className="um-path-block">
            <h3>{t('从哪里开始')}</h3>
            <ol className="um-path-steps"><li>{t('摸底定位起点')}</li><li>{t('生成定制路径')}</li><li>{t('分阶段攻克与结项')}</li></ol>
            {pendingDiagnostic && <TaskRow task={pendingDiagnostic} openTask={openTask} />}
            {latestDiagnostic && <TaskRow task={latestDiagnostic} openTask={openTask} />}
          </section>}
          {proposal && project.pending_plan.reason && <p className="um-path-reason">{project.pending_plan.reason}</p>}
          {proposal && stages.length > 0 && pending.knowledge_path?.version_id !== project.knowledge?.version_id &&
            <p className="um-path-reason">{t('采用新知识版本后，原作答和草稿可在历史任务中回看。')}</p>}
          {visibleStages.map((stage, index) => {
            const status = state(stage);
            const stageTasks = activeTasks.filter(task => task.stage_id === stage.id);
            const latestFailedTask = status === 'remediate' ? stageFailure(stage.id) : undefined;
            const stagePlayableTask = latestFailedTask ? findRemedialTask(stageTasks, latestFailedTask) : undefined;
            const resources = project.resources.filter(resource => stage.sources.includes(resource.id));
            const recommended = courses.filter(link => link.stageId === stage.id);
            const nodes = project.knowledge?.nodes.filter(item => stage.knowledge_nodes?.includes(item.id)) || [];
            const tag = ['快速巩固', '重点突破', '综合串联'].find(label => stage.task.includes(label))
              || (stage.prerequisites.length > 1 ? '综合串联' : status === 'passed' ? '快速巩固' : undefined);
            return <details key={`${proposal}:${stage.id}`} className="um-path-stage" data-state={status} data-highlighted={highlightedStage === stage.id || undefined}
              ref={element => { if (element) stageCards.current.set(stage.id, element); else stageCards.current.delete(stage.id); }}
              open={expanded[stage.id] ?? (proposal ? index === 0 : stage.id === nextStage?.id)}
              onToggle={event => {
                const value = event.currentTarget.open;
                if (value !== (expanded[stage.id] ?? (proposal ? index === 0 : stage.id === nextStage?.id))) {
                  setExpanded(previous => ({ ...previous, [stage.id]: value }));
                }
              }}>
              <summary><span className="um-path-state-dot">{status === 'passed' && <Check size={10} weight="bold" />}</span>
                <span className="um-path-stage-number">{String(index + 1).padStart(2, '0')}</span>
                <strong>{stage.title}</strong><small>{t(proposal ? tag || '计划阶段' : stageLabels[status])}</small><CaretDown size={14} />
              </summary>
              <div className="um-path-stage-content">
                <section><h4>{t('阶段目标与要点')}</h4><MarkdownContent content={stage.outcome} />
                  {stage.task && <MarkdownContent content={stage.task} />}
                  {!!stage.prerequisites.length && <p className="um-path-muted">{t('先学')} {visibleStages.filter(item => stage.prerequisites.includes(item.id)).map(item => item.title).join('、')}</p>}
                  {!proposal && !!nodes.length && <ul>{nodes.map(item => <li key={item.id}><button className="um-learning-text-button" onClick={() => { setNode(item.id); show('knowledge'); }}>
                    {item.title} · {t(knowledgeLabels[item.learning_status || 'unassessed'])}</button></li>)}</ul>}
                </section>
                {(!!resources.length || !proposal && !!recommended.length) && <section><h4>{t('推荐课程与资料')}</h4>
                  {!proposal && <CourseLinks links={recommended} />}
                  <Materials resources={resources} />
                </section>}
                {!proposal && <section><h4>{t('本阶段任务与作答')}</h4>
                  {stageTasks.map(item => <TaskRow key={item.id} task={item} openTask={openTask} />)}
                  {project.status === 'active' && (latestFailedTask ? <button className="um-agent-button um-agent-button-primary"
                    onClick={() => stagePlayableTask ? openTask(stagePlayableTask.id) : requestRemedialTask(stage, latestFailedTask)}>
                    {t(stagePlayableTask ? '开始补救练习' : '换题补救再测')}
                  </button> : <button className="um-agent-button" onClick={() => ask(
                    t('帮我为「{0}」准备一道练习题', { 0: stage.title }), { stage_id: stage.id })}>{t('请小宇出题')}</button>)}
                </section>}
              </div>
            </details>;
          })}
          {!proposal && courses.some(link => !link.stageId) && <section className="um-path-block">
            <h3>{t('配套课程切片')}</h3><CourseLinks links={courses.filter(link => !link.stageId)} />
          </section>}
          {taskQuery.isError && <p role="alert">{t('任务暂时无法读取。')} <button className="um-agent-button" onClick={() => void taskQuery.refetch()}>{t('重试')}</button></p>}
          {!proposal && <details className="um-path-settings">
            <summary>{t('项目设置')}<CaretDown size={14} /></summary>
            {reminder()}
            <div className="um-path-actions">
              {project.status === 'active' && <><button className="um-agent-button" disabled={busy} onClick={() => void act('pause')}>{t('暂停学习')}</button>
                <button className="um-agent-button" onClick={() => show('report')}>{t('提前结束目标')}</button></>}
              <button className="um-agent-button" onClick={() => show('knowledge')}>{t('知识关系')}</button>
            </div>
            {!!unassignedResources.length && <details><summary>{t('项目资料')}</summary><Materials resources={unassignedResources} /></details>}
            {!!tasks.length && <details><summary>{t('任务记录')}</summary>{tasks.map(item => <TaskRow key={item.id} task={item} openTask={openTask} />)}</details>}
            <details onToggle={event => setLibrary(event.currentTarget.open)}><summary>{t('跨项目资料与方法')}</summary>{library && <LearningLibraryPanel project={project} onStudy={ask} />}</details>
          </details>}
          {!proposal && !stages.length && !project.instructions.trim() && <details className="um-path-sample">
            <summary>{t('体验函数基础样板')}</summary><button className="um-agent-button" disabled={busy} onClick={() => void setupSample()}>{t('接入样板')}</button>
          </details>}
        </>}
      </>}
    </div>
    {(view.kind === 'path' || view.kind === 'proposal' || report) && <footer className="um-path-footer">
      {report ? <>
        {project.status === 'completed' ? <button className="um-agent-button" disabled={busy} onClick={() => void act('resume')}>{t('恢复继续学习')}</button> :
          <button className="um-agent-button um-agent-button-primary" disabled={busy || loadingTasks || taskQuery.isError} onClick={() => void act('complete', { review_at: reviewAt })}>{t('确认完成当前目标')}<Check size={16} /></button>}
        <button className="um-agent-button" onClick={() => show('path')}>{t(project.status === 'completed' ? '回看路径明细' : '返回路径视图')}</button>
      </> : proposal ? <>
        <button className="um-agent-button um-agent-button-primary" disabled={busy} onClick={() => void act('accept')}>{t(stages.length ? '确认调整，继续学习' : '确认路径，开始第 1 阶段')}<ArrowRight size={16} /></button>
        <button className="um-agent-button" onClick={() => prefill(t('我想微调一下学习路径：'))}>{t('微调路径')}</button>
        {!!stages.length && <button className="um-agent-button" disabled={busy} onClick={() => void act('reject')}>{t('保留原安排')}</button>}
      </> : project.status === 'completed' || allDone ? <button className="um-agent-button um-agent-button-primary" onClick={() => show('report')}>{t('查看学习成果报告')}<ArrowRight size={16} /></button>
        : pending ? <button className="um-agent-button um-agent-button-primary" onClick={() => show('proposal')}>{t('查看待确认路径')}<ArrowRight size={16} /></button>
        : project.status === 'paused' ? <button className="um-agent-button um-agent-button-primary" disabled={busy} onClick={() => void act('resume')}>{t('恢复学习')}<ArrowRight size={16} /></button>
        : nextStage ? <button className="um-agent-button um-agent-button-primary" disabled={busy || loadingTasks || taskQuery.isError} onClick={() => void continueStage()}>
          {t(nextTaskIsRemedial ? '开始补救练习' : nextTask ? '继续当前任务' : nextFailure ? '复盘并换题再测' : '开始本阶段学习')}<ArrowRight size={16} /></button>
        : pendingDiagnostic ? <button className="um-agent-button um-agent-button-primary" onClick={() => openTask(pendingDiagnostic.id)}>{t('打开摸底任务')}<ArrowRight size={16} /></button>
        : latestDiagnostic ? <button className="um-agent-button um-agent-button-primary" onClick={() => ask(t('根据我的摸底结果制定学习路径吧'), { task_id: latestDiagnostic.id })}>{t('生成学习路径')}<ArrowRight size={16} /></button>
        : <button className="um-agent-button um-agent-button-primary" onClick={() => prefill(t('我想系统学习'))}>{t('告诉小宇学习目标')}<ArrowRight size={16} /></button>}
    </footer>}
  </section>;
}
