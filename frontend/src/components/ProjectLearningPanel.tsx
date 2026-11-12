import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import * as Dialog from '@radix-ui/react-dialog';
import { ArrowRight, BookOpen, CalendarBlank, Clock, FolderOpen, TreeStructure, X } from '@phosphor-icons/react';
import { toast } from 'sonner';
import api from '@/lib/api';
import { queryClient } from '@/lib/queryClient';
import { useAuthStore } from '@/store/useAuthStore';
import { learningKey, learningUrl, useProjectLearning, type ProjectLearning } from '@/lib/projectLearning';
import { useXiaoYuChat } from '@/pages/xiaoyu/xiaoYuChatContext';
import '@/styles/project-learning.css';
import { LearningLibraryPanel } from './LearningLibraryPanel';
import { LearningKnowledgePanel } from './LearningKnowledgePanel';
import { Switch } from './ui/switch';
import { LearningTasksPanel } from './LearningTasksPanel';

const statusLabels = { preparing: '了解目标', active: '学习中', paused: '已暂停', completed: '已结束' };
const assistanceLabels: Record<string, string> = { independent: '独立完成', hint: '获得提示', guided: '逐步引导', unknown: '帮助程度待了解' };

export function ProjectLearningContent({ knowledgeOnly = false, onStart }: { knowledgeOnly?: boolean; onStart?: () => void }) {
  const { chat, openingProject, activate } = useXiaoYuChat();
  useEffect(activate, [activate]);
  const userId = useAuthStore(s => s.user?.id);
  const projectId = chat.projectId;
  const query = useProjectLearning(projectId);
  const [busy, setBusy] = useState(false);
  const [resourceQuery, setResourceQuery] = useState('');
  const [candidates, setCandidates] = useState<{ title: string; url: string; summary: string }[]>([]);
  const navigate = useNavigate();
  const data = query.data;
  const key = learningKey(userId, projectId);
  const start = (text: string) => {
    chat.setInput(text);
    onStart?.();
    navigate('/xiaoyu');
  };
  const act = async (action: string, enabled?: boolean) => {
    if (!data || !projectId || busy) return;
    setBusy(true);
    try {
      const response = await api.patch<ProjectLearning>(`/ai/projects/${projectId}/learning/`, { action, enabled, revision: data.revision });
      queryClient.setQueryData(key, response.data);
    } catch { toast.error('安排未更新，请重新查看最新状态后重试。'); void query.refetch(); }
    finally { setBusy(false); }
  };
  const findResource = async (url?: string) => {
    if (!projectId || busy || (!url && !resourceQuery.trim())) return;
    setBusy(true);
    try {
      const { data: result } = await api.post(`/ai/projects/${projectId}/learning/`, url ? { url } : { query: resourceQuery.trim() });
      if (url) { await query.refetch(); toast.success('已读取原文，小宇可在后续规划中引用。'); }
      else setCandidates(result.candidates || []);
    } catch { toast.error('资料暂时无法读取，请换一个公开来源或在对话中补充材料。'); }
    finally { setBusy(false); }
  };
  if (openingProject) return <p className="um-learning-notice" role="status">正在打开学习项目…</p>;
  if (!projectId) return (
    <div className="um-learning-empty">
      <FolderOpen size={36} weight="duotone" aria-hidden="true" />
      <h2>从一个学习项目开始</h2>
      <Link className="um-agent-button um-agent-button-primary" to="/xiaoyu?new=project" onClick={onStart}>创建学习项目 <ArrowRight size={16} /></Link>
    </div>
  );
  if (query.isPending) return <p className="um-learning-notice" role="status">正在读取学习安排…</p>;
  if (query.isError || !data) return <div className="um-learning-notice" role="alert"><p>学习安排暂时无法读取。</p><button className="um-agent-button" onClick={() => void query.refetch()}>重新读取</button></div>;
  const stages = data.plan.stages || [];
  const current = stages.find(stage => stage.id === data.current_stage);
  const guidance = data.teaching_guidance;
  const feedback = guidance?.feedback || data.task_progress?.feedback || data.feedback;
  const nextAction = guidance?.next_action || (data.task_progress?.feedback ? data.task_progress.next_action : data.next_action);
  const scheduledAt = data.status === 'paused' ? data.resume_at : data.followup_at;
  const resources = new Map(data.resources.map(item => [item.id, item]));
  return <div className="um-learning-content">
    <header className="um-learning-summary">
      <div>{knowledgeOnly && <p>当前目标的知识关系</p>}<h2>{data.name}</h2></div>
      <span className="um-learning-status" data-status={data.status}>{data.planning_enabled ? statusLabels[data.status] : '自由对话'}</span>
    </header>
    {(data.plan.goal || data.instructions) && <p className="um-learning-goal">{data.plan.goal || data.instructions}</p>}
    {!knowledgeOnly && data.planning_enabled && <div className="um-learning-preferences">
      <label>主动提醒<Switch checked={data.reminders_enabled} disabled={busy} onCheckedChange={enabled => void act('reminders', enabled)} /></label>
    </div>}
    {(data.planning_enabled || knowledgeOnly) && <>
    {!knowledgeOnly && <>
      <div className="um-learning-schedule">
        {!!data.plan.weekly_minutes && <span><Clock size={15} />每周 {data.plan.weekly_minutes} 分钟</span>}
        {data.plan.deadline && <span><CalendarBlank size={15} />目标日期 {data.plan.deadline}</span>}
      </div>
      <section className="um-learning-next">
        <span>下一步{current && ` · ${current.title}`}</span>
        <h3>{nextAction || '和小宇明确学习目标与起点'}</h3>
        {feedback && <p>{feedback}</p>}
        <button className="um-agent-button um-agent-button-primary"
          disabled={data.status === 'paused' || data.status === 'completed'}
          onClick={() => start(nextAction ? `请读取当前项目实际任务与教学建议，接续下一步：${nextAction}。需要补救或复测时先读取原任务结果，说明依据，再准备相应的新任务；不要代答或把模型评分当成已独立验证的掌握。` : '请结合这个项目的目标与要求，了解我的起点，形成阶段路径并开始第一段学习。')}>
          让小宇准备下一步 <ArrowRight size={15} />
        </button>
        {guidance?.reason && <details><summary>这次安排的依据</summary><p>{guidance.reason}</p>{guidance.stalled && <p>目前这一步仍有卡点，先调整讲解或任务，再继续检验。</p>}</details>}
      </section>
      <div className="um-learning-plan-tools">
        <Link to={learningUrl('/knowledge-tree', projectId, chat.conversationId)}><TreeStructure size={16} />知识关系</Link>
        <Link to={learningUrl('/courses', projectId, chat.conversationId)}><BookOpen size={16} />课程与材料</Link>
        <div className="um-learning-controls">
          <button className="um-agent-button" disabled={busy || data.status === 'preparing'} onClick={() => void act(data.status === 'paused' || data.status === 'completed' ? 'resume' : 'pause')}>{data.status === 'paused' || data.status === 'completed' ? '恢复学习' : '暂停学习'}</button>
          {data.status === 'active' && <button className="um-agent-button" disabled={busy} onClick={() => void act('complete')}>结束当前目标</button>}
        </div>
      </div>
      {scheduledAt && <p className="um-learning-time">{data.status === 'paused' ? '预计恢复' : '下次跟进'}：{new Date(scheduledAt).toLocaleString('zh-CN')}{data.reminders_enabled && <><br />{data.followup_text}</>}</p>}
      {data.pending_plan.plan && <section className="um-learning-proposal"><h3>待商量的计划调整</h3><p>{data.pending_plan.reason}</p><p>目标：{data.pending_plan.plan.goal}</p>{data.pending_plan.knowledge && <p>知识地图：{data.pending_plan.knowledge.title} · 版本 {data.pending_plan.knowledge.revision}<br />目标范围：{data.pending_plan.knowledge.targets.join('、')}<br />学习深度：{data.pending_plan.knowledge.depth === 'transfer' ? '迁移应用' : '理解与应用'}</p>}{!data.pending_plan.knowledge && data.knowledge?.path && <p>本方案不再绑定知识地图。</p>}<p>每周投入：{data.pending_plan.plan.weekly_minutes || '待确定'} 分钟；期限：{data.pending_plan.plan.deadline || '未设定'}</p><ol>{data.pending_plan.plan.stages.map(stage => <li key={stage.id}>{stage.title}：{stage.outcome}</li>)}</ol><div className="um-learning-controls"><button className="um-agent-button um-agent-button-primary" disabled={busy} onClick={() => void act('accept')}>接受这个方案</button><button className="um-agent-button" disabled={busy} onClick={() => void act('reject')}>保留原安排</button></div></section>}
    </>}
    {!knowledgeOnly && <LearningTasksPanel key={`tasks:${projectId}`} project={data} onStudy={start} />}
    {knowledgeOnly && <LearningKnowledgePanel key={`knowledge:${projectId}`} project={data} onStudy={start} />}
    <section><h3>{knowledgeOnly ? '阶段与前置关系' : '阶段路径'}</h3>{!stages.length ? <p className="um-learning-muted">暂无阶段安排</p> : <ol className="um-learning-stages">{stages.map((stage, index) => <li key={stage.id} data-current={stage.id === data.current_stage}><span className="um-learning-stage-number">{index + 1}</span><div><h4>{stage.title}{stage.id === data.current_stage && <small>当前阶段</small>}</h4><p>{stage.outcome}</p>{stage.prerequisites.length > 0 && <p className="um-learning-muted">前置：{stage.prerequisites.map(id => stages.find(item => item.id === id)?.title || id).join('、')}</p>}{stage.task && <p>学习活动：{stage.task}</p>}<ul className="um-learning-sources">{stage.sources.map(id => { const resource = resources.get(id); return resource ? <li key={id}>{resource.source_kind === 'unimind_original' ? resource.title : <a href={resource.url} target="_blank" rel="noreferrer">{resource.title}</a>}</li> : null; })}</ul><button className="um-learning-text-button" onClick={() => start(`我想从“${stage.title}”继续，请先结合已有表现判断起点，再安排本次学习。`)}>围绕这一段学习</button></div></li>)}</ol>}</section>
    {!knowledgeOnly && <details className="um-learning-evidence"><summary>反馈与安排的依据</summary>{data.events.filter(event => event.kind === 'progress' || event.kind === 'plan' || event.kind === 'followup').map(event => <article key={event.id}><time>{new Date(event.created_at).toLocaleString('zh-CN')}</time>{event.delivery && <p className="um-learning-muted">跟进已保存到站内 · {event.delivery.read === null ? '阅读状态不可用' : event.delivery.read ? '已读' : '未读'} · {event.delivery.responded ? '已收到后续回应' : '等待反馈'}</p>}{event.source && <blockquote>{event.source.text}</blockquote>}<p>{String(event.content.observation || event.content.text || event.content.reason || '阶段安排')}</p>{Boolean(event.content.assistance) && <p className="um-learning-muted">{assistanceLabels[String(event.content.assistance)]}</p>}{Boolean(event.content.strategy) && <p>采用的方法：{String(event.content.strategy)}（待后续表现检验）</p>}</article>)}{!data.events.some(event => event.kind === 'progress' || event.kind === 'plan' || event.kind === 'followup') && <p>暂无学习记录</p>}</details>}
    <section><h3>学习资料与来源</h3>{data.resources.map(resource => <details className="um-learning-resource" key={resource.id}><summary>{resource.title}</summary><>{resource.source_kind === 'unimind_original' ? <p>UniMind 原创内容 · 版本快照</p> : <a href={resource.url} target="_blank" rel="noreferrer">打开原文</a>}</><p className="um-learning-muted">{resource.source_kind === 'unimind_original' ? '快照创建于 ' : '读取于 '}{new Date(resource.read_at).toLocaleString('zh-CN')}{resource.library_revision && ` · 资料库版本 ${resource.library_revision}`}<br />{[resource.domain, resource.topic, resource.level, resource.edition].filter(Boolean).join(' · ')}</p><p>{resource.excerpt}</p></details>)}<form className="um-learning-search" onSubmit={event => { event.preventDefault(); void findResource(); }}><label htmlFor="learning-resource-search">查找公开学习资料</label><div><input id="learning-resource-search" value={resourceQuery} maxLength={300} onChange={event => setResourceQuery(event.target.value)} placeholder="输入关键词" /><button className="um-agent-button" disabled={busy || !resourceQuery.trim()}>查找</button></div></form>{candidates.map(item => <article className="um-learning-candidate" key={item.url}><a href={item.url} target="_blank" rel="noreferrer">{item.title}</a><p>{item.summary}</p><button className="um-agent-button" disabled={busy} onClick={() => void findResource(item.url)}>读取原文加入项目</button></article>)}</section>
    <LearningLibraryPanel key={`library:${projectId}`} project={data} onStudy={start} />
    </>}
  </div>;
}

