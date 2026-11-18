import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { autoDiscoverTreePublicAssets, getTreePublicAssets, importTreePublicAsset, resolvePublicAssetLink } from '@/lib/knowledgeBuilderApi';
import { useAuthStore } from '@/store/useAuthStore';
import type {
  AssetSourceKind, AssetTrack, KnowledgeTreeBuildDetail, PedagogicalRole,
  PublicAssetCatalogItem, TreePublicAssetImportPayload,
} from '@/types/knowledgeBuilder';

interface Props {
  tree: KnowledgeTreeBuildDetail;
  onClose: () => void;
  onChanged: () => void;
}

type AssetFilter = 'all' | AssetTrack | 'internal';
const roleLabels: Record<string, string> = {
  series_episode: '系列主线讲次', concept_intuition: '概念直觉与动画',
  core_derivation: '核心推导与机制', worked_example: '典型例题实战', wiki_reference: '权威词条定义',
};

function errorMessage(error: unknown): string {
  const data = (error as { response?: { data?: unknown } })?.response?.data;
  if (typeof data === 'string') return data;
  if (Array.isArray(data)) return data.join('；');
  if (data && typeof data === 'object') return Object.values(data).flat().join('；');
  return error instanceof Error ? error.message : '请求失败，请稍后重试。';
}

