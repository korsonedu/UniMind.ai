import { getLocale, t, useLocale } from '@/i18n';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowRight } from '@phosphor-icons/react';
import api from '@/lib/api';
import { learningKey, learningUrl, type ProjectLearning } from '@/lib/projectLearning';
import type { LearningKnowledge } from './LearningKnowledgePanel';
import { queryClient } from '@/lib/queryClient';
import { normalizeApiError } from '@/lib/apiError';
import type { LearningTask } from './LearningTasksPanel';
import { listKnowledgeBuilds } from '@/lib/knowledgeBuilderApi';
import { queryKeys } from '@/lib/queryKeys';
import { MarkdownContent } from './MarkdownContent';
import { useAuthStore } from '@/store/useAuthStore';
import { useXiaoYuChat } from '@/pages/xiaoyu/xiaoYuChatContext';

type Node = LearningKnowledge['nodes'][number];
interface MapVersion { version_id: number; revision: number; title: string; nodes: Node[] }

export function LearningKnowledgeView({ project, selected, tasks, tasksLoading, onSelect, onStudy, onTask }: {
  project: ProjectLearning; selected: string; tasks: LearningTask[]; tasksLoading: boolean; onSelect: (id: string) => void;
  onStudy: (text: string, activity?: Record<string, unknown>) => void; onTask: (id: string) => void;
}) {
  useLocale();
  const userId = useAuthStore(state => state.user?.id);
  const { chat } = useXiaoYuChat();
  const [searchParams] = useSearchParams();
  const conversationId = (chat.projectId === project.project_id && chat.conversationId)
    || searchParams.get('conversation') || project.conversation_id || undefined;
  const knowledge = project.knowledge;
  const [allNodes, setAllNodes] = useState(false);
  const [choosing, setChoosing] = useState(!knowledge?.path);
  const [shownVersion, setShownVersion] = useState(knowledge?.version_id);
  if (shownVersion !== knowledge?.version_id) {
    setShownVersion(knowledge?.version_id);
    setChoosing(!knowledge?.path);
  }
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
  const builds = useQuery({ queryKey: queryKeys.knowledgeBuilder.list(userId),
    queryFn: ({ signal }) => listKnowledgeBuilds(signal) });
  const nodes = knowledge?.nodes || [];
  const stage = project.plan.stages?.find(item => item.id === project.current_stage);
  const node = nodes.find(item => item.id === selected) || nodes.find(item => stage?.knowledge_nodes?.includes(item.id)) || nodes[0];
  const parents = nodes.filter(item => node?.prerequisites.includes(item.id));
  const children = nodes.filter(item => item.prerequisites.includes(node?.id || ''));
  const evidence = knowledge?.evidence?.filter(item => item.node_id === node?.id) || [];
  const observation = evidence.find(item => item.event_id === evidenceId) || evidence[0];
  const activity = node ? { node_id: node.id, version_id: knowledge?.version_id } : undefined;
  const startNode = async (id: string, mode: 'apply' | 'transfer' = 'apply') => {
    const unit = nodes.find(item => item.id === id);
    if (!unit || !knowledge?.version_id) return;
    const pending = tasks.find(task => task.version_id === knowledge.version_id && task.node_id === id && task.is_current !== false
      && ['ready', 'processing', 'partial', 'failed'].includes(task.status));
    if (pending) {
      setBusy(true);
      try {
        await api.patch(`/ai/projects/${project.project_id}/learning/`, { action: 'focus', revision: project.revision, task_id: pending.id });
        await queryClient.invalidateQueries({ queryKey: learningKey(userId, project.project_id) });
        onTask(pending.id);
      } catch (error) { toast.error(normalizeApiError(error, t('学习安排未更新，请重试。')).message); }
      finally { setBusy(false); }
      return;
    }
    const phase = project.plan.stages?.find(item => item.knowledge_nodes?.includes(id));
    onStudy(t('请读取“{0}”的原作答与已有表现，继续这个节点。已有待答任务就复用；否则为知识版本 {1}、节点 {2}、阶段 {3} 创建一个{4}学习任务，给出可作答入口，等我实际完成后再评价。', {
      0: unit.title, 1: knowledge.version_id, 2: id, 3: phase?.id || '', 4: mode === 'transfer' ? t('迁移应用') : t('理解与应用'),
    }), { version_id: knowledge.version_id, node_id: id });
  };
  const prepare = async () => {
    if (!targets.length || !version.data || busy) return;
    setBusy(true); setError('');
    try {
      await api.post(url, { action: 'prepare', version_id: version.data.version_id, targets, depth });
      onStudy(t('请根据我选择的知识地图“{0}”版本{1}，目标为{2}，深度为{3}，覆盖全部前置节点和实际来源，形成阶段安排。已有范围改变时，请先将具体调整保存为待确认方案，让我在确认界面采用或保留原安排。提交方案不代表采用新计划，不要只在回复里列建议，也不要再次询问是否要生成方案。', { 0: version.data.title, 1: version.data.revision, 2: version.data.nodes.filter(item => targets.includes(item.id)).map(item => item.title).join('、'), 3: depth === 'apply' ? t('理解与应用') : t('迁移应用') }), { version_id: version.data.version_id, targets, depth });
      setChoosing(false);
    } catch { setError(t('资料来源暂时无法接入，请核对来源是否已归档后重试。')); }
    finally { setBusy(false); }
  };
  const closure = new Set<string>();
  const visit = (id: string) => { if (closure.has(id)) return; closure.add(id); version.data?.nodes.find(item => item.id === id)?.prerequisites.forEach(visit); };
  targets.forEach(visit);
  return <section className="um-work-knowledge">
    <div className="um-work-section-heading"><div><h2>{t('知识关系')}</h2><p>{knowledge?.title || t('围绕当前学习内容，了解前置与依据')}{knowledge?.revision && t(' · 版本 {0}', { 0: knowledge.revision })}</p></div><button className="um-agent-button" onClick={() => setChoosing(value => !value)}>{t('选择学习范围')}</button></div>
    <div className="um-work-actions">
      <button className="um-agent-button" onClick={() => onStudy(t('我想系统学习当前项目的目标。请结合已有背景，必要时先简短了解用途、范围与基础，再和我确定一段可以开始的学习路径。请查询可用的学科知识结构，有适合的就复用；也可以边学边了解，不必先完成整套问答或快测。'))}>{t('和小宇确定学习路径')}</button>
      <Link className="um-learning-text-button" to={learningUrl(knowledge?.builder ? `/xiaoyu/knowledge-builder/${knowledge.builder.build_id}` : '/xiaoyu/knowledge-builder', project.project_id, conversationId)}>{knowledge?.builder ? t('展开完整图谱') : t('选择知识结构')}</Link>
    </div>
    {!!knowledge?.recommendations.length && <section className="um-work-node-evidence"><h3>{t('建议下一步')}</h3>{knowledge.recommendations.map(item => <div className="um-work-section-heading" key={item.node_id}><div><strong>{item.title}</strong><p>{t(item.reason)}</p></div><button className="um-agent-button" disabled={busy || tasksLoading || !project.planning_enabled || project.status !== 'active'} onClick={() => { onSelect(item.node_id); startNode(item.node_id, item.mode); }}>{t('继续学习')}</button></div>)}</section>}
    {choosing ? <div className="um-work-map-picker">
      <p>{t('地图与来源可以复用，当前表现按项目分别记录。采用新版本时，已有作答保留在原版本。')}</p>
      <Link className="um-agent-button" to={learningUrl('/xiaoyu/knowledge-builder?create=1', project.project_id, conversationId)}>{t('和小宇生成知识结构')}</Link>
      {builds.isError && <button className="um-learning-text-button" onClick={() => void builds.refetch()}>{t('重新读取学科结构')}</button>}
      {!!builds.data?.some(build => build.status === 'COMPLETED') && <details><summary>{t('已有学科知识结构')}</summary>{builds.data.filter(build => build.status === 'COMPLETED').map(build => <p key={build.id}><Link to={learningUrl(`/xiaoyu/knowledge-builder/${build.id}`, project.project_id, conversationId)}>{build.subject}</Link></p>)}</details>}
      {maps.isPending && <p role="status">{t('正在读取知识地图…')}</p>}
      {maps.isError && <button className="um-agent-button" onClick={() => void maps.refetch()}>{t('重新读取地图')}</button>}
      {maps.data && !maps.data.maps.length && <p>{t('还没有地图，可以先让小宇从本人资料与实际引用整理。')}</p>}
      <label>{t('知识地图版本')}<select aria-label={t('知识地图版本')} value={versionId} onChange={event => { setVersionId(event.target.value); setTargets([]); }}><option value="">{t('请选择')}</option>{maps.data?.maps.flatMap(map => map.versions.map(v => <option key={v.id} value={v.id}>{map.title} {t('· 版本')} {v.revision}</option>))}</select></label>
      {version.isFetching && !!versionId && <p role="status">{t('正在读取版本…')}</p>}
      {version.isError && <p role="alert">{t('地图版本无法读取，请重新选择。')}</p>}
      {version.data && <><fieldset><legend>{t('目标知识')}</legend>{version.data.nodes.map(item => <label key={item.id}><input type="checkbox" checked={targets.includes(item.id)} onChange={event => setTargets(previous => event.target.checked ? [...previous, item.id] : previous.filter(id => id !== item.id))} />{item.title}</label>)}</fieldset>
        <label>{t('学习深度')}<select aria-label={t('学习深度')} value={depth} onChange={event => setDepth(event.target.value)}><option value="apply">{t('理解与应用')}</option><option value="transfer">{t('迁移应用')}</option></select></label>
        {!!targets.length && <p>{t('本次纳入：')}{version.data.nodes.filter(item => closure.has(item.id)).map(item => item.title).join('、')}{t('。包含所选目标需要的前置知识。')}</p>}
        {project.planning_enabled ? <button className="um-agent-button um-agent-button-primary" disabled={!targets.length || busy || version.isFetching} onClick={() => void prepare()}>{busy ? t('正在准备来源…') : t('请小宇形成调整方案')}</button> : <button className="um-agent-button" disabled={!targets.length || version.isFetching} onClick={() => onStudy(t('请解释我在知识地图“{0}”中选择的知识，以及它们的前置关系。当前保持自由对话，不建立学习安排。', { 0: version.data.title }), { version_id: version.data.version_id, targets, depth })}>{t('请小宇解释所选知识')}</button>}</>}
      {project.planning_enabled && <button className="um-agent-button" onClick={() => onStudy(t('请结合当前项目的目标，从本人资料库实际版本与原文引用整理知识地图，并与我确定学习范围。'))}>{t('和小宇构建地图')}</button>}
      {!project.planning_enabled && <p>{t('当前是自由对话项目。采用学习范围需要')}<Link to="/xiaoyu?new=project">{t('新建规划项目')}</Link>{t('，创建时选择规划模式。')}</p>}
      {error && <p role="alert">{error}</p>}
    </div> : node ? <>
      <div className="um-work-section-heading"><p>{t('关系为教学建议，当前学习安排保持不变。')}</p><button className="um-learning-text-button" onClick={() => setAllNodes(value => !value)}>{allNodes ? t('收起全部节点') : t('查看全部 {0} 个节点', { 0: nodes.length })}</button></div>
      {allNodes && <nav className="um-work-node-index" aria-label={t('全部知识节点')}>{nodes.map(item => <button className="um-agent-button" aria-pressed={item.id === node.id} key={item.id} onClick={() => onSelect(item.id)}>{item.title}</button>)}</nav>}
      <div className="um-work-relations" aria-label={t('当前节点的局部知识关系')}>
        <div><span>{t('前置知识')}</span>{parents.length ? parents.map(item => <button key={item.id} onClick={() => onSelect(item.id)}>{item.title}<ArrowRight size={14} /></button>) : <p>{t('没有前置节点')}</p>}</div>
        <div className="um-work-node-current"><span>{t('正在查看')}</span><h3>{node.title}</h3>{(node.learning_status || stage?.knowledge_nodes?.includes(node.id)) && <small>{node.learning_status && t({ unassessed: '尚待了解', recheck: '建议再检查', review: '建议回补', supported: '已有独立支持' }[node.learning_status])}{stage?.knowledge_nodes?.includes(node.id) && `${node.learning_status ? ' · ' : ''}${t('当前阶段涉及')}`}</small>}</div>
        <div><span>{t('后续知识')}</span>{children.length ? children.map(item => <button key={item.id} onClick={() => onSelect(item.id)}>{item.title}<ArrowRight size={14} /></button>) : <p>{t('没有后续节点')}</p>}</div>
      </div>
      <p>{node.outcome}</p>
      {project.planning_enabled && <button className="um-agent-button um-agent-button-primary" disabled={busy || tasksLoading || project.status !== 'active'} onClick={() => startNode(node.id)}>{t('开始这个节点')}</button>}
      {!!tasks.filter(task => task.version_id === knowledge?.version_id && task.node_id === node.id).length && <section className="um-work-node-evidence"><h3>{t('节点任务')}</h3>{tasks.filter(task => task.version_id === knowledge?.version_id && task.node_id === node.id).map(task => <p key={task.id}><button className="um-learning-text-button" onClick={() => onTask(task.id)}>{task.title} · {task.status === 'completed' ? t('查看作答与评价') : t('继续任务')}</button></p>)}</section>}
      <div className="um-work-node-evidence"><h3>{t('目前了解的表现')}</h3><p>{node.beliefs?.apply.effective_count ? t('常规应用：{0} 次独立观察，包含答对与答错。', { 0: node.beliefs.apply.independent_count }) : t('常规应用：尚无可计入的作答观察。')}{node.beliefs?.transfer.effective_count ? t('迁移检查：{0} 次独立观察。', { 0: node.beliefs.transfer.independent_count }) : t('迁移应用仍需实际检查。')}</p>
        <button className="um-agent-button" onClick={() => onStudy(t('请解释当前查看的“{0}”，结合它的前置知识和本项目实际表现，说明它与当前任务的关系。', { 0: node.title }), activity)}>{t('请小宇解释这个节点')}</button>
        <details><summary>{t('知识内容的来源')}</summary><p>{node.citation.title} {t('· 资料版本')} {node.citation.revision}</p><blockquote>{node.citation.quote}</blockquote><p>{node.citation.source_kind === 'generated_graph' ? t('AI 生成的知识结构快照，尚未逐项核验教材依据；前置关系为教学建议。') : t('引用支持知识内容，前置关系尚未独立验证。')}</p></details>
        {node.beliefs && <details><summary>{t('条件估计与计算说明')}</summary>{(['apply', 'transfer'] as const).map(mode => <p key={mode}>{mode === 'apply' ? t('常规应用') : t('迁移应用')}{t('：均值')} {node.beliefs![mode].mean.toFixed(2)}{t('，80%条件范围')} {node.beliefs![mode].interval.map(v => v.toFixed(2)).join(t(' 至 '))}{t('。有效权重')} {node.beliefs![mode].effective_count}。</p>)}<p>{t('固定参数尚未校准，不代表真实掌握概率。提示降低证据权重，引导与帮助未知的记录不更新估计。')}</p></details>}
      </div>
      <section className="um-work-node-evidence"><h3>{t('这个节点的作答依据')}</h3>{!evidence.length ? <p>{t('当前项目、当前地图版本尚无作答依据。')}</p> : <>
        <label>{t('选择一条记录')}<select value={observation?.event_id || ''} onChange={event => setEvidenceId(Number(event.target.value))}>{[...evidence].reverse().map(item => <option key={item.event_id} value={item.event_id}>{new Date(item.at).toLocaleString(getLocale())} · {item.outcome === 'success' ? t('支持观察') : item.outcome === 'failure' ? t('相反观察') : t('尚不明确')}</option>)}</select></label>
        {observation && <article><MarkdownContent content={observation.question} /><p>{t('判断标准：')}{observation.rubric}</p><blockquote>{observation.quote}</blockquote><p>{observation.reason}</p><p>{observation.label_source === 'objective_answer_key' ? t('按标准答案比对。') : t('模型参考评价，尚未独立复核。')}{observation.assistance === 'unknown' || observation.assistance === 'guided' ? t('本次帮助程度未知或逐步引导完成，成绩保留，未计入条件估计。') : observation.assistance === 'hint' ? t('本次获得提示，证据按较低权重计入。') : t('本次声明独立完成。')}</p>
          {observation.task_id && <button className="um-agent-button" onClick={() => onTask(observation.task_id!)}>{t('查看原作答与评价')}</button>}
          {!observation.task_id && <button className="um-agent-button" onClick={() => onStudy(t('请回看“{0}”在{1}的作答依据，对照原任务与标准复盘。', { 0: node.title, 1: observation.at }), activity)}>{t('请小宇复盘这条依据')}</button>}
        </article>}
      </>}</section>
    </> : <p>{t('当前还没有绑定知识地图。可以先通过实际任务了解起点。')}</p>}
  </section>;
}
