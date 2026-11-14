import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight } from '@phosphor-icons/react';
import api from '@/lib/api';
import type { ProjectLearning } from '@/lib/projectLearning';
import type { LearningKnowledge } from './LearningKnowledgePanel';
import { MarkdownContent } from './MarkdownContent';
import { useAuthStore } from '@/store/useAuthStore';

type Node = LearningKnowledge['nodes'][number];
interface MapVersion { version_id: number; revision: number; title: string; nodes: Node[] }

export function LearningKnowledgeView({ project, selected, onSelect, onStudy, onTask }: {
  project: ProjectLearning; selected: string; onSelect: (id: string) => void;
  onStudy: (text: string, activity?: Record<string, unknown>) => void; onTask: (id: string) => void;
}) {
  const userId = useAuthStore(state => state.user?.id);
  const knowledge = project.knowledge;
  const [allNodes, setAllNodes] = useState(false);
  const [choosing, setChoosing] = useState(!knowledge?.path);
  const [versionId, setVersionId] = useState('');
  const [targets, setTargets] = useState<string[]>([]);
  const [depth, setDepth] = useState('apply');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [evidenceId, setEvidenceId] = useState<number | null>(null);
  const url = `/ai/projects/${project.project_id}/learning/knowledge/`;
  const maps = useQuery({ queryKey: ['learning-knowledge-maps', userId, project.project_id],
    queryFn: ({ signal }) => api.get<{ maps: { id: number; title: string; versions: { id: number; revision: number }[] }[] }>(url, { signal }).then(r => r.data) });
  const version = useQuery({ queryKey: ['learning-knowledge-version', userId, project.project_id, versionId], enabled: !!versionId,
    queryFn: ({ signal }) => api.get<MapVersion>(url, { params: { version_id: versionId }, signal }).then(r => r.data) });
  const nodes = knowledge?.nodes || [];
  const stage = project.plan.stages?.find(item => item.id === project.current_stage);
  const node = nodes.find(item => item.id === selected) || nodes.find(item => stage?.knowledge_nodes?.includes(item.id)) || nodes[0];
  const parents = nodes.filter(item => node?.prerequisites.includes(item.id));
  const children = nodes.filter(item => item.prerequisites.includes(node?.id || ''));
  const evidence = knowledge?.evidence?.filter(item => item.node_id === node?.id) || [];
  const observation = evidence.find(item => item.event_id === evidenceId) || evidence.at(-1);
  const activity = node ? { node_id: node.id, version_id: knowledge?.version_id } : undefined;
  const prepare = async () => {
    if (!targets.length || !version.data || busy) return;
    setBusy(true); setError('');
    try {
      await api.post(url, { action: 'prepare', version_id: version.data.version_id, targets, depth });
      onStudy(`请采用我选择的知识地图“${version.data.title}”版本${version.data.revision}，目标为${version.data.nodes.filter(item => targets.includes(item.id)).map(item => item.title).join('、')}，深度为${depth === 'apply' ? '理解与应用' : '迁移应用'}。请读取该版本并 prepare 所选目标，覆盖全部前置节点和来源，形成阶段安排；已有范围改变时先给我待确认方案。`, { version_id: version.data.version_id, targets, depth });
      setChoosing(false);
    } catch { setError('资料来源暂时无法接入，请核对来源是否已归档后重试。'); }
    finally { setBusy(false); }
  };
  const closure = new Set<string>();
  const visit = (id: string) => { if (closure.has(id)) return; closure.add(id); version.data?.nodes.find(item => item.id === id)?.prerequisites.forEach(visit); };
  targets.forEach(visit);
  return <section className="um-work-knowledge">
    <div className="um-work-section-heading"><div><h2>知识关系</h2><p>{knowledge?.title || '围绕当前学习内容，了解前置与依据'}{knowledge?.revision && ` · 版本 ${knowledge.revision}`}</p></div><button className="um-agent-button" onClick={() => setChoosing(value => !value)}>选择学习范围</button></div>
    {choosing ? <div className="um-work-map-picker">
      <p>地图与来源可以复用，当前表现按项目分别记录。采用新版本时，已有作答保留在原版本。</p>
      {maps.isPending && <p role="status">正在读取知识地图…</p>}
      {maps.isError && <button className="um-agent-button" onClick={() => void maps.refetch()}>重新读取地图</button>}
      {maps.data && !maps.data.maps.length && <p>还没有地图，可以先让小宇从本人资料与实际引用整理。</p>}
      <label>知识地图版本<select aria-label="知识地图版本" value={versionId} onChange={event => { setVersionId(event.target.value); setTargets([]); }}><option value="">请选择</option>{maps.data?.maps.flatMap(map => map.versions.map(v => <option key={v.id} value={v.id}>{map.title} · 版本 {v.revision}</option>))}</select></label>
      {version.isFetching && !!versionId && <p role="status">正在读取版本…</p>}
      {version.isError && <p role="alert">地图版本无法读取，请重新选择。</p>}
      {version.data && <><fieldset><legend>目标知识</legend>{version.data.nodes.map(item => <label key={item.id}><input type="checkbox" checked={targets.includes(item.id)} onChange={event => setTargets(previous => event.target.checked ? [...previous, item.id] : previous.filter(id => id !== item.id))} />{item.title}</label>)}</fieldset>
        <label>学习深度<select aria-label="学习深度" value={depth} onChange={event => setDepth(event.target.value)}><option value="apply">理解与应用</option><option value="transfer">迁移应用</option></select></label>
        {!!targets.length && <p>本次纳入：{version.data.nodes.filter(item => closure.has(item.id)).map(item => item.title).join('、')}。包含所选目标需要的前置知识。</p>}
        <button className="um-agent-button um-agent-button-primary" disabled={!targets.length || busy || version.isFetching || !project.planning_enabled} onClick={() => void prepare()}>{busy ? '正在准备来源…' : '请小宇形成调整方案'}</button></>}
      {project.planning_enabled && <button className="um-agent-button" onClick={() => onStudy('请结合当前项目的目标，从本人资料库实际版本与原文引用整理知识地图，并与我确定学习范围。')}>和小宇构建地图</button>}
      {!project.planning_enabled && <p>当前是自由对话项目。采用学习范围需要新建规划项目。</p>}
      {error && <p role="alert">{error}</p>}
    </div> : node ? <>
      <div className="um-work-section-heading"><p>关系为教学建议，当前学习安排保持不变。</p><button className="um-learning-text-button" onClick={() => setAllNodes(value => !value)}>{allNodes ? '收起全部节点' : `查看全部 ${nodes.length} 个节点`}</button></div>
      {allNodes && <nav className="um-work-node-index" aria-label="全部知识节点">{nodes.map(item => <button className="um-agent-button" aria-pressed={item.id === node.id} key={item.id} onClick={() => onSelect(item.id)}>{item.title}</button>)}</nav>}
      <div className="um-work-relations" aria-label="当前节点的局部知识关系">
        <div><span>前置知识</span>{parents.length ? parents.map(item => <button key={item.id} onClick={() => onSelect(item.id)}>{item.title}<ArrowRight size={14} /></button>) : <p>没有前置节点</p>}</div>
        <div className="um-work-node-current"><span>正在查看</span><h3>{node.title}</h3>{stage?.knowledge_nodes?.includes(node.id) && <small>当前阶段涉及</small>}</div>
        <div><span>后续知识</span>{children.length ? children.map(item => <button key={item.id} onClick={() => onSelect(item.id)}>{item.title}<ArrowRight size={14} /></button>) : <p>没有后续节点</p>}</div>
      </div>
      <p>{node.outcome}</p>
      <div className="um-work-node-evidence"><h3>目前了解的表现</h3><p>{node.beliefs?.apply.effective_count ? `常规应用：${node.beliefs.apply.independent_count} 次独立观察，包含答对与答错。` : '常规应用：尚无可计入的作答观察。'}{node.beliefs?.transfer.effective_count ? `迁移检查：${node.beliefs.transfer.independent_count} 次独立观察。` : '迁移应用仍需实际检查。'}</p>
        <button className="um-agent-button" disabled={!project.planning_enabled} onClick={() => onStudy(`请解释当前查看的“${node.title}”，结合它的前置知识和本项目实际表现，说明它与当前任务的关系。`, activity)}>请小宇解释这个节点</button>
        <details><summary>知识内容的来源</summary><p>{node.citation.title} · 资料版本 {node.citation.revision}</p><blockquote>{node.citation.quote}</blockquote><p>引用支持知识内容，前置关系尚未独立验证。</p></details>
        {node.beliefs && <details><summary>条件估计与计算说明</summary>{(['apply', 'transfer'] as const).map(mode => <p key={mode}>{mode === 'apply' ? '常规应用' : '迁移应用'}：均值 {node.beliefs![mode].mean.toFixed(2)}，80%条件范围 {node.beliefs![mode].interval.map(v => v.toFixed(2)).join(' 至 ')}。有效权重 {node.beliefs![mode].effective_count}。</p>)}<p>固定参数尚未校准，不代表真实掌握概率。提示降低证据权重，引导与帮助未知的记录不更新估计。</p></details>}
      </div>
      <section className="um-work-node-evidence"><h3>这个节点的作答依据</h3>{!evidence.length ? <p>当前项目、当前地图版本尚无作答依据。</p> : <>
        <label>选择一条记录<select value={observation?.event_id || ''} onChange={event => setEvidenceId(Number(event.target.value))}>{[...evidence].reverse().map(item => <option key={item.event_id} value={item.event_id}>{new Date(item.at).toLocaleString('zh-CN')} · {item.outcome === 'success' ? '支持观察' : item.outcome === 'failure' ? '相反观察' : '尚不明确'}</option>)}</select></label>
        {observation && <article><MarkdownContent content={observation.question} /><p>判断标准：{observation.rubric}</p><blockquote>{observation.quote}</blockquote><p>{observation.reason}</p><p>{observation.label_source === 'objective_answer_key' ? '按标准答案比对。' : '模型参考评价，尚未独立复核。'}{observation.assistance === 'unknown' || observation.assistance === 'guided' ? '本次帮助程度未知或逐步引导完成，成绩保留，未计入条件估计。' : observation.assistance === 'hint' ? '本次获得提示，证据按较低权重计入。' : '本次声明独立完成。'}</p>
          {observation.task_id && <button className="um-agent-button" onClick={() => onTask(observation.task_id!)}>查看原作答与评价</button>}
          {!observation.task_id && <button className="um-agent-button" onClick={() => onStudy(`请回看“${node.title}”在${observation.at}的作答依据，对照原任务与标准复盘。`, activity)}>请小宇复盘这条依据</button>}
        </article>}
      </>}</section>
    </> : <p>当前还没有绑定知识地图。可以先通过实际任务了解起点。</p>}
  </section>;
}