export function ProjectLearningDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (value: boolean) => void }) {
  return <Dialog.Root open={open} onOpenChange={onOpenChange}>
    <Dialog.Portal>
      <Dialog.Overlay className="um-agent-project-overlay" />
      <Dialog.Content className="um-native-agent um-learning-dialog">
        <header className="um-learning-dialog-header">
          <Dialog.Title><BookOpen size={18} />学习安排</Dialog.Title>
          <Dialog.Close asChild><button className="um-agent-icon-button" aria-label="关闭学习安排"><X size={18} /></button></Dialog.Close>
        </header>
        <Dialog.Description className="sr-only">查看项目阶段、下一步、学习依据和跟进安排。</Dialog.Description>
        <div className="um-learning-dialog-body"><ProjectLearningContent onStart={() => onOpenChange(false)} /></div>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
}


export function ProjectLearningResume() {
  const { chat, openingProject } = useXiaoYuChat();
  const { data } = useProjectLearning(chat.projectId);
  if (!data?.planning_enabled || openingProject) return null;
  const feedback = data.teaching_guidance?.feedback || data.task_progress?.feedback || data.feedback;
  const nextAction = data.teaching_guidance?.next_action || data.task_progress?.next_action || data.next_action;
  return <div className="um-learning-resume" role="status"><div><span>{data.name} · {statusLabels[data.status]}</span><p>{feedback || '小宇会结合你的目标和基础，安排可以开始的一段学习。'}</p>{nextAction && <p className="um-learning-muted">下一步：{nextAction}</p>}</div>{nextAction && data.status === 'active' && <button className="um-agent-button" onClick={() => chat.setInput(`请读取当前项目实际任务与教学建议，继续下一步：${nextAction}。先核对原作答与评价依据，需要时安排补救或不同内容的复测，不替我完成任务。`)}>继续学习</button>}</div>;
}
