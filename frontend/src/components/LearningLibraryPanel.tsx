import { getLocale, t, useLocale } from '@/i18n';
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
  useLocale();
  const [snapshot, setSnapshot] = useState<Resource | null>(null);
  const [version, setVersion] = useState('');
  const [tags, setTags] = useState({ domain: resource.domain, topic: resource.topic, level: resource.level, edition: resource.edition });
  return <article className="um-learning-library-item"><h4>{resource.title} {resource.is_archived && <small>{t('已归档')}</small>}</h4>
    <p className="um-learning-muted">{[resource.domain, resource.topic, resource.level, resource.edition].filter(Boolean).join(' · ') || t('尚未归类')} · {resource.source_kind === 'unimind_original' ? t('原创快照创建于 ') : t('原文读取于 ')}{new Date(resource.read_at).toLocaleString(getLocale())}</p>
    <div className="um-learning-controls"><button className="um-agent-button" disabled={busy || resource.is_archived} onClick={() => void act({ kind: 'resource', action: 'attach', resource_id: resource.id })}>{t('接入当前项目')}</button>{resource.source_kind !== 'unimind_original' && <><a href={resource.url} target="_blank" rel="noreferrer">{t('原文')}</a><button className="um-learning-text-button" disabled={busy} onClick={() => void reread(resource)}>{t('重新核验原文')}</button></>}<button className="um-learning-text-button" disabled={busy} onClick={() => void act({ kind: 'resource', action: resource.is_archived ? 'restore' : 'archive', resource_id: resource.id, revision: resource.revision })}>{resource.is_archived ? t('恢复使用') : t('归档')}</button></div>
    <details><summary>{t('片段与适用范围')}</summary><p className="um-learning-library-excerpt">{resource.excerpt}</p><form onSubmit={event => { event.preventDefault(); void act({ kind: 'resource', action: 'update', resource_id: resource.id, revision: resource.revision, ...tags }); }}><div className="um-learning-library-fields">{(['domain', 'topic', 'level', 'edition'] as const).map((key, index) => <label key={key}>{[t('领域'), t('主题'), t('适用基础'), t('年份或版本')][index]}<input maxLength={key === 'topic' ? 200 : key === 'domain' ? 100 : 80} value={tags[key]} onChange={event => setTags(previous => ({ ...previous, [key]: event.target.value }))} /></label>)}</div><button className="um-agent-button" disabled={busy}>{t('保存适用标签')}</button></form></details>
    <details><summary>{t('回看历史版本')}</summary><label>{t('历史版本')}<select aria-label={t('资料历史版本')} value={version} disabled={busy} onChange={event => { const selected = event.target.value; setVersion(selected); if (!selected) setSnapshot(null); else void history(resource, Number(selected)).then(setSnapshot); }}><option value="">{t('请选择版本')}</option>{resource.versions?.map(item => <option key={item.revision} value={item.revision}>{t('版本')} {item.revision} · {new Date(item.created_at).toLocaleString(getLocale())}</option>)}</select></label>{snapshot && <div><h4>{snapshot.title}</h4><p className="um-learning-muted">{[snapshot.domain, snapshot.topic, snapshot.level, snapshot.edition].filter(Boolean).join(' · ')} · {snapshot.source_kind === 'unimind_original' ? t('原创快照创建于 ') : t('原文读取于 ')}{new Date(snapshot.read_at).toLocaleString(getLocale())}</p><p className="um-learning-library-excerpt">{snapshot.excerpt}</p></div>}</details>
  </article>;
}

