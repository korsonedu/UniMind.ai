import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  attachBlockResource,
  attachBlockResourceToProject,
  autoDiscoverBlockResources,
  deleteBlockResource,
  getBlockResources,
  resolvePublicAssetLink,
  updateBlockResource,
  voteBlockResource,
} from '@/lib/knowledgeBuilderApi';
import type {
  AssetSourceKind,
  AssetTrack,
  BlockResourceItem,
  BlockResourcePayload,
  BlockResourcesResponse,
  BlockResourceUpdatePayload,
  KnowledgeTreeBuildDetail,
  LearningBlock,
  MicroLessonCitation,
  SourceAlignmentItem,
  TreeAtomPoint,
} from '@/types/knowledgeBuilder';
import { useAuthStore } from '@/store/useAuthStore';
import { t } from '@/i18n';

interface Props {
  open: boolean;
  tree: KnowledgeTreeBuildDetail;
  block: LearningBlock;
  atoms: TreeAtomPoint[];
  activeAtom?: TreeAtomPoint;
  taskProjectId: number | null;
  focusedCitation?: MicroLessonCitation | SourceAlignmentItem | null;
  onClose: () => void;
  onChanged: () => void;
}

const roleLabels: Record<string, string> = {
  series_episode: '系列主线讲次',
  concept_intuition: '概念直觉',
  core_derivation: '核心推导',
  worked_example: '例题实战',
  wiki_reference: '权威词条定义',
  primary_textbook: '主讲教材',
  official_syllabus: '权威考纲',
  video_lecture: '精讲视频',
};

function errorMessage(error: unknown): string {
  const data = (error as { response?: { data?: unknown } })?.response?.data;
  if (typeof data === 'string') return data;
  if (Array.isArray(data)) return data.join('；');
  if (data && typeof data === 'object') return Object.values(data).flat().join('；');
  return error instanceof Error ? error.message : '请求失败，请稍后重试。';
}

function resourceTrack(resource: BlockResourceItem): AssetTrack {
  return resource.asset_track ?? (resource.source_kind === 'course' ? 'spine' : resource.source_kind === 'wikipedia' ? 'wiki' : 'spotlight');
}

