import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  alignTreeSource,
  autoDiscoverTreePublicAssets,
  createTreeSource,
  deleteSourceAlignment,
  deleteTreeSource,
  getTreePublicAssets,
  importTreePublicAsset,
  listTreeSources,
  resolvePublicAssetLink,
  updateSourceAlignment,
} from '@/lib/knowledgeBuilderApi';
import { useAuthStore } from '@/store/useAuthStore';
import type {
  AssetSourceKind,
  AssetTrack,
  CreateTreeSourcePayload,
  KnowledgeTreeBuildDetail,
  PedagogicalRole,
  PublicAssetCatalogItem,
  SourceTocNode,
  TreePublicAssetImportPayload,
  TreeSourceDocumentItem,
  TreeSourceKind,
} from '@/types/knowledgeBuilder';

interface Props {
  tree: KnowledgeTreeBuildDetail;
  onClose: () => void;
  onChanged: () => void;
}

type AssetFilter = 'all' | AssetTrack | 'internal';
const roleLabels: Record<string, string> = {
  series_episode: '系列主线讲次',
  concept_intuition: '概念直觉与动画',
  core_derivation: '核心推导与机制',
  worked_example: '典型例题实战',
  wiki_reference: '权威词条定义',
  primary_textbook: '主讲教材',
  official_syllabus: '权威考纲',
  video_lecture: '精讲视频',
};

const sourceKindLabels: Record<TreeSourceKind, string> = {
  pdf: '📄 PDF 教材/考纲',
  markdown: '📘 Markdown 讲义',
  text: '📝 纯文本大纲',
  bilibili_series: '📺 B站系列合集',
  course_album: '🏛️ 站内课程专辑',
  web_repo: '📚 开源讲义仓库',
};

function errorMessage(error: unknown): string {
  const data = (error as { response?: { data?: unknown } })?.response?.data;
  if (typeof data === 'string') return data;
  if (Array.isArray(data)) return data.join('；');
  if (data && typeof data === 'object') return Object.values(data).flat().join('；');
  return error instanceof Error ? error.message : '请求失败，请稍后重试。';
}

function TocTreeNodes({ nodes, depth = 0 }: { nodes: SourceTocNode[]; depth?: number }) {
  if (!nodes?.length) return null;
  return (
    <ul className={depth > 0 ? 'ml-4 mt-1 border-l pl-3 space-y-1' : 'space-y-1.5'}>
      {nodes.map(node => (
        <li key={node.node_id} className="text-xs">
          <div className="flex flex-wrap items-baseline gap-1.5">
            <span className="font-mono text-[11px] text-muted-foreground">{node.node_id}</span>
            <strong className="text-foreground">{node.title}</strong>
            {node.locator && node.locator !== node.title && (
              <span className="kb-badge kb-resource-locator">{node.locator}</span>
            )}
            <span className="text-muted-foreground">({node.char_count} 字)</span>
          </div>
          {node.summary && node.summary !== node.title && (
            <p className="text-muted-foreground line-clamp-1">{node.summary}</p>
          )}
          {node.children && node.children.length > 0 && <TocTreeNodes nodes={node.children} depth={depth + 1} />}
        </li>
      ))}
    </ul>
  );
}