export function TreePublicAssetModal({ tree, onClose, onChanged }: Props) {
  const userId = useAuthStore(state => state.user?.id);
  const queryClient = useQueryClient();
  const queryKey = ['knowledge-tree-public-assets', userId, tree.id];
  const assetsQuery = useQuery({ queryKey, queryFn: ({ signal }) => getTreePublicAssets(tree.id, signal) });
  const isIntl = (assetsQuery.data?.region_pref ?? tree.region_pref ?? 'cn') === 'intl';
  const trackLabels: Record<AssetTrack, string> = {
    spine: '🎬 主线配套课', spotlight: '🌟 单点神作', wiki: isIntl ? '📖 Wikipedia 词条' : '📖 专业开源 Wiki 词条',
  };
  const sourceLabels: Record<AssetSourceKind, string> = {
    course: '站内课程', library: '个人资料', web: '公开课 / 网页', bilibili: 'B站合集',
    github: '开源讲义仓库', wikipedia: isIntl ? 'Wikipedia' : 'OI-Wiki / 开源学科词条', youtube: isIntl ? 'YouTube / OCW' : '公开视频', marketplace: '共享市场',
  };
  const filters: { value: AssetFilter; label: string }[] = [
    { value: 'all', label: '全部' },
    { value: 'spine', label: '🎬 主线成套课（自动按分P对位到各块）' },
    { value: 'spotlight', label: '🌟 单点神作（直达难点）' },
    { value: 'wiki', label: trackLabels.wiki },
    { value: 'internal', label: '🏛️ 站内课程专辑与共享市场' },
  ];
  const [tab, setTab] = useState<'catalog' | 'import'>('catalog');
  const [filter, setFilter] = useState<AssetFilter>('all');
  const [url, setUrl] = useState('');
  const [title, setTitle] = useState('');
  const [track, setTrack] = useState<AssetTrack | ''>('');
  const [role, setRole] = useState<PedagogicalRole>('');
  const [outline, setOutline] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const mount = useMutation({
    mutationFn: (payload: TreePublicAssetImportPayload) => importTreePublicAsset(tree.id, payload),
    onSuccess: async (data, payload) => {
      setMessage(`已向本树挂载 ${data.mounted_count} 条${trackLabels[data.asset_track]}资源。`);
      if (payload.url) { setUrl(''); setTitle(''); setOutline(''); }
      onChanged();
      await Promise.all([
        queryClient.invalidateQueries({ queryKey }),
        queryClient.invalidateQueries({ queryKey: ['knowledge-block-resources', userId, tree.id] }),
      ]);
    },
    onError: (err: unknown) => setError(errorMessage(err)),
  });
  const discoverMutation = useMutation({
    mutationFn: () => autoDiscoverTreePublicAssets(tree.id),
    onSuccess: async (data) => {
      setMessage(`已从全网智能发现并向本树挂载 ${data.mounted_count} 条资源。`);
      onChanged();
      await Promise.all([
        queryClient.invalidateQueries({ queryKey }),
        queryClient.invalidateQueries({ queryKey: ['knowledge-block-resources', userId, tree.id] }),
      ]);
    },
    onError: (err: unknown) => setError(errorMessage(err)),
  });
  const importAsset = (payload: TreePublicAssetImportPayload) => {
    setError(''); setMessage(''); mount.mutate(payload);
  };
  const data = assetsQuery.data;
  const catalog = data?.catalog_assets.filter(asset => filter === 'all' || (
    filter === 'internal' ? ['course', 'library', 'marketplace'].includes(asset.source_kind) : asset.asset_track === filter
  ));
  const showInternal = filter === 'all' || filter === 'internal';
  const showWiki = filter === 'all' || filter === 'wiki';
  const visibleCount = (catalog?.length ?? 0)
    + (showInternal ? (data?.marketplace_listings.length ?? 0) + (data?.albums.length ?? 0) : 0)
    + (showWiki ? data?.wiki_candidates.length ?? 0 : 0);
  const renderCatalog = (asset: PublicAssetCatalogItem) => <article key={`catalog-${asset.id}`} className="kb-public-asset-card space-y-3">
    <div className="flex flex-wrap items-center gap-2">
      <a href={resolvePublicAssetLink(asset.url)} target="_blank" rel="noopener noreferrer" className="font-semibold underline underline-offset-4">{asset.title}</a>
      <span className="kb-badge">{sourceLabels[asset.source_kind]}</span>
      <span className={`kb-badge kb-track-${asset.asset_track}`}>{trackLabels[asset.asset_track]}</span>
      {asset.pedagogical_role && <span className="kb-badge">{roleLabels[asset.pedagogical_role] ?? asset.pedagogical_role}</span>}
    </div>
    <p className="text-sm text-muted-foreground">{asset.description}</p>
    {asset.segments.length > 0 && <ol className="kb-public-asset-segments" aria-label={`${asset.title}分P与章节目录`}>
      {asset.segments.map(segment => <li key={`${segment.index}-${segment.url}`}>
        <a href={resolvePublicAssetLink(segment.url || asset.url, segment.locator || (!segment.url && asset.source_kind === 'bilibili' ? `P${segment.index}` : undefined))} target="_blank" rel="noopener noreferrer" className="underline underline-offset-4">
          {segment.locator || `第 ${segment.index} 讲`} · {segment.title}
        </a>
        {segment.summary && <p className="text-xs text-muted-foreground">{segment.summary}</p>}
      </li>)}
    </ol>}
    <Button size="sm" disabled={mount.isPending || discoverMutation.isPending} onClick={() => importAsset({ public_asset_id: asset.id })}>一键对齐挂载到本树</Button>
  </article>;

  return <Dialog open onOpenChange={open => { if (!open) onClose(); }}>
    <DialogContent className="kb-public-assets-dialog sm:max-w-[1000px] max-h-[90dvh] overflow-y-auto">
      <DialogHeader>
        <DialogTitle>公开资产池 &amp; 整树挂载</DialogTitle>
        <DialogDescription>{tree.subject} · 精选成套课、单点讲解与权威词条，按知识块自动对位挂载。</DialogDescription>
      </DialogHeader>
      <div className="kb-public-assets-summary" aria-label="整树三轨挂载概览">
        {data ? <>
          <p>🎬 主线配套课 ({data.mounted_summary.spine_count ?? (data.mounted_summary as Record<string, number>).spine ?? 0}) · 🌟 单点神作 ({data.mounted_summary.spotlight_count ?? (data.mounted_summary as Record<string, number>).spotlight ?? 0}) · {trackLabels.wiki} ({data.mounted_summary.wiki_count ?? (data.mounted_summary as Record<string, number>).wiki ?? 0})</p>
          <p className="text-sm text-muted-foreground">{isIntl ? '国际信源模式（YouTube / Wikipedia / GitHub / OCW）' : '国内信源模式（B站 / OI-Wiki / Hello-Algo / 开源讲义仓库 / 站内）'}</p>
        </> : <p>{assetsQuery.isLoading ? '正在读取三轨挂载概览…' : '三轨挂载概览读取失败。'}</p>}
        <Button size="sm" disabled={mount.isPending || discoverMutation.isPending} onClick={() => {
          setError(''); setMessage(''); discoverMutation.mutate();
        }}>{discoverMutation.isPending ? '正在全网搜索并匹配…' : '🌐 全网智能搜索并自动挂载'}</Button>
      </div>
      <div className="kb-public-assets-tabs flex flex-wrap gap-2" role="tablist" aria-label="公开资产导入方式">
        <Button id="kb-public-catalog-tab" role="tab" aria-selected={tab === 'catalog'} aria-controls="kb-public-catalog-panel" variant={tab === 'catalog' ? 'default' : 'outline'} onClick={() => setTab('catalog')}>精选公开资产池 &amp; 站内共享市场</Button>
        <Button id="kb-public-import-tab" role="tab" aria-selected={tab === 'import'} aria-controls="kb-public-import-panel" variant={tab === 'import' ? 'default' : 'outline'} onClick={() => setTab('import')}>粘贴链接智能拆集导入</Button>
      </div>
      {error && <p role="alert" className="text-red-600">{error}</p>}
      {message && <p role="status" className="kb-study-status is-complete">{message}</p>}
      {mount.isPending && <p role="status" className="text-sm">正在解析资源并对齐知识树，请稍候…</p>}
      {tab === 'catalog' ? <section id="kb-public-catalog-panel" role="tabpanel" aria-labelledby="kb-public-catalog-tab" className="space-y-4">
        <div className="kb-public-assets-filters flex flex-wrap gap-2" role="group" aria-label="按资源轨道筛选">
          {filters.map(item => <Button key={item.value} size="sm" variant={filter === item.value ? 'default' : 'outline'} aria-pressed={filter === item.value} onClick={() => setFilter(item.value)}>{item.label}</Button>)}
        </div>
        {assetsQuery.isLoading && <p role="status">正在读取精选资产池…</p>}
        {assetsQuery.error && <p role="alert">{errorMessage(assetsQuery.error)} <Button size="sm" variant="outline" onClick={() => void assetsQuery.refetch()}>重新读取</Button></p>}
        {data && visibleCount === 0 && <p className="text-sm text-muted-foreground">当前筛选下暂无资源，可以粘贴链接导入。</p>}
        <div className="kb-public-assets-grid">
          {catalog?.map(renderCatalog)}
          {showWiki && data?.wiki_candidates.map(candidate => <article key={`wiki-${candidate.url}`} className="kb-public-asset-card space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <a href={resolvePublicAssetLink(candidate.url, candidate.locator)} target="_blank" rel="noopener noreferrer" className="font-semibold underline underline-offset-4">{candidate.title}</a>
              <span className="kb-badge">{sourceLabels.wikipedia}</span><span className="kb-badge kb-track-wiki">{trackLabels.wiki}</span>
              <span className="kb-badge">{roleLabels[candidate.pedagogical_role] ?? (candidate.pedagogical_role || '权威词条定义')}</span>
              {candidate.locator && <span className="kb-badge">{candidate.locator}</span>}
            </div>
            <p className="text-sm text-muted-foreground">{candidate.summary}</p>
            <Button size="sm" disabled={mount.isPending || discoverMutation.isPending} onClick={() => importAsset({ url: resolvePublicAssetLink(candidate.url, candidate.locator), title: candidate.title, asset_track: 'wiki', pedagogical_role: candidate.pedagogical_role })}>一键对齐挂载到本树</Button>
          </article>)}
          {showInternal && data?.marketplace_listings.map(listing => <article key={`marketplace-${listing.id}`} className="kb-public-asset-card space-y-3">
            <div className="flex flex-wrap items-center gap-2"><a href="/courses" target="_blank" rel="noopener noreferrer" className="font-semibold underline underline-offset-4">{listing.title}</a><span className="kb-badge">共享市场</span><span className="kb-badge">{listing.content_type}</span></div>
            <p className="text-sm text-muted-foreground">{listing.description}</p>
            {listing.subject && <p className="text-xs text-muted-foreground">{listing.subject}</p>}
            <Button size="sm" disabled={mount.isPending || discoverMutation.isPending} onClick={() => importAsset({ marketplace_listing_id: listing.id })}>一键对齐挂载到本树</Button>
          </article>)}
          {showInternal && data?.albums.map(album => <article key={`album-${album.id}`} className="kb-public-asset-card space-y-3">
            <div className="flex flex-wrap items-center gap-2"><a href="/courses" target="_blank" rel="noopener noreferrer" className="font-semibold underline underline-offset-4">{album.name}</a><span className="kb-badge">站内课程专辑</span><span className="kb-badge">{album.course_count} 门课程</span></div>
            <p className="text-sm text-muted-foreground">{album.description}</p>
            <Button size="sm" disabled={mount.isPending || discoverMutation.isPending} onClick={() => importAsset({ album_id: album.id })}>一键对齐挂载到本树</Button>
          </article>)}
        </div>
      </section> : <section id="kb-public-import-panel" role="tabpanel" aria-labelledby="kb-public-import-tab">
        <form className="kb-public-assets-form space-y-4" onSubmit={event => {
          event.preventDefault();
          importAsset({ url: url.trim(), ...(title.trim() ? { title: title.trim() } : {}), ...(track ? { asset_track: track } : {}), ...(role ? { pedagogical_role: role } : {}), ...(outline.trim() ? { outline_text: outline.trim() } : {}) });
        }}>
          <p className="text-sm text-muted-foreground">{isIntl ? '支持 YouTube、Wikipedia、GitHub 开源讲义及国际公开课。' : '支持 B站多P或单品视频、专业开源 Wiki（如 OI-Wiki / Hello-Algo）、开源学科讲义及站内课程。'}解析后自动沉淀进资产池，并挂载到本树。</p>
          <label className="block text-sm space-y-2"><span>公开资源 HTTPS 链接</span><Input type="url" required pattern="https://.*" maxLength={2000} value={url} placeholder="https://www.bilibili.com/video/BV…" onChange={event => setUrl(event.target.value)} disabled={mount.isPending || discoverMutation.isPending} /></label>
          <label className="block text-sm space-y-2"><span>资源标题（可选）</span><Input value={title} maxLength={300} placeholder="留空时自动读取标题" onChange={event => setTitle(event.target.value)} disabled={mount.isPending || discoverMutation.isPending} /></label>
          <div className="kb-public-assets-form-grid">
            <label className="block text-sm">挂载轨道<select className="kb-study-select" value={track} disabled={mount.isPending || discoverMutation.isPending} onChange={event => setTrack(event.target.value as AssetTrack | '')}>
              <option value="">自动识别</option><option value="spine">主线成套课 Spine（拆集分发到整树）</option><option value="spotlight">单点神作 Spotlight</option><option value="wiki">{trackLabels.wiki}</option>
            </select></label>
            <label className="block text-sm">教学角色<select className="kb-study-select" value={role} disabled={mount.isPending || discoverMutation.isPending} onChange={event => setRole(event.target.value as PedagogicalRole)}>
              <option value="">自动识别</option>{Object.entries(roleLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select></label>
          </div>
          <details className="kb-public-asset-card">
            <summary className="cursor-pointer text-sm font-medium">补充自定义分P/章节目录（每行一集，自动生成 ?p=N 直达链接）</summary>
            <p className="my-2 text-sm text-muted-foreground">按实际顺序填写每集标题。导入时会解析目录，并为 B站分P生成对应直达链接。</p>
            <Textarea aria-label="自定义分P或章节目录" rows={7} value={outline} maxLength={30000} disabled={mount.isPending || discoverMutation.isPending} placeholder={'第1集 金融市场概览\n第2集 资本资产定价\n第3集 资本市场线'} onChange={event => setOutline(event.target.value)} />
          </details>
          <Button type="submit" disabled={mount.isPending || discoverMutation.isPending || !url.trim()}>{mount.isPending ? '正在解析并挂载…' : '解析并自动挂载到知识树'}</Button>
        </form>
      </section>}
    </DialogContent>
  </Dialog>;
}
