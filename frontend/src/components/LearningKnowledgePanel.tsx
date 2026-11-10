import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Link } from 'react-router-dom';
import api from '@/lib/api';
import { useAuthStore } from '@/store/useAuthStore';
import { learningUrl, type ProjectLearning } from '@/lib/projectLearning';

interface Belief { mean: number; interval: [number, number]; effective_count: number; independent_count: number; stale_days: number | null; }
interface KnowledgeNode {
  id: string; title: string; outcome: string; prerequisites: string[];
  citation: { resource_id: number; revision: number; quote: string; url: string; title: string; read_at: string };
  beliefs?: Record<'apply' | 'transfer', Belief>;
}
interface KnowledgeVersion { version_id: number; revision: number; title: string; nodes: KnowledgeNode[]; }
export interface LearningKnowledge {
  algorithm: string; version_id?: number; revision?: number; title?: string;
  path: { version_id: number; targets: string[]; depth: 'apply' | 'transfer' } | null;
  nodes: KnowledgeNode[];
  excluded_evidence_count?: number;
  recommendations: { node_id: string; title: string; mode: 'apply' | 'transfer'; reason: string; information_gain: number; target_coverage: number; gap: number; score: number }[];
  evidence?: { event_id: number; conversation_id: string; source: string; question: string; rubric: string; quote: string; reason: string; outcome: 'success' | 'failure' | 'unclear'; assistance: string; node_id: string; mode: 'apply' | 'transfer'; at: string }[];
}
const modes = { apply: '理解与应用', transfer: '迁移应用' };
const outcomes = { success: '支持观察', failure: '相反观察', unclear: '尚不明确' };
const assistance: Record<string, string> = { independent: '独立完成', hint: '获得提示', guided: '逐步引导', unknown: '帮助程度未知' };

function Estimate({ title, estimate }: { title: string; estimate: Belief }) {
  return <div className="um-knowledge-estimate"><strong>{title}</strong><p>{estimate.effective_count ? `已有 ${estimate.independent_count} 次独立观察 · 有效证据权重 ${estimate.effective_count}` : '尚需实际任务了解'}{estimate.stale_days !== null && estimate.stale_days > 30 && ' · 证据较早'}</p>
    <details><summary>条件估计与范围</summary><p>均值 {estimate.mean.toFixed(2)}，80% 条件范围 {estimate.interval.map(value => value.toFixed(2)).join(' 至 ')}。固定原型参数下的计算，尚未校准，不代表真实掌握概率。</p></details></div>;
}