export function BlockResourceDrawer({
  open,
  tree,
  block,
  atoms,
  activeAtom,
  taskProjectId,
  focusedCitation,
  onClose,
  onChanged,
}: Props) {
  const userId = useAuthStore(state => state.user?.id);
  const queryClient = useQueryClient();
  const drawerKey = ['knowledge-block-resources-full', userId, tree.id, block.id];
  const fastKey = ['knowledge-block-resources', userId, tree.id, block.id];
  const resourcesQuery = useQuery({
    queryKey: drawerKey,
    enabled: open,
    queryFn: () => getBlockResources(tree.id, block.id, undefined, { includeCandidates: true }),
  });

  const [query, setQuery] = useState(`${tree.subject} ${activeAtom?.name ?? block.short_title}`);
  const [url, setUrl] = useState('');
  const [atomId, setAtomId] = useState(activeAtom ? String(activeAtom.id) : '');
  const [assetTrack, setAssetTrack] = useState<AssetTrack>('spotlight');
  const [locator, setLocator] = useState('');
  const [saveToLibrary, setSaveToLibrary] = useState(false);
  const [searchResults, setSearchResults] = useState<BlockResourcesResponse | null>(null);
  const [searched, setSearched] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const onError = (err: unknown) => setError(errorMessage(err));
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: drawerKey });
    void queryClient.invalidateQueries({ queryKey: fastKey });
    onChanged();
  };

  const attach = useMutation({
    mutationFn: (payload: BlockResourcePayload) => attachBlockResource(tree.id, block.id, payload),
    onSuccess: () => { setUrl(''); setNotice('已挂载资源到本知识块。'); refresh(); },
    onError,
  });
  const update = useMutation({
    mutationFn: (payload: BlockResourceUpdatePayload) => updateBlockResource(tree.id, block.id, payload),
    onSuccess: refresh,
    onError,
  });
  const remove = useMutation({
    mutationFn: (id: number) => deleteBlockResource(tree.id, block.id, id),
    onSuccess: refresh,
    onError,
  });
  const voteMutation = useMutation({
    mutationFn: ({ resourceId, vote }: { resourceId: number; vote: 1 | -1 | 0 }) =>
      voteBlockResource(tree.id, block.id, resourceId, vote),
    onSuccess: refresh,
    onError,
  });
  const search = useMutation({
    mutationFn: () => getBlockResources(tree.id, block.id, query),
    onSuccess: data => { setSearchResults(data); setSearched(true); },
    onError,
  });
  const blockDiscover = useMutation({
    mutationFn: () => autoDiscoverBlockResources(tree.id, block.id, activeAtom?.id),
    onSuccess: data => {
      setNotice(data.mounted_count > 0 ? `已为当前知识块补充挂载 ${data.mounted_count} 条兜底外部资源。` : '暂未发现更高分的新增外部资源，可直接粘贴链接补充。');
      refresh();
    },
    onError,
  });
  const useResource = useMutation({
    mutationFn: (id: number) => attachBlockResourceToProject(tree.id, block.id, taskProjectId!, id),
    onSuccess: data => { setNotice(data.notice); refresh(); },
    onError,
  });

  const busy = attach.isPending || update.isPending || remove.isPending || search.isPending || blockDiscover.isPending || useResource.isPending || voteMutation.isPending;
  const candidateData = searchResults ?? resourcesQuery.data;
  const isIntl = (candidateData?.region_pref ?? tree.region_pref ?? 'cn') === 'intl';
  const resources = resourcesQuery.data?.resources ?? block.resources ?? [];
  const alignments = resourcesQuery.data?.source_alignments ?? [];

  const sourceLabels: Record<AssetSourceKind, string> = {
    course: '站内课程',
    library: '个人资料快照',
    web: '公开网页',
    bilibili: 'B站',
    github: '开源讲义仓库',
    wikipedia: isIntl ? 'Wikipedia' : 'OI-Wiki / 开源学科词条',
    youtube: isIntl ? 'YouTube / OCW' : '公开视频',
    marketplace: '共享市场',
  };
  const trackLabels: Record<AssetTrack, string> = {
    spine: '🎬 主线配套课',
    spotlight: '🌟 单点神作',
    wiki: isIntl ? '📖 Wikipedia 词条' : '📖 专业开源 Wiki 词条',
  };

  const mountWeb = (link: string) => {
    setError('');
    setNotice('');
    attach.mutate({
      url: link.trim(),
      asset_track: assetTrack,
      locator: locator.trim(),
      save_to_library: saveToLibrary,
      ...(atomId ? { atom_id: Number(atomId) } : {}),
    });
  };

  const citationTitle = focusedCitation
    ? ('source_title' in focusedCitation ? focusedCitation.source_title : focusedCitation.title)
    : '';
  const citationUrl = focusedCitation
    ? ('source_url' in focusedCitation ? focusedCitation.source_url : focusedCitation.url)
    : '';
  const citationExcerpt = focusedCitation
    ? (focusedCitation.full_excerpt || ('excerpt_quote' in focusedCitation ? focusedCitation.excerpt_quote : focusedCitation.quote))
    : '';

  return (
    <Dialog open={open} onOpenChange={nextOpen => { if (!nextOpen) onClose(); }}>
      <DialogContent className="sm:max-w-[820px] max-h-[88dvh] overflow-y-auto space-y-4">
        <DialogHeader>
          <DialogTitle>📚 权威出处与延伸资源管理 · {block.short_title}</DialogTitle>
          <DialogDescription>
            {activeAtom ? `当前知识点：${activeAtom.name}` : '查看主线原文切片、管理延伸参考，或按需补充单块外部资源。'}
          </DialogDescription>
        </DialogHeader>

        {notice && <p role="status" className="rounded-lg border border-emerald-200 bg-emerald-50/70 px-3 py-2 text-sm text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-100">{notice}</p>}
        {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50/70 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">{error}</p>}

        {focusedCitation && (
          <section className="space-y-2 rounded-xl border border-primary/30 bg-primary/5 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="kb-badge">📌 主线原文切片</span>
              <strong className="text-sm">{citationTitle}</strong>
              {focusedCitation.section_title && <span className="text-xs text-muted-foreground">· {focusedCitation.section_title}</span>}
              {focusedCitation.locator && <span className="kb-badge kb-resource-locator">{focusedCitation.locator}</span>}
            </div>
            <p className="whitespace-pre-wrap text-sm leading-relaxed">{citationExcerpt || '暂无原文切片文本。'}</p>
            {citationUrl && (
              <a
                href={resolvePublicAssetLink(citationUrl, focusedCitation.locator) ?? citationUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-block text-sm font-medium underline underline-offset-4"
              >
                直达原始出处（{focusedCitation.locator || '打开链接'}） →
              </a>
            )}
          </section>
        )}

        {alignments.length > 0 && (
          <section className="space-y-2">
            <h3 className="font-semibold text-sm">🧭 本块已对齐主线出处（{alignments.length}）</h3>
            <div className="space-y-2">
              {alignments.map(item => {
                const href = item.source_url ? resolvePublicAssetLink(item.source_url, item.locator) : undefined;
                return (
                  <article key={item.id} className="rounded-lg border bg-card p-3 space-y-1.5 text-sm">
                    <div className="flex flex-wrap items-center gap-2">
                      <strong>{item.source_title}</strong>
                      {item.locator && <span className="kb-badge kb-resource-locator">{item.locator}</span>}
                      <span className="kb-badge">{roleLabels[item.alignment_role] ?? item.alignment_role}</span>
                      {item.atom_name && <span className="kb-badge">{item.atom_name}</span>}
                    </div>
                    <p className="text-xs text-muted-foreground">{item.section_title}{item.match_reason ? ` · ${item.match_reason}` : ''}</p>
                    {item.excerpt_quote && <p className="text-xs leading-relaxed text-muted-foreground whitespace-pre-wrap">{item.excerpt_quote}</p>}
                    {href && (
                      <a href={href} target="_blank" rel="noopener noreferrer" className="text-xs underline underline-offset-4">
                        打开对应分 P / 原文 →
                      </a>
                    )}
                  </article>
                );
              })}
            </div>
          </section>
        )}

        <section className="space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-semibold text-sm">🔗 延伸参考资源（{resources.length}）</h3>
            <Button size="sm" variant="outline" disabled={busy} onClick={() => { setError(''); setNotice(''); blockDiscover.mutate(); }}>
              {blockDiscover.isPending ? '正在单块兜底搜索…' : '🌐 单块按需补充外部资源'}
            </Button>
          </div>
          {resourcesQuery.isLoading && <p className="text-sm text-muted-foreground">正在读取资源…</p>}
          {resources.length === 0 && !resourcesQuery.isLoading && (
            <p className="text-sm text-muted-foreground">当前知识块暂未挂载额外延伸链接。主线资料与原生微课件已可直接学习。</p>
          )}
          <div className="space-y-2">
            {resources.map(resource => {
              const track = resourceTrack(resource);
              const href = resource.source_kind === 'course' && resource.course_id
                ? `/course/${resource.course_id}`
                : resolvePublicAssetLink(resource.url, resource.locator);
              return (
                <article key={resource.id} className="kb-study-resource space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <a href={href} target="_blank" rel="noopener noreferrer" className="font-semibold underline">{resource.title}</a>
                    <span className="kb-badge">{sourceLabels[resource.source_kind]}</span>
                    {resource.locator && <span className="kb-badge kb-resource-locator">{resource.locator}</span>}
                    {resource.origin === 'auto' && <span className="kb-badge">AI 自动挂载</span>}
                  </div>
                  {resource.excerpt && <p className="text-xs text-muted-foreground whitespace-pre-wrap">{resource.excerpt}</p>}
                  <div className="flex flex-wrap items-center gap-2">
                    {taskProjectId !== null && (
                      <Button size="sm" variant="outline" disabled={busy} onClick={() => { setError(''); useResource.mutate(resource.id); }}>
                        用于当前小宇项目
                      </Button>
                    )}
                    <Button size="sm" variant={resource.user_vote === 1 ? 'default' : 'outline'} disabled={busy} onClick={() => voteMutation.mutate({ resourceId: resource.id, vote: resource.user_vote === 1 ? 0 : 1 })}>
                      👍 {resource.upvotes ?? 0}
                    </Button>
                    <Button size="sm" variant={resource.user_vote === -1 ? 'default' : 'outline'} disabled={busy} onClick={() => voteMutation.mutate({ resourceId: resource.id, vote: resource.user_vote === -1 ? 0 : -1 })}>
                      👎 {resource.downvotes ?? 0}
                    </Button>
                    <select className="kb-study-select" aria-label={`${resource.title}的资源轨道`} value={track} disabled={busy} onChange={e => update.mutate({ resource_id: resource.id, asset_track: e.target.value as AssetTrack })}>
                      <option value="spine">主线</option>
                      <option value="spotlight">神作</option>
                      <option value="wiki">{trackLabels.wiki}</option>
                    </select>
                    <select className="kb-study-select" aria-label={`${resource.title}绑定的原子知识点`} value={resource.atom ?? ''} disabled={busy} onChange={e => update.mutate({ resource_id: resource.id, atom_id: e.target.value ? Number(e.target.value) : null, step_id: null })}>
                      <option value="">整个知识块</option>
                      {atoms.map(atom => <option key={atom.id} value={atom.id}>{atom.name}</option>)}
                    </select>
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => remove.mutate(resource.id)}>移除</Button>
                  </div>
                </article>
              );
            })}
          </div>
        </section>

        <section className="space-y-3 rounded-xl border bg-muted/20 p-4">
          <h3 className="font-semibold text-sm">➕ 手动补充外部链接或搜索候选</h3>
          <form className="flex flex-wrap gap-2" onSubmit={e => { e.preventDefault(); mountWeb(url); }}>
            <Input className="flex-1 min-w-48" aria-label="公开 HTTPS 链接" type="url" required pattern="https://.*" value={url} maxLength={1000} placeholder="https://www.bilibili.com/video/BV…" onChange={e => setUrl(e.target.value)} />
            <Input className="w-40" aria-label="资源定位符" value={locator} maxLength={120} placeholder="P3 · 05:20" onChange={e => setLocator(e.target.value)} />
            <Button disabled={busy || !url.trim()}>{attach.isPending ? '挂载中…' : '挂载链接'}</Button>
          </form>
          <div className="flex flex-wrap items-center gap-3 text-xs">
            <label>轨道 <select className="kb-study-select" value={assetTrack} onChange={e => setAssetTrack(e.target.value as AssetTrack)}>
              <option value="spotlight">🌟 单点神作</option>
              <option value="spine">🎬 主线配套</option>
              <option value="wiki">{trackLabels.wiki}</option>
            </select></label>
            <label>知识点 <select className="kb-study-select" value={atomId} onChange={e => setAtomId(e.target.value)}>
              <option value="">自动匹配</option>
              {atoms.map(atom => <option key={atom.id} value={atom.id}>{atom.name}</option>)}
            </select></label>
            <label className="flex items-center gap-1.5"><input type="checkbox" checked={saveToLibrary} onChange={e => setSaveToLibrary(e.target.checked)} />同时存入个人资料库</label>
          </div>

          <details className="pt-1">
            <summary className="cursor-pointer text-xs font-medium text-muted-foreground">展开联网搜索 / 站内与词条候选</summary>
            <div className="mt-3 space-y-3">
              <form className="flex gap-2" onSubmit={e => { e.preventDefault(); setError(''); search.mutate(); }}>
                <Input aria-label="资源搜索词" value={query} maxLength={300} onChange={e => setQuery(e.target.value)} />
                <Button size="sm" disabled={busy}>{search.isPending ? '搜索中…' : t('联网搜索')}</Button>
              </form>
              {searched && searchResults?.web_candidates.length === 0 && <p className="text-xs text-muted-foreground">未找到匹配的公开 HTTPS 候选，可调整搜索词。</p>}
              {searchResults?.web_candidates.map(candidate => (
                <article key={candidate.url} className="rounded-lg border bg-card p-2.5 text-xs space-y-1">
                  <a href={resolvePublicAssetLink(candidate.url)} target="_blank" rel="noopener noreferrer" className="font-medium underline">{candidate.title}</a>
                  <p className="text-muted-foreground">{candidate.summary}</p>
                  <Button size="sm" variant="outline" disabled={busy} onClick={() => mountWeb(candidate.url)}>挂载到本块</Button>
                </article>
              ))}
              {(candidateData?.internal_candidates?.length ?? 0) > 0 && (
                <div className="space-y-1.5">
                  <p className="text-xs font-medium">站内课程与个人资料</p>
                  {candidateData?.internal_candidates.map((candidate, idx) => (
                    <div key={idx} className="flex items-center justify-between gap-2 rounded-lg border bg-card p-2 text-xs">
                      <span>{candidate.title} ({sourceLabels[candidate.source_kind]})</span>
                      <Button size="sm" variant="outline" disabled={busy} onClick={() => attach.mutate({ ...(candidate.course_id ? { course_id: candidate.course_id } : { library_resource_id: candidate.library_resource_id }), atom_id: candidate.atom_id, step_id: candidate.step_id })}>挂载</Button>
                    </div>
                  ))}
                </div>
              )}
              {(candidateData?.wiki_candidates?.length ?? 0) > 0 && (
                <div className="space-y-1.5">
                  <p className="text-xs font-medium">{trackLabels.wiki}推荐</p>
                  {candidateData?.wiki_candidates?.slice(0, 4).map(candidate => (
                    <div key={candidate.url} className="flex items-center justify-between gap-2 rounded-lg border bg-card p-2 text-xs">
                      <a href={resolvePublicAssetLink(candidate.url, candidate.locator)} target="_blank" rel="noopener noreferrer" className="underline">{candidate.title}</a>
                      <Button size="sm" variant="outline" disabled={busy} onClick={() => attach.mutate({ url: candidate.url, asset_track: 'wiki', pedagogical_role: candidate.pedagogical_role, locator: candidate.locator, ...(atomId ? { atom_id: Number(atomId) } : {}) })}>挂载</Button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </details>
        </section>
      </DialogContent>
    </Dialog>
  );
}