export function TreePublicAssetModal({ tree, onClose, onChanged }: Props) {
  const userId = useAuthStore(state => state.user?.id);
  const queryClient = useQueryClient();

  // V2 Source-First queries & state
  const sourcesKey = ['knowledge-tree-sources', userId, tree.id];
  const sourcesQuery = useQuery({
    queryKey: sourcesKey,
    queryFn: ({ signal }) => listTreeSources(tree.id, signal),
  });

  // Legacy public asset pool query (loaded when user opens secondary tab)
  const [mainTab, setMainTab] = useState<'sources' | 'legacy'>('sources');
  const legacyKey = ['knowledge-tree-public-assets', userId, tree.id];
  const assetsQuery = useQuery({
    queryKey: legacyKey,
    enabled: mainTab === 'legacy',
    queryFn: ({ signal }) => getTreePublicAssets(tree.id, signal),
  });

  // V2 Source import form state
  const [sourceKind, setSourceKind] = useState<TreeSourceKind>('markdown');
  const [sourceTitle, setSourceTitle] = useState('');
  const [sourceUrl, setSourceUrl] = useState('');
  const [sourceContent, setSourceContent] = useState('');
  const [sourceOutline, setSourceOutline] = useState('');
  const [selectedAlbumId, setSelectedAlbumId] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [autoAlignAfterImport, setAutoAlignAfterImport] = useState(true);
  const [activeSourceId, setActiveSourceId] = useState<number | null>(null);

  // Legacy form state
  const [legacySubTab, setLegacySubTab] = useState<'catalog' | 'import'>('catalog');
  const [filter, setFilter] = useState<AssetFilter>('all');
  const [url, setUrl] = useState('');
  const [title, setTitle] = useState('');
  const [track, setTrack] = useState<AssetTrack | ''>('');
  const [role, setRole] = useState<PedagogicalRole>('');
  const [outline, setOutline] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const invalidateAll = async () => {
    onChanged();
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: sourcesKey }),
      queryClient.invalidateQueries({ queryKey: legacyKey }),
      queryClient.invalidateQueries({ queryKey: ['knowledge-block-resources', userId, tree.id] }),
      queryClient.invalidateQueries({ queryKey: ['knowledge-atom-micro-lesson', userId, tree.id] }),
    ]);
  };

  const createSourceMutation = useMutation({
    mutationFn: (payload: CreateTreeSourcePayload) => createTreeSource(tree.id, payload),
    onSuccess: async res => {
      setActiveSourceId(res.source.id);
      setSourceTitle('');
      setSourceUrl('');
      setSourceContent('');
      setSourceOutline('');
      setSelectedFile(null);
      const alignMsg = res.alignment_result
        ? `并完成树对树对齐（命中 ${res.alignment_result.coverage.aligned_block_count}/${res.alignment_result.coverage.total_block_count} 个知识块）`
        : '，点击「一键树对树语义对齐」即可映射到各知识点';
      setMessage(`已解析主线资料《${res.source.title}》（共 ${res.source.node_count} 个目录切片）${alignMsg}。`);
      await invalidateAll();
    },
    onError: err => setError(errorMessage(err)),
  });

  const alignSourceMutation = useMutation({
    mutationFn: (sourceId: number) => alignTreeSource(tree.id, sourceId),
    onSuccess: async res => {
      setMessage(
        `树对树语义对齐完成：覆盖 ${res.coverage.aligned_block_count}/${res.coverage.total_block_count} 个知识块、${res.coverage.aligned_atom_count}/${res.coverage.total_atom_count} 个知识点（共 ${res.coverage.alignment_count} 条锚点）。`
      );
      await invalidateAll();
    },
    onError: err => setError(errorMessage(err)),
  });

  const deleteSourceMutation = useMutation({
    mutationFn: (sourceId: number) => deleteTreeSource(tree.id, sourceId),
    onSuccess: async () => {
      setMessage('已解绑该主线资料并清理其对齐锚点。');
      await invalidateAll();
    },
    onError: err => setError(errorMessage(err)),
  });

  const verifyAlignmentMutation = useMutation({
    mutationFn: ({ sourceId, alignmentId, isVerified }: { sourceId: number; alignmentId: number; isVerified: boolean }) =>
      updateSourceAlignment(tree.id, sourceId, alignmentId, isVerified),
    onSuccess: async () => { await invalidateAll(); },
    onError: err => setError(errorMessage(err)),
  });

  const removeAlignmentMutation = useMutation({
    mutationFn: ({ sourceId, alignmentId }: { sourceId: number; alignmentId: number }) =>
      deleteSourceAlignment(tree.id, sourceId, alignmentId),
    onSuccess: async () => { await invalidateAll(); },
    onError: err => setError(errorMessage(err)),
  });

  // Legacy mutations
  const mount = useMutation({
    mutationFn: (payload: TreePublicAssetImportPayload) => importTreePublicAsset(tree.id, payload),
    onSuccess: async (data, payload) => {
      setMessage(`已向本树挂载 ${data.mounted_count} 条资源。`);
      if (payload.url) { setUrl(''); setTitle(''); setOutline(''); }
      await invalidateAll();
    },
    onError: err => setError(errorMessage(err)),
  });

  const discoverMutation = useMutation({
    mutationFn: () => autoDiscoverTreePublicAssets(tree.id),
    onSuccess: async data => {
      setMessage(`已从全网智能发现并向本树挂载 ${data.mounted_count} 条资源。`);
      await invalidateAll();
    },
    onError: err => setError(errorMessage(err)),
  });

  const handleCreateSource = (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    setMessage('');
    const payload: CreateTreeSourcePayload = {
      source_kind: sourceKind,
      title: sourceTitle.trim() || undefined,
      is_primary: true,
      auto_align: autoAlignAfterImport,
    };
    if (sourceKind === 'pdf') {
      if (!selectedFile) {
        setError('请先选择一个 PDF 文件。');
        return;
      }
      payload.file = selectedFile;
    } else if (sourceKind === 'markdown' || sourceKind === 'text') {
      if (selectedFile) {
        payload.file = selectedFile;
      } else if (sourceContent.trim()) {
        payload.content = sourceContent;
      } else {
        setError('请粘贴讲义/考纲文本，或选择本地 .md / .txt 文件。');
        return;
      }
    } else if (sourceKind === 'bilibili_series' || sourceKind === 'web_repo') {
      if (!sourceUrl.trim()) {
        setError('请填写公开 HTTPS 链接。');
        return;
      }
      payload.url = sourceUrl.trim();
      if (sourceOutline.trim()) payload.outline_text = sourceOutline;
    } else if (sourceKind === 'course_album') {
      if (!selectedAlbumId) {
        setError('请选择一个站内课程专辑。');
        return;
      }
      payload.album_id = Number(selectedAlbumId);
    }
    createSourceMutation.mutate(payload);
  };

  const sourcesData = sourcesQuery.data;
  const sources: TreeSourceDocumentItem[] = sourcesData?.sources ?? [];
  const selectedSource = sources.find(s => s.id === activeSourceId) ?? sources[0] ?? null;
  const coverage = sourcesData?.coverage;
  const blockPct = coverage && coverage.total_block_count > 0
    ? Math.round((coverage.aligned_block_count / coverage.total_block_count) * 100)
    : 0;

  // Legacy data
  const data = assetsQuery.data;
  const isIntl = (data?.region_pref ?? tree.region_pref ?? 'cn') === 'intl';
  const trackLabels: Record<AssetTrack, string> = {
    spine: '🎬 主线配套课',
    spotlight: '🌟 单点神作',
    wiki: isIntl ? '📖 Wikipedia 词条' : '📖 专业开源 Wiki 词条',
  };
  const sourceLabels: Record<AssetSourceKind, string> = {
    course: '站内课程', library: '个人资料', web: '公开课 / 网页', bilibili: 'B站合集',
    github: '开源讲义仓库', wikipedia: isIntl ? 'Wikipedia' : 'OI-Wiki / 开源学科词条', youtube: isIntl ? 'YouTube / OCW' : '公开视频', marketplace: '共享市场',
  };
  const filters: { value: AssetFilter; label: string }[] = [
    { value: 'all', label: '全部' },
    { value: 'spine', label: '🎬 主线成套课' },
    { value: 'spotlight', label: '🌟 单点神作' },
    { value: 'wiki', label: trackLabels.wiki },
    { value: 'internal', label: '🏛️ 站内课程与共享市场' },
  ];
  const catalog = data?.catalog_assets.filter(asset => filter === 'all' || (
    filter === 'internal' ? ['course', 'library', 'marketplace'].includes(asset.source_kind) : asset.asset_track === filter
  ));
  const showInternal = filter === 'all' || filter === 'internal';
  const showWiki = filter === 'all' || filter === 'wiki';

  const busy = createSourceMutation.isPending || alignSourceMutation.isPending || deleteSourceMutation.isPending || mount.isPending || discoverMutation.isPending;

  const renderCatalog = (asset: PublicAssetCatalogItem) => (
    <article key={`catalog-${asset.id}`} className="kb-public-asset-card space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <a href={resolvePublicAssetLink(asset.url)} target="_blank" rel="noopener noreferrer" className="font-semibold underline underline-offset-4">{asset.title}</a>
        <span className="kb-badge">{sourceLabels[asset.source_kind]}</span>
        <span className={`kb-badge kb-track-${asset.asset_track}`}>{trackLabels[asset.asset_track]}</span>
      </div>
      <p className="text-sm text-muted-foreground">{asset.description}</p>
      <Button size="sm" disabled={busy} onClick={() => { setError(''); setMessage(''); mount.mutate({ public_asset_id: asset.id }); }}>
        一键对齐挂载到本树
      </Button>
    </article>
  );

  return (
    <Dialog open onOpenChange={open => { if (!open) onClose(); }}>
      <DialogContent className="kb-public-assets-dialog sm:max-w-[1040px] max-h-[90dvh] overflow-y-auto space-y-4">
        <DialogHeader>
          <DialogTitle>📚 主线资料与切片对齐</DialogTitle>
          <DialogDescription>
            {tree.subject} · Source-First 架构：导入权威教材、考纲、B站合集或站内专辑，执行 Tree-to-Tree 语义对齐，为每个知识点生成可溯源的多模态微课件。
          </DialogDescription>
        </DialogHeader>

        {/* Top Mode Tabs */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-3" role="tablist" aria-label="资料管理模式">
          <div className="flex flex-wrap gap-2">
            <Button
              role="tab"
              size="sm"
              aria-selected={mainTab === 'sources'}
              variant={mainTab === 'sources' ? 'default' : 'outline'}
              onClick={() => setMainTab('sources')}
            >
              📚 主线资料与树对树对齐（{sources.length}）
            </Button>
            <Button
              role="tab"
              size="sm"
              aria-selected={mainTab === 'legacy'}
              variant={mainTab === 'legacy' ? 'default' : 'outline'}
              onClick={() => setMainTab('legacy')}
            >
              🌐 公开资产池 &amp; 兜底参考
            </Button>
          </div>
          {coverage && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>主线覆盖率：</span>
              <strong className="text-foreground">{coverage.aligned_block_count}/{coverage.total_block_count} 块</strong>
              <span>（{coverage.aligned_atom_count}/{coverage.total_atom_count} 知识点）</span>
              <progress value={blockPct} max={100} className="w-20 h-2" />
              <span>{blockPct}%</span>
            </div>
          )}
        </div>

        {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50/70 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">{error}</p>}
        {message && <p role="status" className="kb-study-status is-complete">{message}</p>}

        {mainTab === 'sources' ? (
          <div className="space-y-5">
            {/* Step 1: Import Source */}
            <form onSubmit={handleCreateSource} className="rounded-xl border bg-muted/20 p-4 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="font-semibold text-sm">① 导入主线信源（建议每棵树绑定 1~3 份核心资料）</h3>
                <div className="flex flex-wrap gap-1.5">
                  {(['markdown', 'pdf', 'bilibili_series', 'course_album', 'web_repo', 'text'] as TreeSourceKind[]).map(kind => (
                    <Button
                      key={kind}
                      type="button"
                      size="sm"
                      variant={sourceKind === kind ? 'default' : 'outline'}
                      className="h-7 rounded-full text-xs"
                      onClick={() => { setSourceKind(kind); setSelectedFile(null); setError(''); }}
                    >
                      {sourceKindLabels[kind]}
                    </Button>
                  ))}
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <label className="block text-xs space-y-1">
                  <span>资料名称（可选，留空自动提取）</span>
                  <Input
                    value={sourceTitle}
                    maxLength={240}
                    placeholder="如：《基金从业协会教材》或 3Blue1Brown 线代合集"
                    onChange={e => setSourceTitle(e.target.value)}
                    disabled={busy}
                  />
                </label>

                {(sourceKind === 'bilibili_series' || sourceKind === 'web_repo') && (
                  <label className="block text-xs space-y-1">
                    <span>公开 HTTPS 链接</span>
                    <Input
                      type="url"
                      required
                      pattern="https://.*"
                      value={sourceUrl}
                      placeholder={sourceKind === 'bilibili_series' ? 'https://www.bilibili.com/video/BV…' : 'https://github.com/… 或 https://oi-wiki.org/…'}
                      onChange={e => setSourceUrl(e.target.value)}
                      disabled={busy}
                    />
                  </label>
                )}

                {sourceKind === 'course_album' && (
                  <label className="block text-xs space-y-1">
                    <span>选择站内课程专辑</span>
                    <select
                      className="kb-study-select w-full h-9"
                      value={selectedAlbumId}
                      onChange={e => setSelectedAlbumId(e.target.value)}
                      disabled={busy}
                    >
                      <option value="">请选择专辑…</option>
                      {(sourcesData?.albums ?? []).map(album => (
                        <option key={album.id} value={album.id}>{album.name}</option>
                      ))}
                    </select>
                  </label>
                )}

                {(sourceKind === 'pdf' || sourceKind === 'markdown' || sourceKind === 'text') && (
                  <label className="block text-xs space-y-1">
                    <span>上传本地文件（{sourceKind === 'pdf' ? '.pdf' : '.md / .txt，可选'}）</span>
                    <Input
                      type="file"
                      accept={sourceKind === 'pdf' ? '.pdf,application/pdf' : '.md,.markdown,.txt,text/plain,text/markdown'}
                      onChange={e => setSelectedFile(e.target.files?.[0] ?? null)}
                      disabled={busy}
                    />
                  </label>
                )}
              </div>

              {(sourceKind === 'markdown' || sourceKind === 'text') && !selectedFile && (
                <label className="block text-xs space-y-1">
                  <span>直接粘贴 Markdown 讲义 / 教材章节 / 考纲原文</span>
                  <Textarea
                    rows={5}
                    value={sourceContent}
                    onChange={e => setSourceContent(e.target.value)}
                    placeholder={'# 第1章 股权投资基金概述\n## 1.1 组织形式\n公司型、合伙型与契约型基金的税负与治理差异…'}
                    disabled={busy}
                  />
                </label>
              )}

              {(sourceKind === 'bilibili_series' || sourceKind === 'web_repo') && (
                <details className="text-xs">
                  <summary className="cursor-pointer font-medium text-muted-foreground">可选：粘贴自定义分 P / 章节目录（每行一集，解析失败时也可直接建树）</summary>
                  <Textarea
                    className="mt-2"
                    rows={4}
                    value={sourceOutline}
                    onChange={e => setSourceOutline(e.target.value)}
                    placeholder={'P1 基金组织形式概览\nP2 募集流程与合格投资者\nP3 估值方法与退出机制'}
                    disabled={busy}
                  />
                </details>
              )}

              <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
                <label className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={autoAlignAfterImport}
                    onChange={e => setAutoAlignAfterImport(e.target.checked)}
                    disabled={busy}
                  />
                  导入解析完成后，自动执行一次 DeepSeek 树对树语义对齐
                </label>
                <Button type="submit" size="sm" disabled={busy}>
                  {createSourceMutation.isPending ? '正在解析并建树…' : '解析并绑定为主线资料'}
                </Button>
              </div>
            </form>

            {/* Step 2 & 3: Bound Sources List, TOC Tree Preview & Tree-to-Tree Alignment */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
              <div className="lg:col-span-4 space-y-2">
                <h3 className="font-semibold text-sm">② 已绑定主线资料（{sources.length}）</h3>
                {sourcesQuery.isLoading && <p className="text-xs text-muted-foreground">正在加载主线资料…</p>}
                {!sourcesQuery.isLoading && sources.length === 0 && (
                  <p className="rounded-xl border border-dashed p-4 text-xs text-muted-foreground">
                    尚未绑定主线资料。导入 1 份核心教材/大纲/B站合集后，即可一键对齐整棵知识树，让微课件全部可溯源。
                  </p>
                )}
                {sources.map(src => {
                  const active = selectedSource?.id === src.id;
                  return (
                    <article
                      key={src.id}
                      className={`rounded-xl border p-3 space-y-2 cursor-pointer transition ${active ? 'border-primary bg-primary/5' : 'bg-card hover:bg-muted/30'}`}
                      onClick={() => setActiveSourceId(src.id)}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="font-semibold text-sm truncate">{src.title}</p>
                          <p className="text-xs text-muted-foreground">
                            {sourceKindLabels[src.source_kind]} · {src.node_count} 切片 · 已对齐 {src.aligned_block_count} 块 / {src.aligned_atom_count} 点
                          </p>
                        </div>
                        {src.is_primary && <span className="kb-badge shrink-0">主线</span>}
                      </div>
                      <div className="flex flex-wrap gap-1.5" onClick={e => e.stopPropagation()}>
                        <Button
                          size="sm"
                          className="h-7 text-xs"
                          disabled={busy}
                          onClick={() => { setError(''); setMessage(''); alignSourceMutation.mutate(src.id); }}
                        >
                          {alignSourceMutation.isPending && alignSourceMutation.variables === src.id ? '对齐中…' : '✨ 一键树对树对齐'}
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 text-xs text-destructive"
                          disabled={busy}
                          onClick={() => { setError(''); setMessage(''); deleteSourceMutation.mutate(src.id); }}
                        >
                          解绑
                        </Button>
                      </div>
                    </article>
                  );
                })}
              </div>

              <div className="lg:col-span-8 space-y-4">
                {selectedSource ? (
                  <>
                    <section className="rounded-xl border bg-card p-4 space-y-2">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <h3 className="font-semibold text-sm">🌲 目录树预览 · {selectedSource.title}</h3>
                        <span className="text-xs text-muted-foreground">共 {selectedSource.node_count} 个可溯源切片</span>
                      </div>
                      <div className="max-h-52 overflow-y-auto pr-1">
                        <TocTreeNodes nodes={selectedSource.toc_tree} />
                      </div>
                    </section>

                    <section className="rounded-xl border bg-card p-4 space-y-2.5">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <h3 className="font-semibold text-sm">
                          ③ 对齐结果与核对（{selectedSource.alignments.length} 条锚点 · 覆盖 {selectedSource.aligned_block_count} 块）
                        </h3>
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7 text-xs"
                          disabled={busy}
                          onClick={() => { setError(''); setMessage(''); alignSourceMutation.mutate(selectedSource.id); }}
                        >
                          ↻ 重新执行树对树对齐
                        </Button>
                      </div>
                      {selectedSource.alignments.length === 0 ? (
                        <p className="text-xs text-muted-foreground">尚未生成对齐映射，点击上方「✨ 一键树对树对齐」即可批量映射知识点与章节页码。</p>
                      ) : (
                        <div className="max-h-72 overflow-y-auto space-y-2 pr-1">
                          {selectedSource.alignments.map(item => (
                            <article key={item.id} className="rounded-lg border bg-muted/20 p-2.5 text-xs space-y-1">
                              <div className="flex flex-wrap items-center justify-between gap-2">
                                <div className="flex flex-wrap items-center gap-1.5">
                                  <strong>{item.atom_name || item.block_title}</strong>
                                  <span className="text-muted-foreground">↔</span>
                                  <span className="kb-badge kb-resource-locator">{item.locator || item.section_title}</span>
                                  <span className="kb-badge">{roleLabels[item.alignment_role] ?? item.alignment_role}</span>
                                  <span className="text-muted-foreground">{Math.round(item.confidence * 100)}%</span>
                                </div>
                                <div className="flex items-center gap-1.5">
                                  <Button
                                    size="sm"
                                    variant={item.is_verified ? 'default' : 'outline'}
                                    className="h-6 px-2 text-[11px]"
                                    onClick={() => verifyAlignmentMutation.mutate({ sourceId: selectedSource.id, alignmentId: item.id, isVerified: !item.is_verified })}
                                  >
                                    {item.is_verified ? '✓ 已核对' : '核对确认'}
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    className="h-6 px-2 text-[11px] text-destructive"
                                    onClick={() => removeAlignmentMutation.mutate({ sourceId: selectedSource.id, alignmentId: item.id })}
                                  >
                                    解绑
                                  </Button>
                                </div>
                              </div>
                              {item.match_reason && <p className="text-muted-foreground">理由：{item.match_reason}</p>}
                              {item.excerpt_quote && <p className="text-muted-foreground line-clamp-2">{item.excerpt_quote}</p>}
                            </article>
                          ))}
                        </div>
                      )}
                    </section>
                  </>
                ) : (
                  <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
                    在上方导入一份主线教材 / 讲义 / B站合集后，这里将展示目录树预览与树对树对齐结果。
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : (
          /* Secondary Tab: Legacy Public Asset Pool & Fallback Discovery */
          <div className="space-y-4">
            <div className="kb-public-assets-summary" aria-label="整树三轨挂载概览">
              {data ? (
                <>
                  <p>🎬 主线配套课 ({data.mounted_summary.spine_count ?? 0}) · 🌟 单点神作 ({data.mounted_summary.spotlight_count ?? 0}) · {trackLabels.wiki} ({data.mounted_summary.wiki_count ?? 0})</p>
                  <p className="text-xs text-muted-foreground">{isIntl ? '国际信源模式' : '国内信源模式'}（兜底外链模式，推荐优先使用「主线资料与树对树对齐」）</p>
                </>
              ) : (
                <p className="text-sm">{assetsQuery.isLoading ? '正在读取三轨挂载概览…' : '三轨挂载概览读取失败。'}</p>
              )}
              <Button size="sm" variant="outline" disabled={busy} onClick={() => { setError(''); setMessage(''); discoverMutation.mutate(); }}>
                {discoverMutation.isPending ? '正在全网搜索并匹配…' : '🌐 整树兜底全网搜索'}
              </Button>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant={legacySubTab === 'catalog' ? 'default' : 'outline'} onClick={() => setLegacySubTab('catalog')}>精选公开资产池 &amp; 站内共享市场</Button>
              <Button size="sm" variant={legacySubTab === 'import' ? 'default' : 'outline'} onClick={() => setLegacySubTab('import')}>粘贴链接拆集挂载</Button>
            </div>
            {legacySubTab === 'catalog' ? (
              <section className="space-y-3">
                <div className="flex flex-wrap gap-2">
                  {filters.map(item => (
                    <Button key={item.value} size="sm" variant={filter === item.value ? 'default' : 'outline'} onClick={() => setFilter(item.value)}>{item.label}</Button>
                  ))}
                </div>
                <div className="kb-public-assets-grid">
                  {catalog?.map(renderCatalog)}
                  {showWiki && data?.wiki_candidates.map(candidate => (
                    <article key={`wiki-${candidate.url}`} className="kb-public-asset-card space-y-2">
                      <a href={resolvePublicAssetLink(candidate.url, candidate.locator)} target="_blank" rel="noopener noreferrer" className="font-semibold underline">{candidate.title}</a>
                      <p className="text-xs text-muted-foreground">{candidate.summary}</p>
                      <Button size="sm" disabled={busy} onClick={() => { setError(''); setMessage(''); mount.mutate({ url: resolvePublicAssetLink(candidate.url, candidate.locator), title: candidate.title, asset_track: 'wiki', pedagogical_role: candidate.pedagogical_role }); }}>一键对齐挂载</Button>
                    </article>
                  ))}
                  {showInternal && data?.albums.map(album => (
                    <article key={`album-${album.id}`} className="kb-public-asset-card space-y-2">
                      <strong className="text-sm">{album.name}</strong>
                      <p className="text-xs text-muted-foreground">{album.description}</p>
                      <Button size="sm" disabled={busy} onClick={() => { setError(''); setMessage(''); mount.mutate({ album_id: album.id }); }}>一键对齐挂载</Button>
                    </article>
                  ))}
                </div>
              </section>
            ) : (
              <form className="space-y-3" onSubmit={e => {
                e.preventDefault();
                setError('');
                setMessage('');
                mount.mutate({
                  url: url.trim(),
                  ...(title.trim() ? { title: title.trim() } : {}),
                  ...(track ? { asset_track: track } : {}),
                  ...(role ? { pedagogical_role: role } : {}),
                  ...(outline.trim() ? { outline_text: outline.trim() } : {}),
                });
              }}>
                <Input type="url" required pattern="https://.*" value={url} placeholder="https://www.bilibili.com/video/BV…" onChange={e => setUrl(e.target.value)} />
                <Input value={title} placeholder="资源标题（可选）" onChange={e => setTitle(e.target.value)} />
                <div className="flex flex-wrap gap-3 text-sm">
                  <select className="kb-study-select" value={track} onChange={e => setTrack(e.target.value as AssetTrack | '')}>
                    <option value="">自动识别轨道</option>
                    <option value="spine">主线成套课</option>
                    <option value="spotlight">单点神作</option>
                    <option value="wiki">{trackLabels.wiki}</option>
                  </select>
                  <select className="kb-study-select" value={role} onChange={e => setRole(e.target.value as PedagogicalRole)}>
                    <option value="">自动识别角色</option>
                    {Object.entries(roleLabels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </div>
                <Textarea rows={4} value={outline} placeholder="可选：自定义分 P 目录（每行一集）" onChange={e => setOutline(e.target.value)} />
                <Button type="submit" disabled={busy || !url.trim()}>{mount.isPending ? '挂载中…' : '解析并挂载到知识树'}</Button>
              </form>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
