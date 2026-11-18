import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { attachBlockResource, deleteBlockResource, blockAssessment, attachBlockResourceToProject, getBlockResources, resolvePublicAssetLink, updateBlockResource } from '@/lib/knowledgeBuilderApi';
import type { AssetSourceKind, AssetTrack, BlockResourcesResponse, BlockResourceUpdatePayload, BlockQuizMode, BlockResourceItem, BlockResourcePayload, KnowledgeTreeBuildDetail, LearningBlock } from '@/types/knowledgeBuilder';
import { learningKey, type ProjectLearning } from '@/lib/projectLearning';
import { PracticeQuizCard } from '@/pages/xiaoyu/visuals/PracticeQuizCard';
import { Link } from 'react-router-dom';
import { learningUrl } from '@/lib/projectLearning';
import { useAuthStore } from '@/store/useAuthStore';

interface Props {
  tree: KnowledgeTreeBuildDetail; block: LearningBlock; project?: ProjectLearning;
  onClose: () => void; onChanged: () => void;
}
const roleLabels: Record<string, string> = {
  series_episode: '系列主线讲次', concept_intuition: '概念直觉', core_derivation: '核心推导',
  worked_example: '例题实战', wiki_reference: '权威词条定义',
};
const tracks: AssetTrack[] = ['spine', 'spotlight', 'wiki'];
function resourceTrack(resource: BlockResourceItem): AssetTrack {
  return resource.asset_track ?? (resource.source_kind === 'course' ? 'spine' : resource.source_kind === 'wikipedia' ? 'wiki' : 'spotlight');
}
function errorMessage(error: unknown): string {
  const data = (error as { response?: { data?: unknown } })?.response?.data;
  if (typeof data === 'string') return data;
  if (Array.isArray(data)) return data.join('；');
  if (data && typeof data === 'object') return Object.values(data).flat().join('；');
  return error instanceof Error ? error.message : '请求失败，请稍后重试。';
}

