import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import * as Dialog from '@radix-ui/react-dialog';
import { BookOpen, X } from '@phosphor-icons/react';
import { toast } from 'sonner';
import api from '@/lib/api';
import { queryClient } from '@/lib/queryClient';
import { useAuthStore } from '@/store/useAuthStore';
import { learningKey, learningUrl, useProjectLearning, type ProjectLearning } from '@/lib/projectLearning';
import { useXiaoYuChat } from '@/pages/xiaoyu/xiaoYuChatContext';
import '@/styles/project-learning.css';
import { LearningLibraryPanel } from './LearningLibraryPanel';
import { LearningKnowledgePanel } from './LearningKnowledgePanel';

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
  const act = async (action: string) => {
    if (!data || !projectId || busy) return;
    setBusy(true);
    try {
      const response = await api.patch<ProjectLearning>(`/ai/projects/${projectId}/learning/`, { action, revision: data.revision });
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
  if (!projectId) return <div className="um-learning-empty"><h2>从一个学习项目开始</h2><p>在小宇的项目目录中选择或创建项目，再由小宇接续目标、安排和进展。</p><Link to="/xiaoyu?new=project">创建学习项目</Link></div>;
  if (openingProject || query.isPending) return <p role="status">正在读取项目学习安排…</p>;
  if (query.isError || !data) return <div role="alert"><p>学习安排暂时无法读取，当前对话仍可保留。</p><button className="um-agent-button" onClick={() => void query.refetch()}>重新读取</button></div>;
  const stages = data.plan.stages || [];
  const current = stages.find(stage => stage.id === data.current_stage);
  const resources = new Map(data.resources.map(item => [item.id, item]));
  return <div className="um-learning-content">
    <header className="um-learning-summary"><div><p>{knowledgeOnly ? '当前目标的知识关系' : '当前学习项目'}</p><h2>{data.name}</h2></div><span className="um-learning-status">{statusLabels[data.status]}</span></header>
    <p className="um-learning-goal">{data.plan.goal || data.instructions || '和小宇聊聊你想学会什么。'}</p>
    {!knowledgeOnly && <>
      <section className="um-learning-next"><span>接下来</span><p>{data.feedback || (current ? `正在推进：${current.title}` : '先了解你的基础，准备可以开始的第一段学习。')}</p><strong>{data.next_action || '和小宇明确学习目标与起点'}</strong><button className="um-agent-button um-agent-button-primary" onClick={() => start(data.next_action ? `继续这个项目的学习：${data.next_action}` : '请结合这个项目的目标与要求，了解我的起点，形成阶段路径并开始第一段学习。')}>和小宇继续</button></section>
      <div className="um-learning-controls"><button className="um-agent-button" disabled={busy || data.status === 'preparing'} onClick={() => void act(data.status === 'paused' || data.status === 'completed' ? 'resume' : 'pause')}>{data.status === 'paused' || data.status === 'completed' ? '恢复学习' : '暂停学习'}</button>{data.status === 'active' && <button className="um-agent-button" disabled={busy} onClick={() => void act('complete')}>结束当前目标</button>}<Link to={learningUrl('/knowledge-tree', projectId, chat.conversationId)}>查看知识关系</Link><Link to={learningUrl('/courses', projectId, chat.conversationId)}>课程与材料</Link></div>
      {data.followup_at && <p className="um-learning-time">{data.status === 'paused' ? '预计恢复' : '下次跟进'}：{new Date(data.followup_at).toLocaleString('zh-CN')}<br />{data.followup_text}<br />可以直接告诉小宇调整时间或减少联系。</p>}
      {data.pending_plan.plan && <section className="um-learning-proposal"><h3>待商量的计划调整</h3><p>{data.pending_plan.reason}</p><p>目标：{data.pending_plan.plan.goal}</p>{data.pending_plan.knowledge && <p>知识地图：{data.pending_plan.knowledge.title} · 版本 {data.pending_plan.knowledge.revision}<br />目标范围：{data.pending_plan.knowledge.targets.join('、')}<br />学习深度：{data.pending_plan.knowledge.depth === 'transfer' ? '迁移应用' : '理解与应用'}</p>}{!data.pending_plan.knowledge && data.knowledge?.path && <p>本方案不再绑定知识地图。</p>}<p>每周投入：{data.pending_plan.plan.weekly_minutes || '待确定'} 分钟；期限：{data.pending_plan.plan.deadline || '未设定'}</p><ol>{data.pending_plan.plan.stages.map(stage => <li key={stage.id}>{stage.title}：{stage.outcome}</li>)}</ol><div className="um-learning-controls"><button className="um-agent-button um-agent-button-primary" disabled={busy} onClick={() => void act('accept')}>接受这个方案</button><button className="um-agent-button" disabled={busy} onClick={() => void act('reject')}>保留原安排</button></div></section>}
    </>}
    {knowledgeOnly && <LearningKnowledgePanel key={`knowledge:${projectId}`} project={data} onStudy={start} />}
    <section><h3>{knowledgeOnly ? '阶段与前置关系' : '阶段路径'}</h3>{!stages.length ? <p className="um-learning-muted">尚未形成阶段路径，由小宇结合目标和基础逐步准备。</p> : <ol className="um-learning-stages">{stages.map((stage, index) => <li key={stage.id} data-current={stage.id === data.current_stage}><span className="um-learning-stage-number">{index + 1}</span><div><h4>{stage.title}{stage.id === data.current_stage && <small>当前阶段</small>}</h4><p>{stage.outcome}</p>{stage.prerequisites.length > 0 && <p className="um-learning-muted">前置：{stage.prerequisites.map(id => stages.find(item => item.id === id)?.title || id).join('、')}</p>}{stage.task && <p>学习活动：{stage.task}</p>}<ul className="um-learning-sources">{stage.sources.map(id => { const resource = resources.get(id); return resource ? <li key={id}><a href={resource.url} target="_blank" rel="noreferrer">{resource.title}</a></li> : null; })}</ul><button className="um-learning-text-button" onClick={() => start(`我想从“${stage.title}”继续，请先结合已有表现判断起点，再安排本次学习。`)}>围绕这一段学习</button></div></li>)}</ol>}</section>
    {!knowledgeOnly && <details className="um-learning-evidence"><summary>展开反馈与安排的依据</summary>{data.events.filter(event => event.kind === 'progress' || event.kind === 'plan' || event.kind === 'followup').map(event => <article key={event.id}><time>{new Date(event.created_at).toLocaleString('zh-CN')}</time>{event.delivery && <p className="um-learning-muted">跟进已保存到站内 · {event.delivery.read === null ? '阅读状态不可用' : event.delivery.read ? '已读' : '未读'} · {event.delivery.responded ? '已收到后续回应' : '等待反馈'}（单独记录学习成果）</p>}{event.source && <blockquote>{event.source.text}</blockquote>}<p>{String(event.content.observation || event.content.text || event.content.reason || '阶段安排')}</p>{Boolean(event.content.assistance) && <p className="um-learning-muted">{assistanceLabels[String(event.content.assistance)]}</p>}{Boolean(event.content.strategy) && <p>采用的方法：{String(event.content.strategy)}（待后续表现检验）</p>}</article>)}{!data.events.some(event => event.kind === 'progress' || event.kind === 'plan' || event.kind === 'followup') && <p>还没有相关学习证据，后续会根据实际作答和成果补充。</p>}</details>}
    <section><h3>学习资料与来源</h3><p className="um-learning-muted">原文读取记录与教学有效性分别判断，有时效的内容还需核对适用日期。</p>{data.resources.map(resource => <details className="um-learning-resource" key={resource.id}><summary>{resource.title}</summary><a href={resource.url} target="_blank" rel="noreferrer">打开原文</a><p className="um-learning-muted">读取于 {new Date(resource.read_at).toLocaleString('zh-CN')}{resource.library_revision && ` · 资料库版本 ${resource.library_revision}`}<br />{[resource.domain, resource.topic, resource.level, resource.edition].filter(Boolean).join(' · ')}</p><p>{resource.excerpt}</p></details>)}<form className="um-learning-search" onSubmit={event => { event.preventDefault(); void findResource(); }}><label htmlFor="learning-resource-search">查找公开学习资料</label><div><input id="learning-resource-search" value={resourceQuery} maxLength={300} onChange={event => setResourceQuery(event.target.value)} placeholder="例如：大学 计算机组成 原理 开放课程" /><button className="um-agent-button" disabled={busy || !resourceQuery.trim()}>查找</button></div></form>{candidates.map(item => <article className="um-learning-candidate" key={item.url}><a href={item.url} target="_blank" rel="noreferrer">{item.title}</a><p>{item.summary}</p><button className="um-agent-button" disabled={busy} onClick={() => void findResource(item.url)}>读取原文加入项目</button></article>)}</section>
    <LearningLibraryPanel key={`library:${projectId}`} project={data} onStudy={start} />
  </div>;
}

export function ProjectLearningDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (value: boolean) => void }) {
  return <Dialog.Root open={open} onOpenChange={onOpenChange}><Dialog.Portal><Dialog.Overlay className="um-agent-project-overlay" /><Dialog.Content className="um-native-agent um-learning-dialog"><header className="um-learning-dialog-header"><Dialog.Title><BookOpen size={18} />学习安排</Dialog.Title><Dialog.Close asChild><button className="um-agent-icon-button" aria-label="关闭学习安排"><X size={18} /></button></Dialog.Close></header><Dialog.Description className="sr-only">查看项目阶段、下一步、学习依据和跟进安排。</Dialog.Description><ProjectLearningContent onStart={() => onOpenChange(false)} /></Dialog.Content></Dialog.Portal></Dialog.Root>;
}


export function ProjectLearningResume() {
  const { chat, openingProject } = useXiaoYuChat();
  const { data } = useProjectLearning(chat.projectId);
  if (!data || openingProject) return null;
  return <div className="um-learning-resume" role="status"><div><span>{data.name} · {statusLabels[data.status]}</span><p>{data.feedback || '小宇会结合你的目标和基础，安排可以开始的一段学习。'}</p>{data.next_action && <p className="um-learning-muted">下一步：{data.next_action}</p>}</div>{data.next_action && data.status === 'active' && <button className="um-agent-button" onClick={() => chat.setInput(`继续这个项目的学习：${data.next_action}`)}>继续学习</button>}</div>;
}
