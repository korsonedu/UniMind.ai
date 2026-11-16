import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { MarkdownContent } from '@/components/MarkdownContent';
import { attachBlockResource, deleteBlockResource, generateBlockQuiz, getBlockResources, resolvePublicAssetLink, submitBlockQuiz, updateBlockResource } from '@/lib/knowledgeBuilderApi';
import type { AssetSourceKind, AssetTrack, BlockResourcesResponse, BlockResourceUpdatePayload, BlockQuizMode, BlockQuizQuestion, BlockQuizSubmitResult, BlockResourceItem, BlockResourcePayload, KnowledgeTreeBuildDetail, LearningBlock, UserBlockProgressItem } from '@/types/knowledgeBuilder';
import { useAuthStore } from '@/store/useAuthStore';

interface Props {
  tree: KnowledgeTreeBuildDetail; block: LearningBlock; progress?: UserBlockProgressItem;
  onClose: () => void; onChanged: () => void;
}
const sourceLabels: Record<AssetSourceKind, string> = {
  course: '站内课程', library: '个人资料快照', web: '公开网页', bilibili: 'B站', github: 'GitHub 开源',
  wikipedia: '维基百科', youtube: 'YouTube / OCW', marketplace: '共享市场',
};
const trackLabels: Record<AssetTrack, string> = { spine: '🎬 主线配套课', spotlight: '🌟 单点神作', wiki: '📖 权威百科与开源文档' };
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