export function BlockStudyDialog({ tree, block, project, onClose, onChanged }: Props) {
  const userId = useAuthStore(state => state.user?.id);
  const queryClient = useQueryClient();
  const resourceKey = ['knowledge-block-resources', userId, tree.id, block.id];
  const resourcesQuery = useQuery({ queryKey: resourceKey, queryFn: () => getBlockResources(tree.id, block.id) });
  const [tab, setTab] = useState<'resources' | 'quiz'>('resources');
  const [query, setQuery] = useState(`${tree.subject} ${block.short_title}`);
  const [url, setUrl] = useState('');
  const [atomId, setAtomId] = useState('');
  const [assetTrack, setAssetTrack] = useState<AssetTrack>('spotlight');
  const [locator, setLocator] = useState('');
  const [saveToLibrary, setSaveToLibrary] = useState(false);
  const [searchResults, setSearchResults] = useState<BlockResourcesResponse | null>(null);
  const [searched, setSearched] = useState(false);
  const [mode, setMode] = useState<BlockQuizMode>('objective');
  const [error, setError] = useState('');
  const atoms = tree.atoms.filter(atom => block.steps.some(step => step.step_atoms.some(item => item.atom === atom.id)));
  const onError = (err: unknown) => setError(errorMessage(err));
  const refresh = () => { void queryClient.invalidateQueries({ queryKey: resourceKey }); onChanged(); };
  const attach = useMutation({
    mutationFn: (payload: BlockResourcePayload) => attachBlockResource(tree.id, block.id, payload),
    onSuccess: () => { setUrl(''); refresh(); }, onError,
  });
  const update = useMutation({ mutationFn: (payload: BlockResourceUpdatePayload) => updateBlockResource(tree.id, block.id, payload), onSuccess: refresh, onError });
  const remove = useMutation({ mutationFn: (id: number) => deleteBlockResource(tree.id, block.id, id), onSuccess: refresh, onError });
  const search = useMutation({
    mutationFn: () => getBlockResources(tree.id, block.id, query),
    onSuccess: data => { setSearchResults(data); setSearched(true); }, onError,
  });
  const assessmentKey = ['block-assessment', userId, project?.project_id, tree.id, block.id];
  const canAssess = project?.status === 'active' && project.knowledge?.builder?.build_id === tree.id
    && project.knowledge.nodes.some(node => node.builder_block_ids?.includes(block.id));
  const assessmentQuery = useQuery({ queryKey: assessmentKey, enabled: !!canAssess,
    queryFn: () => blockAssessment(tree.id, block.id, { project_id: project!.project_id, action: 'read' }),
    refetchInterval: query => query.state.data?.preparation?.status === 'pending' || query.state.data?.assessment?.items.some(item => item.task.status === 'processing') ? 2500 : false,
  });
  const assessment = assessmentQuery.data?.assessment;
  const preparing = assessmentQuery.data?.preparation?.status === 'pending';
  const refreshTasks = () => {
    void queryClient.invalidateQueries({ queryKey: assessmentKey });
    void queryClient.invalidateQueries({ queryKey: ['learning-tasks', userId, project?.project_id] });
    void queryClient.invalidateQueries({ queryKey: learningKey(userId, project?.project_id ?? null) });
    onChanged();
  };
  const generate = useMutation({
    mutationFn: () => blockAssessment(tree.id, block.id, { project_id: project!.project_id, action: 'generate', mode, retest: !!assessment }),
    onSuccess: data => { queryClient.setQueryData(assessmentKey, data); refreshTasks(); }, onError,
  });
  const [notice, setNotice] = useState('');
  const useResource = useMutation({
    mutationFn: (id: number) => attachBlockResourceToProject(tree.id, block.id, project!.project_id, id),
    onSuccess: data => { setNotice(data.notice); refreshTasks(); }, onError,
  });
  const busy = attach.isPending || update.isPending || remove.isPending || search.isPending || generate.isPending || useResource.isPending;
  const mountWeb = (link: string) => { setError(''); attach.mutate({ url: link.trim(), asset_track: assetTrack, locator: locator.trim(), save_to_library: saveToLibrary, ...(atomId ? { atom_id: Number(atomId) } : {}) }); };
  const resources = resourcesQuery.data?.resources ?? block.resources ?? [];
  const candidateData = searchResults ?? resourcesQuery.data;
  const isIntl = (candidateData?.region_pref ?? tree.region_pref ?? 'cn') === 'intl';
  const sourceLabels: Record<AssetSourceKind, string> = {
    course: '站内课程', library: '个人资料快照', web: '公开网页', bilibili: 'B站', github: '开源讲义仓库',
    wikipedia: isIntl ? 'Wikipedia' : 'OI-Wiki / 开源学科词条', youtube: isIntl ? 'YouTube / OCW' : '公开视频', marketplace: '共享市场',
  };
  const trackLabels: Record<AssetTrack, string> = { spine: '🎬 主线配套课', spotlight: '🌟 单点神作', wiki: isIntl ? '📖 Wikipedia 词条' : '📖 专业开源 Wiki 词条' };
  const renderResource = (resource: BlockResourceItem, allowEdit = true) => {
    const track = resourceTrack(resource);
    const href = resource.source_kind === 'course' && resource.course_id ? `/course/${resource.course_id}` : resolvePublicAssetLink(resource.url, resource.locator);
    return <article key={resource.id} className={`kb-study-resource kb-study-track-resource is-${track}`}>
      <div className="flex flex-wrap items-center gap-2">
        <a href={href} target="_blank" rel="noopener noreferrer" className="font-semibold underline">{resource.title}</a>
        <span className="kb-badge">{sourceLabels[resource.source_kind]}</span>
        {resource.locator && <span className="kb-badge kb-resource-locator">{resource.locator}</span>}
        {resource.pedagogical_role && <span className="kb-badge">{roleLabels[resource.pedagogical_role] ?? resource.pedagogical_role}</span>}
        {track === 'spine' && <span className="text-sm text-muted-foreground">体系连贯主干</span>}
      </div>
      <p className="text-sm text-muted-foreground">{block.steps.find(step => step.id === resource.step)?.step_title ?? '整个知识块'}{resource.atom ? ` · ${atoms.find(atom => atom.id === resource.atom)?.name ?? ''}` : ''}</p>
      {track === 'wiki' ? <p className="whitespace-pre-wrap text-sm">{resource.excerpt || '暂无词条摘要。'}</p>
        : <details><summary>查看正文摘要</summary><p className="whitespace-pre-wrap text-sm">{resource.excerpt || '暂无正文摘要。'}</p></details>}
      <a href={href} target="_blank" rel="noopener noreferrer" className="kb-resource-direct-link underline">直接打开{resource.locator ? `（${resource.locator}）` : ''}</a>
      {project && <Button size="sm" variant="outline" disabled={busy} onClick={() => { setError(''); useResource.mutate(resource.id); }}>用于当前小宇项目</Button>}
      {allowEdit && <div className="kb-resource-adjustments flex flex-wrap items-center gap-2">
        <label className="text-sm">轨道<select className="kb-study-select" aria-label={`${resource.title}的资源轨道`} value={track} disabled={busy} onChange={event => {
          setError(''); update.mutate({ resource_id: resource.id, asset_track: event.target.value as AssetTrack });
        }}><option value="spine">主线</option><option value="spotlight">神作</option><option value="wiki">{trackLabels.wiki}</option></select></label>
        <label className="text-sm">绑定原子知识点<select className="kb-study-select" aria-label={`${resource.title}绑定的原子知识点`} value={resource.atom ?? ''} disabled={busy} onChange={event => {
          setError(''); update.mutate({ resource_id: resource.id, atom_id: event.target.value ? Number(event.target.value) : null, step_id: null });
        }}><option value="">整个知识块</option>{atoms.map(atom => <option key={atom.id} value={atom.id}>{atom.name}</option>)}</select></label>
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => { setError(''); remove.mutate(resource.id); }}>移除挂载</Button>
      </div>}
    </article>;
  };
  return <Dialog open onOpenChange={open => { if (!open) onClose(); }}>
    <DialogContent className="w-screen max-w-none sm:max-w-none h-dvh max-h-dvh rounded-none border-0 p-6 md:p-10 overflow-y-auto kb-study-dialog kb-study-dialog--fullscreen">
      <DialogHeader><DialogTitle>{block.code} · {block.short_title}</DialogTitle>
        <DialogDescription>第 {block.layer} 层 · 学习资源与项目检测</DialogDescription></DialogHeader>
      <p className="text-sm text-muted-foreground">检测与小宇共用项目任务、原始作答和后续建议。本次通过后仍需换题检验。</p>
      <div className="flex gap-2" role="tablist" aria-label="知识块学习">
        <Button id="kb-study-resources-tab" role="tab" aria-selected={tab === 'resources'} aria-controls="kb-study-resources" variant={tab === 'resources' ? 'default' : 'outline'} onClick={() => setTab('resources')}>学习资源</Button>
        <Button id="kb-study-quiz-tab" role="tab" aria-selected={tab === 'quiz'} aria-controls="kb-study-quiz" variant={tab === 'quiz' ? 'default' : 'outline'} onClick={() => setTab('quiz')}>项目检测</Button>
      </div>
      {notice && <p role="status">{notice}</p>}
      {error && <p role="alert" className="text-red-600">{error}</p>}
      {tab === 'resources' ? <section id="kb-study-resources" role="tabpanel" aria-labelledby="kb-study-resources-tab" className="space-y-4">
        <h3 className="font-semibold">已挂载资源 · {resourcesQuery.data?.resources.length ?? block.resources?.length ?? 0}</h3>
        {resourcesQuery.isLoading && <p>正在读取资源…</p>}
        {resourcesQuery.error && <p role="alert">{errorMessage(resourcesQuery.error)} <Button variant="ghost" onClick={() => void resourcesQuery.refetch()}>重试</Button></p>}
        {tracks.map(track => {
          const trackResources = resources.filter(resource => resourceTrack(resource) === track);
          return <section key={track} className={`kb-study-track is-${track}`} aria-label={trackLabels[track]}>
            <h3 className="font-semibold">{trackLabels[track]} · {trackResources.length}</h3>
            <p className="text-sm text-muted-foreground">{track === 'spine' ? '按讲次连贯学习，直达对应分 P 或章节。' : track === 'spotlight' ? '围绕当前难点，查看概念直觉、核心推导与例题实战。' : '随时查阅概念定义、章节锚点与开源文档。'}</p>
            {trackResources.map(resource => renderResource(resource))}
            {trackResources.length === 0 && <p className="text-sm text-muted-foreground">当前轨道还没有挂载资源。</p>}
          </section>;
        })}
        <section className="space-y-2" aria-label={`${trackLabels.wiki}推荐`}>
          <h3 className="font-semibold">{trackLabels.wiki}推荐</h3>
          {candidateData?.wiki_candidates?.map(candidate => <article key={candidate.url} className="kb-study-resource space-y-2">
            <a href={resolvePublicAssetLink(candidate.url, candidate.locator)} target="_blank" rel="noopener noreferrer" className="font-medium underline">{candidate.title}</a>
            {candidate.locator && <span className="kb-badge">{candidate.locator}</span>}
            <p className="text-sm">{candidate.summary}</p>
            <Button size="sm" variant="outline" disabled={busy} onClick={() => { setError(''); attach.mutate({ url: candidate.url, asset_track: 'wiki', pedagogical_role: candidate.pedagogical_role, locator: candidate.locator, ...(atomId ? { atom_id: Number(atomId) } : {}) }); }}>挂载到本块</Button>
          </article>)}
          {candidateData && !candidateData.wiki_candidates?.length && <p className="text-sm text-muted-foreground">暂无匹配的概念词条。</p>}
        </section>
        <section className="space-y-2" aria-label="精选资产池候选">
          <h3 className="font-semibold">🌟 精选资产池候选</h3>
          {candidateData?.catalog_candidates?.map(candidate => <article key={candidate.id} className="kb-study-resource space-y-2">
            <div className="flex flex-wrap items-center gap-2"><a href={resolvePublicAssetLink(candidate.url)} target="_blank" rel="noopener noreferrer" className="font-medium underline">{candidate.title}</a><span className="kb-badge">{sourceLabels[candidate.source_kind]}</span><span className="kb-badge">{trackLabels[candidate.asset_track]}</span></div>
            <p className="text-sm">{candidate.description}</p>
            <Button size="sm" variant="outline" disabled={busy} onClick={() => { setError(''); attach.mutate({ public_asset_id: candidate.id, asset_track: candidate.asset_track, pedagogical_role: candidate.pedagogical_role, ...(atomId ? { atom_id: Number(atomId) } : {}) }); }}>挂载到本块</Button>
          </article>)}
          {candidateData && !candidateData.catalog_candidates?.length && <p className="text-sm text-muted-foreground">暂无匹配的精选资产。</p>}
        </section>
        <h3 className="font-semibold">匹配的站内课程与个人资料</h3>
        {resourcesQuery.data?.internal_candidates.map((candidate, index) => <article key={index} className="kb-study-resource flex items-center justify-between gap-2">
          <div><a href={resolvePublicAssetLink(candidate.url, candidate.locator)} target="_blank" rel="noopener noreferrer" className="font-semibold underline">{candidate.title}</a><p className="text-sm">{sourceLabels[candidate.source_kind]}</p></div>
          <Button variant="outline" size="sm" disabled={busy} onClick={() => { setError(''); attach.mutate({ ...(candidate.course_id ? { course_id: candidate.course_id } : { library_resource_id: candidate.library_resource_id }), atom_id: candidate.atom_id, step_id: candidate.step_id }); }}>挂载到本块</Button>
        </article>)}
        {resourcesQuery.data?.internal_candidates.length === 0 && <p className="text-sm text-muted-foreground">暂未匹配到站内资源，可搜索或粘贴公开网页。</p>}
        <div className="kb-study-resource space-y-3">
          <h3 className="font-semibold">搜索网上公开资源</h3>
          <form className="flex gap-2" onSubmit={event => { event.preventDefault(); setError(''); search.mutate(); }}>
            <Input aria-label="资源搜索词" value={query} maxLength={300} onChange={event => setQuery(event.target.value)} />
            <Button disabled={busy}>{search.isPending ? '搜索中…' : '联网搜索'}</Button>
          </form>
          <label className="flex gap-2 text-sm"><input type="checkbox" checked={saveToLibrary} onChange={event => setSaveToLibrary(event.target.checked)} />同时存入我的个人资料库</label>
          <label className="block text-sm">关联原子知识点<select className="kb-study-select" value={atomId} onChange={event => setAtomId(event.target.value)}>
            <option value="">自动匹配原子点</option>{atoms.map(atom => <option key={atom.id} value={atom.id}>{atom.name}</option>)}
          </select></label>
          {searched && searchResults?.web_candidates.length === 0 && <p>没有找到公开 HTTPS 候选，请调整搜索词。</p>}
          {searchResults?.web_candidates.map(candidate => <article key={candidate.url} className="kb-study-resource space-y-2">
            <a href={resolvePublicAssetLink(candidate.url)} target="_blank" rel="noopener noreferrer" className="font-medium underline">{candidate.title}</a><p className="text-sm">{candidate.summary}</p>
            <Button size="sm" variant="outline" disabled={busy} onClick={() => mountWeb(candidate.url)}>读取正文并挂载到本块</Button>
          </article>)}
          <h3 className="font-semibold">直接粘贴 HTTPS 链接</h3>
          <div className="flex flex-wrap gap-3">
            <label className="text-sm">挂载轨道<select className="kb-study-select" value={assetTrack} onChange={event => setAssetTrack(event.target.value as AssetTrack)}>
              <option value="spotlight">🌟 单点神作</option><option value="spine">🎬 主线配套</option><option value="wiki">{trackLabels.wiki}</option>
            </select></label>
            <label className="flex-1 text-sm">定位符<Input aria-label="资源定位符" value={locator} maxLength={300} placeholder="P3 · 05:20 或 #资本市场线" onChange={event => setLocator(event.target.value)} /></label>
          </div>
          <form className="flex flex-wrap gap-2" onSubmit={event => { event.preventDefault(); mountWeb(url); }}>
            <Input className="flex-1 min-w-48" aria-label="公开 HTTPS 链接" type="url" required pattern="https://.*" value={url} maxLength={1000} placeholder="https://…" onChange={event => setUrl(event.target.value)} />
            <Button disabled={busy || !url.trim()}>{attach.isPending ? '读取并挂载中…' : '读取正文并挂载'}</Button>
          </form>
        </div>
      </section> : <section id="kb-study-quiz" role="tabpanel" aria-labelledby="kb-study-quiz-tab" className="space-y-4">
        {!canAssess ? <p>请先把这个知识块加入当前项目目标，在小宇确认学习安排后开始检测。</p> : <>
          <label className="block text-sm">题型模式<select className="kb-study-select" value={mode} disabled={busy || !!assessment && !assessment.complete} onChange={event => setMode(event.target.value as BlockQuizMode)}>
            <option value="objective">客观题快测</option><option value="challenge">进阶挑战（加一道开放题）</option>
          </select></label>
          <p className="text-sm text-muted-foreground">逐个覆盖本块核心点，核心题均达到 75%，且平均得分率达到 75%，视为本次检测通过。开放题为模型参考评价。</p>
          {assessmentQuery.isLoading && <p>正在恢复项目任务…</p>}
          {assessmentQuery.error && <p role="alert">{errorMessage(assessmentQuery.error)} <Button variant="ghost" onClick={() => void assessmentQuery.refetch()}>重试</Button></p>}
          {!assessmentQuery.isError && <Button disabled={busy || preparing || assessmentQuery.isLoading || !!assessment && !assessment.complete} onClick={() => { setError(''); generate.mutate(); }}>{generate.isPending || preparing ? '正在准备项目任务…' : assessment ? '换题再检验' : '开始本块检测'}</Button>}
          {assessmentQuery.data?.preparation?.error && <p role="alert">{assessmentQuery.data.preparation.error}</p>}
          {preparing && <p role="status">正在后台逐点准备题目，关闭后可以从本块或小宇恢复。</p>}
          {assessment?.items.map(item => <article key={item.task.id} className="kb-study-resource space-y-2">
            <p>{item.atom_name} · {item.membership_type === 'core' ? '核心点' : '拓展点'}</p>
            {item.task.status === 'unavailable' || item.task.is_current === false && !item.task.exam_id ? <p>当前任务已停止使用，请回小宇确认新的学习安排。</p> : <PracticeQuizCard payload={{ ...item.task.payload, learning_task_id: item.task.id, project_id: project!.project_id, conversation_id: project!.conversation_id || undefined, assistance: item.task.assistance, response_type: item.task.response_type, label_source: item.task.summary?.label_source }} onResult={refreshTasks} />}
          </article>)}
          {assessment?.complete && <p className={`kb-study-status ${assessment.passed ? 'is-complete' : 'is-review'}`} role="status">{assessment.passed ? '本次检测通过' : '本次检测待强化'} · {Math.round((assessment.accuracy ?? 0) * 100)}%。长期状态与下一步建议请在小宇查看。</p>}
        </>}
        <Link className="underline" to={learningUrl('/xiaoyu?learning_view=knowledge', project?.project_id ?? null, project?.conversation_id || undefined)} onClick={onClose}>回小宇查看学习安排与下一步</Link>

      </section>}
    </DialogContent>
  </Dialog>;
}
