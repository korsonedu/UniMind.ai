import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import api from '@/lib/api';
import { queryClient } from '@/lib/queryClient';
import { useAuthStore } from '@/store/useAuthStore';
import { learningKey, learningUrl, type ProjectLearning } from '@/lib/projectLearning';
import { Link } from 'react-router-dom';

interface Resource {
  source_kind?: string; id: number; url: string; title: string; excerpt: string; read_at: string;
  domain: string; topic: string; level: string; edition: string; revision: number; is_archived: boolean; versions?: { revision: number; created_at: string }[];
}
interface Evidence {
  project_id: number; conversation_id: string | null; source: string | null; observation: string; assistance: string;
}
interface Strategy {
  id: number; method: string; domain: string; topic: string; revision: number; is_retired: boolean; available: boolean;
  context: { goal?: string; stage?: string; outcome?: string }; source: Evidence;
  counts: { support: number; against: number; uncertain: number };
  reviews: { judgement: 'support' | 'against' | 'uncertain'; reason: string; evidence: Evidence }[];
}
interface Library { resources: Resource[]; strategies: Strategy[]; }
const judgements = { support: '支持观察', against: '相反观察', uncertain: '尚不确定' };
type Operation = Record<string, string | number>;

function ResourceItem({ resource, busy, act, reread, history }: {
  resource: Resource; busy: boolean; act: (data: Operation) => Promise<void>; reread: (resource: Resource) => Promise<void>; history: (resource: Resource, revision: number) => Promise<Resource | null>;
}) {
  const [snapshot, setSnapshot] = useState<Resource | null>(null);
  const [version, setVersion] = useState('');
  const [tags, setTags] = useState({ domain: resource.domain, topic: resource.topic, level: resource.level, edition: resource.edition });
  return <article className="um-learning-library-item"><h4>{resource.title} {resource.is_archived && <small>已归档</small>}</h4>
    <p className="um-learning-muted">{[resource.domain, resource.topic, resource.level, resource.edition].filter(Boolean).join(' · ') || '尚未归类'} · {resource.source_kind === 'unimind_original' ? '原创快照创建于 ' : '原文读取于 '}{new Date(resource.read_at).toLocaleString('zh-CN')}</p>
    <div className="um-learning-controls"><button className="um-agent-button" disabled={busy || resource.is_archived} onClick={() => void act({ kind: 'resource', action: 'attach', resource_id: resource.id })}>接入当前项目</button>{resource.source_kind !== 'unimind_original' && <><a href={resource.url} target="_blank" rel="noreferrer">原文</a><button className="um-learning-text-button" disabled={busy} onClick={() => void reread(resource)}>重新核验原文</button></>}<button className="um-learning-text-button" disabled={busy} onClick={() => void act({ kind: 'resource', action: resource.is_archived ? 'restore' : 'archive', resource_id: resource.id, revision: resource.revision })}>{resource.is_archived ? '恢复使用' : '归档'}</button></div>
    <details><summary>片段与适用范围</summary><p className="um-learning-library-excerpt">{resource.excerpt}</p><form onSubmit={event => { event.preventDefault(); void act({ kind: 'resource', action: 'update', resource_id: resource.id, revision: resource.revision, ...tags }); }}><div className="um-learning-library-fields">{(['domain', 'topic', 'level', 'edition'] as const).map((key, index) => <label key={key}>{['领域', '主题', '适用基础', '年份或版本'][index]}<input maxLength={key === 'topic' ? 200 : key === 'domain' ? 100 : 80} value={tags[key]} onChange={event => setTags(previous => ({ ...previous, [key]: event.target.value }))} /></label>)}</div><button className="um-agent-button" disabled={busy}>保存适用标签</button><p className="um-learning-muted">标签用于组织资料，不代表官方范围已核验。修改资料库不会替换其他项目已引用的快照。</p></form></details>
    <details><summary>回看历史版本</summary><label>历史版本<select aria-label="资料历史版本" value={version} disabled={busy} onChange={event => { const selected = event.target.value; setVersion(selected); if (!selected) setSnapshot(null); else void history(resource, Number(selected)).then(setSnapshot); }}><option value="">请选择版本</option>{resource.versions?.map(item => <option key={item.revision} value={item.revision}>版本 {item.revision} · {new Date(item.created_at).toLocaleString('zh-CN')}</option>)}</select></label>{snapshot && <div><h4>{snapshot.title}</h4><p className="um-learning-muted">{[snapshot.domain, snapshot.topic, snapshot.level, snapshot.edition].filter(Boolean).join(' · ')} · {snapshot.source_kind === 'unimind_original' ? '原创快照创建于 ' : '原文读取于 '}{new Date(snapshot.read_at).toLocaleString('zh-CN')}</p><p className="um-learning-library-excerpt">{snapshot.excerpt}</p></div>}<p className="um-learning-muted">这里只读回看，保留全部历史，列出最近 10 个版本；不替换当前资料或项目引用。</p></details>
  </article>;
}