export function LearningKnowledgePanel({ project, onStudy }: { project: ProjectLearning; onStudy: (text: string) => void }) {
  const userId = useAuthStore(state => state.user?.id);
  const [versionId, setVersionId] = useState('');
  const [targets, setTargets] = useState<string[]>([]);
  const [depth, setDepth] = useState<'apply' | 'transfer'>('apply');
  const [busy, setBusy] = useState(false);
  const active = useRef(true);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  const url = `/ai/projects/${project.project_id}/learning/knowledge/`;
  const maps = useQuery({ queryKey: ['learning-knowledge-maps', userId, project.project_id],
    queryFn: ({ signal }) => api.get<{ maps: { id: number; title: string; versions: { id: number; revision: number }[] }[] }>(url, { signal }).then(result => result.data) });
  const version = useQuery({ queryKey: ['learning-knowledge-version', userId, project.project_id, versionId], enabled: !!versionId,
    queryFn: ({ signal }) => api.get<KnowledgeVersion>(url, { params: { version_id: versionId }, signal }).then(result => result.data) });
  const knowledge = project.knowledge;
  const prepare = async () => {
    if (!targets.length || !version.data || busy) return;
    setBusy(true);
    try {
      const { data } = await api.post(url, { action: 'prepare', version_id: version.data.version_id, targets, depth });
      if (!active.current) return;
      onStudy(`我想在本项目采用知识地图“${version.data.title}”版本 ${version.data.revision}，学习深度为${modes[depth]}。请读取该版本，用以下 prepare 结果形成阶段安排，并覆盖全部前置节点。已有范围或深度改变时先给我待确认方案：${JSON.stringify({ knowledge_path: data.knowledge_path, sources: data.sources, nodes: data.nodes.map((node: KnowledgeNode) => node.id) })}`);
    } catch { toast.error('来源未接入，请检查资料是否已归档，或重新读取知识版本。'); }
    finally { setBusy(false); }
  };
  return <section className="um-learning-knowledge"><h3>知识地图与证据路径</h3><p className="um-learning-muted">按目标选择范围与深度，小宇会补上前置知识，再用实际任务逐步了解你的表现。</p>
    <button className="um-agent-button" onClick={() => onStudy('请结合本项目目标，先从本人资料库的实际版本和原文引用构建知识地图，给出知识单元及前置教学建议，再与我确定学习范围和深度。')}>和小宇构建知识地图</button>
    <details className="um-knowledge-picker"><summary>选择已有地图与学习范围</summary>
      {maps.isPending && <p role="status">正在读取知识地图…</p>}{maps.isError && <p role="alert">地图暂时无法读取。<button className="um-learning-text-button" onClick={() => void maps.refetch()}>重试</button></p>}
      {maps.data && !maps.data.maps.length && <p>还没有知识地图，可以先和小宇从已读资料整理第一张。</p>}
      {!!maps.data?.maps.length && <label>知识地图版本<select aria-label="知识地图版本" value={versionId} onChange={event => { setVersionId(event.target.value); setTargets([]); }}><option value="">请选择</option>{maps.data.maps.flatMap(map => map.versions.map(item => <option key={item.id} value={item.id}>{map.title} · 版本 {item.revision}</option>))}</select></label>}
      {version.isFetching && !!versionId && <p role="status">正在读取版本…</p>}{version.isError && <p role="alert">这个版本暂时无法读取，请重新选择。</p>}
      {version.data && <><fieldset><legend>想学到哪里</legend>{version.data.nodes.map(node => <label className="um-knowledge-target" key={node.id}><input type="checkbox" checked={targets.includes(node.id)} onChange={event => setTargets(previous => event.target.checked ? [...previous, node.id] : previous.filter(id => id !== node.id))} />{node.title}</label>)}</fieldset><label>学习深度<select aria-label="学习深度" value={depth} onChange={event => setDepth(event.target.value as 'apply' | 'transfer')}><option value="apply">理解与应用</option><option value="transfer">迁移应用</option></select></label><p className="um-learning-muted">自动纳入前置节点。下一步将范围带回对话形成计划，重要调整仍需确认。</p><button className="um-agent-button" disabled={busy || version.isFetching || !targets.length} onClick={() => void prepare()}>带回对话形成计划</button></>}
    </details>
    {knowledge?.path && <><h4>{knowledge.title} · 版本 {knowledge.revision}</h4><p>目标：{knowledge.path.targets.map(id => knowledge.nodes.find(node => node.id === id)?.title || id).join('、')} · {modes[knowledge.path.depth]}</p>
      <ol className="um-knowledge-nodes">{knowledge.nodes.map(node => <li key={node.id}><h4>{node.title}</h4><p>{node.outcome}</p><p className="um-learning-muted">前置：{node.prerequisites.map(id => knowledge.nodes.find(item => item.id === id)?.title || id).join('、') || '无'}（教学建议）</p>
        {node.beliefs && <div className="um-knowledge-estimates"><Estimate title="常规任务" estimate={node.beliefs.apply} /><Estimate title="候选迁移任务" estimate={node.beliefs.transfer} /></div>}
        <details><summary>知识依据与资料版本</summary><a href={node.citation.url} target="_blank" rel="noreferrer">{node.citation.title}</a><p className="um-learning-muted">资料版本 {node.citation.revision} · 读取于 {new Date(node.citation.read_at).toLocaleString('zh-CN')}</p><blockquote>{node.citation.quote}</blockquote><p className="um-learning-muted">引用支持知识内容，前置关系尚未独立验证。</p></details>
      </li>)}</ol>
      <h4>建议下一次检查</h4>{knowledge.recommendations.map(item => <article className="um-knowledge-recommendation" key={item.node_id}><p>{item.title} · {modes[item.mode]}</p><p className="um-learning-muted">{item.reason}</p><button className="um-learning-text-button" onClick={() => onStudy(`请围绕当前知识地图节点 ${item.node_id}“${item.title}”安排一次${modes[item.mode]}检查。先登记具体任务和判断标准，呈现任务后等我作答。`)}>让小宇准备任务</button><details><summary>为什么建议这一项</summary><p>预期信息增益 {item.information_gain.toFixed(3)}，目标覆盖 {item.target_coverage.toFixed(2)}，估计缺口 {item.gap.toFixed(2)}，排序值 {item.score.toFixed(3)}。先检查前置节点，再结合这些分项排序；排序值表示原型策略的相对优先级。</p></details></article>)}
      <details className="um-learning-evidence"><summary>查看实际检查依据</summary>{!knowledge.evidence?.length && <p>尚无后续作答证据。</p>}{knowledge.evidence?.map(item => <article key={item.event_id}><time>{new Date(item.at).toLocaleString('zh-CN')}</time><h4>{knowledge.nodes.find(node => node.id === item.node_id)?.title} · {modes[item.mode]} · {outcomes[item.outcome]}</h4><p>任务：{item.question}</p><p>标准：{item.rubric}</p><blockquote>{item.quote}</blockquote><p>{item.reason}</p><p className="um-learning-muted">{assistance[item.assistance]} · 判断由小宇依据任务标准提出，尚未独立复核。</p><Link to={learningUrl('/xiaoyu', project.project_id, item.conversation_id)}>回到原对话</Link></article>)}</details>
      {!!knowledge.excluded_evidence_count && <p className="um-learning-muted">有 {knowledge.excluded_evidence_count} 条历史观察的原始依据已不可核验，已停止计入当前估计。</p>}
      <details><summary>关于贝叶斯证据路径引擎</summary><p>{knowledge.algorithm} 根据可回放的实际任务观测计算常规与迁移两组条件分布。提示降低证据权重，引导与未知帮助不更新；证据过时后逐步回到未知。参数和任务差异尚未用真实学习数据校准，范围只表达固定假设下的不确定性。</p></details>
    </>}
  </section>;
}