export function LearningLibraryPanel({ project, onStudy }: { project: ProjectLearning; onStudy: (text: string) => void }) {
  useLocale();
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
      toast.success(response.data.notice || (response.data.created === false && data.action === 'save' ? t('已在资料库中，保留原记录。') : t('已保存。')));
    } catch { toast.error(t('操作未完成，请重新读取最新记录后重试。')); void library.refetch(); }
    finally { setBusy(false); }
  };
  const reread = async (resource: Resource) => {
    if (busy) return;
    setBusy(true);
    try {
      const { data } = await api.post(`/ai/projects/${project.project_id}/learning/`, { url: resource.url });
      await api.post(url, { kind: 'resource', action: 'save', source_id: data.resource.id, revision: resource.revision });
      await refresh(); toast.success(t('已重新读取并更新我的资料库。其他项目仍保留原引用快照。'));
    } catch { toast.error(t('原文未完成核验，已保留原资料。')); }
    finally { setBusy(false); }
  };
  const history = async (resource: Resource, revision: number) => {
    if (busy) return null;
    setBusy(true);
    try { return (await api.get<{ resource: Resource }>(url, { params: { resource_id: resource.id, revision } })).data.resource; }
    catch { toast.error(t('这个历史版本暂时无法读取。')); return null; }
    finally { setBusy(false); }
  };
  const events = project.events.filter(event => event.kind === 'progress' && event.source && event.content.strategy);
  return <section className="um-learning-library"><h3>{t('跨项目积累与复用')}</h3>
    <div className="um-learning-controls" role="group" aria-label={t('查看学习积累')}><button className="um-agent-button" aria-pressed={tab === 'resources'} onClick={() => setTab('resources')}>{t('我的资料库')}</button><button className="um-agent-button" aria-pressed={tab === 'strategies'} onClick={() => setTab('strategies')}>{t('教学方法与后续观察')}</button></div>
    <form className="um-learning-search" onSubmit={event => { event.preventDefault(); setQuery(search.trim()); }}><label htmlFor="learning-library-query">{t('按标题、领域或主题查找')}</label><div><input id="learning-library-query" maxLength={200} value={search} onChange={event => setSearch(event.target.value)} /><button className="um-agent-button">{t('查找积累')}</button></div></form>
    <details className="um-learning-library-save"><summary>{tab === 'resources' ? t('把本项目已读资料留下') : t('留下本项目使用过的方法')}</summary><div className="um-learning-library-fields"><label>{t('领域')}<input value={domain} maxLength={100} onChange={event => setDomain(event.target.value)} placeholder={t('如：高中数学')} /></label><label>{t('主题')}<input value={topic} maxLength={200} onChange={event => setTopic(event.target.value)} placeholder={t('如：函数概念')} /></label></div>
      {tab === 'resources' ? <><label>{t('选择已读来源')}<select aria-label={t('选择已读来源')} value={sourceId} onChange={event => setSourceId(event.target.value)}><option value="">{t('请选择')}</option>{project.resources.map(resource => <option value={resource.id} key={resource.id}>{resource.title}</option>)}</select></label><button className="um-agent-button" disabled={busy || !sourceId} onClick={() => void act({ kind: 'resource', action: 'save', source_id: sourceId, domain, topic })}>{t('保存到我的资料库')}</button></> : <><label>{t('选择实际教学记录')}<select aria-label={t('选择实际教学记录')} value={eventId} onChange={event => setEventId(event.target.value)}><option value="">{t('请选择')}</option>{events.map(event => <option value={event.id} key={event.id}>{String(event.content.strategy).slice(0, 100)}</option>)}</select></label><button className="um-agent-button" disabled={busy || !eventId} onClick={() => void act({ kind: 'strategy', action: 'save', event_id: Number(eventId), domain, topic })}>{t('保存候选方法')}</button></>}
    </details>
    {library.isPending ? <p role="status">{t('正在读取学习积累…')}</p> : library.isError ? <p role="alert">{t('资料库暂时无法读取。')}<button onClick={() => void library.refetch()}>{t('重试')}</button></p> : <>
      {tab === 'resources' ? library.data.resources.map(resource => <ResourceItem key={`${resource.id}:${resource.revision}`} resource={resource} busy={busy} act={act} reread={reread} history={history} />) : library.data.strategies.map(strategy => <article key={strategy.id} className="um-learning-library-item"><h4>{strategy.domain || t('候选教学方法')} {strategy.is_retired && <small>{t('已停用')}</small>}</h4><p>{strategy.method}</p><p className="um-learning-muted">{strategy.topic}</p><p>{t('适用背景：')}{strategy.context.goal || t('未记录目标')}{strategy.context.stage && ` · ${strategy.context.stage}`}</p><p className="um-learning-muted">{t('支持观察')} {strategy.counts.support} {t('· 相反观察')} {strategy.counts.against} {t('· 尚不确定')} {strategy.counts.uncertain}</p>
        <div className="um-learning-controls"><button className="um-agent-button" disabled={!strategy.available} onClick={() => onStudy(t('我想试试之前用的这个方法：{0}', { 0: strategy.method.slice(0, 400) }))}>{t('和小宇尝试这个方法')}</button><button className="um-learning-text-button" disabled={busy} onClick={() => void act({ kind: 'strategy', action: strategy.is_retired ? 'restore' : 'retire', strategy_id: strategy.id, revision: strategy.revision })}>{strategy.is_retired ? t('恢复候选') : t('暂不采用')}</button></div>
        <details><summary>{t('原始依据与后续观察')}</summary>{strategy.source.source ? <blockquote>{strategy.source.source}</blockquote> : <p>{t('原始提问已删除，此方法不再推荐。')}</p>}<p>{strategy.source.observation}</p>{strategy.source.conversation_id && <Link to={learningUrl('/xiaoyu', strategy.source.project_id, strategy.source.conversation_id)}>{t('回看原始对话')}</Link>}{strategy.reviews.map((review, index) => <div className="um-learning-library-review" key={index}><strong>{t(judgements[review.judgement])}</strong><p>{review.reason}</p>{review.evidence.source ? <blockquote>{review.evidence.source}</blockquote> : <p>{t('对应原始提问已删除，不计入支持观察。')}</p>}<p>{review.evidence.observation}</p></div>)}{!strategy.reviews.length && <p>{t('暂无后续观察')}</p>}</details>
      </article>)}
      {!(tab === 'resources' ? library.data.resources.length : library.data.strategies.length) && <p className="um-learning-muted">{t('暂无匹配记录')}</p>}
    </>}
  </section>;
}