export function BlockStudyDialog({ tree, block, progress, onClose, onChanged }: Props) {
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
  const [questions, setQuestions] = useState<BlockQuizQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [result, setResult] = useState<BlockQuizSubmitResult | null>(progress?.last_quiz_result && 'block_id' in progress.last_quiz_result ? progress.last_quiz_result as BlockQuizSubmitResult : null);
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
  const generate = useMutation({
    mutationFn: (retest: boolean) => generateBlockQuiz(tree.id, block.id, { mode, retest }),
    onSuccess: data => { setQuestions(data.questions); setAnswers({}); setResult(null); onChanged(); }, onError,
  });
  const submit = useMutation({
    mutationFn: () => submitBlockQuiz(tree.id, block.id, { questions, answers }),
    onSuccess: data => { setResult(data); onChanged(); }, onError,
  });
  const busy = attach.isPending || update.isPending || remove.isPending || search.isPending || generate.isPending || submit.isPending;
  const mountWeb = (link: string) => { setError(''); attach.mutate({ url: link.trim(), asset_track: assetTrack, locator: locator.trim(), save_to_library: saveToLibrary, ...(atomId ? { atom_id: Number(atomId) } : {}) }); };
  const status = result?.status ?? progress?.status ?? 'UNSTARTED';
  const best = result?.best_accuracy ?? progress?.best_accuracy ?? 0;
  const statusText = status === 'COMPLETED' ? `已完成 ✓ · 最高正确率 ${Math.round(best * 100)}%` : status === 'NEEDS_REVIEW' ? '待强化 · 需核心点全对且正确率 ≥ 75%' : status === 'LEARNING' ? '学习中 · 需核心点全对且正确率 ≥ 75%' : '未开始';
  const resources = resourcesQuery.data?.resources ?? block.resources ?? [];
  const candidateData = searchResults ?? resourcesQuery.data;
  const renderResource = (resource: BlockResourceItem, allowEdit = true) => {
    const track = resourceTrack(resource);
    const href = resolvePublicAssetLink(resource.url, resource.locator);
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
      {allowEdit && <div className="kb-resource-adjustments flex flex-wrap items-center gap-2">
        <label className="text-sm">轨道<select className="kb-study-select" aria-label={`${resource.title}的资源轨道`} value={track} disabled={busy} onChange={event => {
          setError(''); update.mutate({ resource_id: resource.id, asset_track: event.target.value as AssetTrack });
        }}><option value="spine">主线</option><option value="spotlight">神作</option><option value="wiki">维基</option></select></label>
        <label className="text-sm">绑定原子知识点<select className="kb-study-select" aria-label={`${resource.title}绑定的原子知识点`} value={resource.atom ?? ''} disabled={busy} onChange={event => {
          setError(''); update.mutate({ resource_id: resource.id, atom_id: event.target.value ? Number(event.target.value) : null, step_id: null });
        }}><option value="">整个知识块</option>{atoms.map(atom => <option key={atom.id} value={atom.id}>{atom.name}</option>)}</select></label>
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => { setError(''); remove.mutate(resource.id); }}>移除挂载</Button>
      </div>}
    </article>;
  };
  return <Dialog open onOpenChange={open => { if (!open) onClose(); }}>
    <DialogContent className="sm:max-w-[900px] max-h-[90dvh] overflow-y-auto kb-study-dialog">
      <DialogHeader><DialogTitle>{block.code} · {block.short_title}</DialogTitle>
        <DialogDescription>第 {block.layer} 层 · 学习资源与块级闯关检测</DialogDescription></DialogHeader>
      <p className={`kb-study-status ${status === 'COMPLETED' ? 'is-complete' : status === 'NEEDS_REVIEW' ? 'is-review' : ''}`}>{statusText}</p>
      <div className="flex gap-2" role="tablist" aria-label="知识块学习">
        <Button id="kb-study-resources-tab" role="tab" aria-selected={tab === 'resources'} aria-controls="kb-study-resources" variant={tab === 'resources' ? 'default' : 'outline'} onClick={() => setTab('resources')}>学习资源</Button>
        <Button id="kb-study-quiz-tab" role="tab" aria-selected={tab === 'quiz'} aria-controls="kb-study-quiz" variant={tab === 'quiz' ? 'default' : 'outline'} onClick={() => setTab('quiz')}>闯关检测</Button>
      </div>
      {error && <p role="alert" className="text-red-600">{error}</p>}
      {tab === 'resources' ? <section id="kb-study-resources" role="tabpanel" aria-labelledby="kb-study-resources-tab" className="space-y-4">
        <h3 className="font-semibold">已挂载资源 · {resourcesQuery.data?.resources.length ?? block.resources?.length ?? 0}</h3>
        {result && result.weak_atoms.length > 0 && <p className="kb-study-status is-review">优先回看：{result.weak_atoms.map(atom => atom.name).join('、')}</p>}
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
        <section className="space-y-2" aria-label="维基百科概念词条推荐">
          <h3 className="font-semibold">📖 维基百科概念词条推荐</h3>
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
              <option value="spotlight">🌟 单点神作</option><option value="spine">🎬 主线配套</option><option value="wiki">📖 百科词条</option>
            </select></label>
            <label className="flex-1 text-sm">定位符<Input aria-label="资源定位符" value={locator} maxLength={300} placeholder="P3 · 05:20 或 #资本市场线" onChange={event => setLocator(event.target.value)} /></label>
          </div>
          <form className="flex flex-wrap gap-2" onSubmit={event => { event.preventDefault(); mountWeb(url); }}>
            <Input className="flex-1 min-w-48" aria-label="公开 HTTPS 链接" type="url" required pattern="https://.*" value={url} maxLength={1000} placeholder="https://…" onChange={event => setUrl(event.target.value)} />
            <Button disabled={busy || !url.trim()}>{attach.isPending ? '读取并挂载中…' : '读取正文并挂载'}</Button>
          </form>
        </div>
      </section> : <section id="kb-study-quiz" role="tabpanel" aria-labelledby="kb-study-quiz-tab" className="space-y-4">
        <label className="block text-sm">题型模式<select className="kb-study-select" value={mode} disabled={busy || questions.length > 0 && !result} onChange={event => setMode(event.target.value as BlockQuizMode)}>
          <option value="objective">客观题快测（默认 3～4 题）</option><option value="challenge">进阶主观/计算题挑战（客观题 + 1 道开放题）</option>
        </select></label>
        <p className="text-sm text-muted-foreground">完成标准：所有核心点关联题通过，且总得分率 ≥ 75%。主观题得分率 ≥ 75% 视为通过。核心点较多时会增加题量以逐个覆盖。</p>
        <Button disabled={busy} onClick={() => { setError(''); generate.mutate(false); }}>{generate.isPending ? '正在出题…' : questions.length ? '重新出题' : '开始闯关检测'}</Button>
        {questions.map((question, index) => {
          const graded = result?.results.find(item => item.id === question.id);
          return <article key={question.id} className={`kb-study-resource space-y-3 ${graded ? graded.passed ? 'is-complete' : 'is-review' : ''}`}>
            <p className="text-sm">第 {index + 1} 题 · {question.atom_name} <span className="kb-badge">{question.membership_type === 'core' ? 'CORE 核心' : 'EXT 拓展'}</span></p>
            <MarkdownContent content={question.stem} />
            {question.q_type === 'objective' ? <fieldset disabled={busy || !!result} className="grid gap-2"><legend className="sr-only">选择第 {index + 1} 题答案</legend>
              {Object.entries(question.options).map(([key, label]) => <label key={key} className={`kb-study-option ${answers[question.id] === key ? 'selected' : ''}`}>
                <input type="radio" name={question.id} value={key} checked={answers[question.id] === key} onChange={() => setAnswers(current => ({ ...current, [question.id]: key }))} /><span>{key}.</span><MarkdownContent content={label} />
              </label>)}
            </fieldset> : <><p className="text-sm text-muted-foreground">考察维度：{question.assessment_hint}</p><Textarea aria-label={`${question.atom_name}的作答`} rows={6} maxLength={20000} value={answers[question.id] ?? ''} disabled={busy || !!result} onChange={event => setAnswers(current => ({ ...current, [question.id]: event.target.value }))} placeholder="写出推导、计算过程或机制分析…" /></>}
            {graded && <div className="space-y-2 text-sm"><strong>{graded.passed ? '已通过' : '待强化'} · 得分 {Math.round(graded.score_ratio * 100)}%</strong><MarkdownContent content={`标准答案：${graded.correct_answer}`} /><MarkdownContent content={graded.explanation} /><p>{graded.feedback}</p></div>}
          </article>;
        })}
        {questions.length > 0 && !result && <Button disabled={busy || questions.some(question => !answers[question.id]?.trim())} onClick={() => { setError(''); submit.mutate(); }}>{submit.isPending ? '正在判分…' : '提交并查看结果'}</Button>}
        {result && <div className="space-y-3" aria-live="polite">
          <div className={`kb-study-status ${result.block_completed ? 'is-complete' : 'is-review'}`}><strong>{result.block_completed ? '当前知识块已完成！' : '当前知识块待强化'}</strong><p>总得分率 {Math.round(result.accuracy * 100)}% · 核心点{result.core_passed ? '全部通过' : '尚未全部通过'}</p><p>{result.summary_message}</p></div>
          {questions.length === 0 && result.results.map(item => <article key={item.id} className="kb-study-resource text-sm"><strong>{item.atom_name} · {item.passed ? '已通过' : '待强化'} · {Math.round(item.score_ratio * 100)}%</strong><MarkdownContent content={`标准答案：${item.correct_answer}`} /><MarkdownContent content={item.explanation} /><p>{item.feedback}</p></article>)}
          {result.weak_atoms.length > 0 && <><p className="font-semibold text-red-600">待强化原子知识点：{result.weak_atoms.map(atom => atom.name).join('、')}</p><Button variant="outline" onClick={() => setTab('resources')}>回看对应学习资源</Button>{result.recommended_resources.map(resource => renderResource(resource, false))}</>}
          {!result.block_completed && <Button disabled={busy} onClick={() => { setError(''); generate.mutate(true); }}>针对薄弱点换题复测</Button>}
        </div>}
      </section>}
    </DialogContent>
  </Dialog>;
}