export function LearningLibraryPanel({ project, onStudy }: { project: ProjectLearning; onStudy: (text: string) => void }) {
  const userId = useAuthStore(state => state.user?.id);
  const [tab, setTab] = useState<'resources' | 'strategies'>('resources');
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [domain, setDomain] = useState('');
  const [topic, setTopic] = useState('');
  const [sourceId, setSourceId] = useState('');
  const [eventId, setEventId] = useState('');
  const [busy, setBusy] = useState(false);
  const url = `/ai/projects/${project.project_id}/learning/library/`;
  const library = useQuery({ queryKey: ['learning-library', userId, project.project_id, query], enabled: !!userId,
    queryFn: ({ signal }) => api.get<Library>(url, { params: { query }, signal }).then(response => response.data) });
  const refresh = async () => { await Promise.all([
    queryClient.invalidateQueries({ queryKey: ['learning-library', userId] }),
    queryClient.invalidateQueries({ queryKey: learningKey(userId, project.project_id) }),
  ]); };
  const act = async (data: Operation) => {
    if (busy) return;
    setBusy(true);
    try {
      const response = await api.post(url, data);
      await refresh();
      toast.success(response.data.notice || (response.data.created === false && data.action === 'save' ? '已在资料库中，保留原记录。' : '已保存。'));
    } catch { toast.error('操作未完成，请重新读取最新记录后重试。'); void library.refetch(); }
    finally { setBusy(false); }
  };
  const reread = async (resource: Resource) => {
    if (busy) return;
    setBusy(true);
    try {
      const { data } = await api.post(`/ai/projects/${project.project_id}/learning/`, { url: resource.url });
      await api.post(url, { kind: 'resource', action: 'save', source_id: data.resource.id, revision: resource.revision });
      await refresh(); toast.success('已重新读取并更新我的资料库。其他项目仍保留原引用快照。');
    } catch { toast.error('原文未完成核验，已保留原资料。'); }
    finally { setBusy(false); }
  };
  const history = async (resource: Resource, revision: number) => {
    if (busy) return null;
    setBusy(true);
    try { return (await api.get<{ resource: Resource }>(url, { params: { resource_id: resource.id, revision } })).data.resource; }
    catch { toast.error('这个历史版本暂时无法读取。'); return null; }
    finally { setBusy(false); }
  };
  const events = project.events.filter(event => event.kind === 'progress' && event.source && event.content.strategy);
  return <section className="um-learning-library"><h3>跨项目积累与复用</h3><p className="um-learning-muted">只使用你自己的资料与教学记录。阅读日期、适用背景和后续表现分别保留。</p>
    <div className="um-learning-controls" role="group" aria-label="查看学习积累"><button className="um-agent-button" aria-pressed={tab === 'resources'} onClick={() => setTab('resources')}>我的资料库</button><button className="um-agent-button" aria-pressed={tab === 'strategies'} onClick={() => setTab('strategies')}>教学方法与后续观察</button></div>
    <form className="um-learning-search" onSubmit={event => { event.preventDefault(); setQuery(search.trim()); }}><label htmlFor="learning-library-query">按标题、领域或主题查找</label><div><input id="learning-library-query" maxLength={200} value={search} onChange={event => setSearch(event.target.value)} /><button className="um-agent-button">查找积累</button></div></form>
    <details className="um-learning-library-save"><summary>{tab === 'resources' ? '把本项目已读资料留下' : '留下本项目使用过的方法'}</summary><div className="um-learning-library-fields"><label>领域<input value={domain} maxLength={100} onChange={event => setDomain(event.target.value)} placeholder="如：高中数学" /></label><label>主题<input value={topic} maxLength={200} onChange={event => setTopic(event.target.value)} placeholder="如：函数概念" /></label></div>
      {tab === 'resources' ? <><label>选择已读来源<select aria-label="选择已读来源" value={sourceId} onChange={event => setSourceId(event.target.value)}><option value="">请选择</option>{project.resources.map(resource => <option value={resource.id} key={resource.id}>{resource.title}</option>)}</select></label><button className="um-agent-button" disabled={busy || !sourceId} onClick={() => void act({ kind: 'resource', action: 'save', source_id: sourceId, domain, topic })}>保存到我的资料库</button><p className="um-learning-muted">同一链接不会重复保存。需要更新已有内容时使用“重新核验原文”。</p></> : <><label>选择实际教学记录<select aria-label="选择实际教学记录" value={eventId} onChange={event => setEventId(event.target.value)}><option value="">请选择</option>{events.map(event => <option value={event.id} key={event.id}>{String(event.content.strategy).slice(0, 100)}</option>)}</select></label><button className="um-agent-button" disabled={busy || !eventId} onClick={() => void act({ kind: 'strategy', action: 'save', event_id: Number(eventId), domain, topic })}>保存候选方法</button><p className="um-learning-muted">先保留采用方法与原始表现，等待后续另一轮学习检验。</p></>}
    </details>
    {library.isPending ? <p role="status">正在读取学习积累…</p> : library.isError ? <p role="alert">资料库暂时无法读取。<button onClick={() => void library.refetch()}>重试</button></p> : <>
      {tab === 'resources' ? library.data.resources.map(resource => <ResourceItem key={`${resource.id}:${resource.revision}`} resource={resource} busy={busy} act={act} reread={reread} history={history} />) : library.data.strategies.map(strategy => <article key={strategy.id} className="um-learning-library-item"><h4>{strategy.domain || '候选教学方法'} {strategy.is_retired && <small>已停用</small>}</h4><p>{strategy.method}</p><p className="um-learning-muted">{strategy.topic}</p><p>适用背景：{strategy.context.goal || '历史记录未保留当时目标，试用前需要补充确认。'}{strategy.context.stage && ` · ${strategy.context.stage}`}</p><p className="um-learning-muted">支持观察 {strategy.counts.support} · 相反观察 {strategy.counts.against} · 尚不确定 {strategy.counts.uncertain}。这些记录不证明方法普遍有效。</p>
        <div className="um-learning-controls"><button className="um-agent-button" disabled={!strategy.available} onClick={() => onStudy(`我想在当前项目试用之前的这个方法：“${strategy.method.slice(0, 400)}”。请先查阅我的教学方法记录，核对适用背景和已有相反观察，再登记本次试用，围绕当前目标开始一段学习；等我后续实际表现后再检查结果。`)}>和小宇尝试这个方法</button><button className="um-learning-text-button" disabled={busy} onClick={() => void act({ kind: 'strategy', action: strategy.is_retired ? 'restore' : 'retire', strategy_id: strategy.id, revision: strategy.revision })}>{strategy.is_retired ? '恢复候选' : '暂不采用'}</button></div>
        <details><summary>原始依据与后续观察</summary>{strategy.source.source ? <blockquote>{strategy.source.source}</blockquote> : <p>原始提问已删除，此方法不再推荐。</p>}<p>{strategy.source.observation}</p>{strategy.source.conversation_id && <Link to={learningUrl('/xiaoyu', strategy.source.project_id, strategy.source.conversation_id)}>回看原始对话</Link>}{strategy.reviews.map((review, index) => <div className="um-learning-library-review" key={index}><strong>{judgements[review.judgement]}</strong><p>{review.reason}</p>{review.evidence.source ? <blockquote>{review.evidence.source}</blockquote> : <p>对应原始提问已删除，不计入支持观察。</p>}<p>{review.evidence.observation}</p></div>)}{!strategy.reviews.length && <p>还没有后续检查，不把保存方法或开始试用算作有效。</p>}</details>
      </article>)}
      {!(tab === 'resources' ? library.data.resources.length : library.data.strategies.length) && <p className="um-learning-muted">暂无匹配记录，可以从当前项目的实际资料或教学表现开始积累。</p>}
      <p className="um-learning-muted">最多显示最近 20 条，更多记录可通过关键词查找。归档资料和停用方法保留历史，不再用于新推荐。</p>
    </>}
  </section>;
}
