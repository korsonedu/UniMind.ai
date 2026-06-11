import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { useIsMobile } from '@/lib/useIsMobile';
import { useNavigate } from 'react-router-dom';
import { PageWrapper } from '@/components/PageWrapper';
import { GitMerge, MagnifyingGlass, List } from '@phosphor-icons/react';
import api from '@/lib/api';
import { cn } from '@/lib/utils';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useTranslation } from 'react-i18next';

// Sub-modules
import type { KPNode } from './knowledge-map/types';
import { KnowledgeGraph } from './knowledge-map/GraphCanvas';
import { KnowledgeTreePanel } from './knowledge-map/TreePanel';
import { NodeDetailPanel } from './knowledge-map/NodeDetailPanel';
import { KnowledgeTrainingDialog } from './knowledge-map/TrainingDialog';

export const KnowledgeMap: React.FC = () => {
  const navigate = useNavigate();
  const { t } = useTranslation('knowledgeMap');
  const [allNodes, setAllNodes] = useState<KPNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedNode, setSelectedNode] = useState<KPNode | null>(null);
  const [nodeDetails, setNodeDetails] = useState<{ courses: any[]; articles: any[]; questions: any[] }>({
    courses: [],
    articles: [],
    questions: [],
  });
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [treeSearch, setTreeSearch] = useState('');
  const isMobile = useIsMobile();
  const [selectedQuestion, setSelectedQuestion] = useState<any>(null);
  const [viewMode, setViewMode] = useState<'graph' | 'list'>('graph');
  const [graphRootId, setGraphRootId] = useState<string>('all');
  const [masteryData, setMasteryData] = useState<Record<string, string>>({});
  const [mobileTreeOpen, setMobileTreeOpen] = useState(false);
  const [mobileVisibleCount, setMobileVisibleCount] = useState(40);
  const mobileSentinelRef = useRef<HTMLDivElement>(null);

  // Reset visible count when search changes or toggling to tree
  useEffect(() => {
    setMobileVisibleCount(40);
  }, [treeSearch, mobileTreeOpen]);

  // IntersectionObserver: load more grid items as user scrolls
  useEffect(() => {
    if (!isMobile || mobileTreeOpen) return;
    const sentinel = mobileSentinelRef.current;
    if (!sentinel) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setMobileVisibleCount(prev => Math.min(prev + 40, allNodes.length));
        }
      },
      { rootMargin: '200px' },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [isMobile, mobileTreeOpen, allNodes.length]);

  useEffect(() => {
    fetchMap();
    fetchMastery();
  }, []);

  const fetchMastery = async () => {
    try {
      const { data } = await api.get('/users/me/knowledge-mastery/');
      setMasteryData(data || {});
    } catch (e) { console.debug('[KnowledgeMap] mastery fetch failed:', e); }
  };

  const fetchMap = async () => {
    try {
      const res = await api.get('/quizzes/knowledge-points/');
      let rawData = res.data;
      const flatNodes: KPNode[] = [];
      const flatten = (items: any[]) => {
        for (const item of items) {
          flatNodes.push({
            id: item.id,
            name: item.name,
            description: item.description,
            parent: item.parent,
            level: item.level,
            order: item.order,
            questions_count: item.questions_count,
          });
          if (item.children && item.children.length > 0) flatten(item.children);
        }
      };
      if (rawData.length > 0 && rawData[0].children !== undefined) flatten(rawData);
      else flatNodes.push(...rawData);
      flatNodes.sort((a, b) => (b.questions_count || 0) - (a.questions_count || 0) || (a.order ?? 0) - (b.order ?? 0) || a.name.localeCompare(b.name));
      setAllNodes(flatNodes);
    } catch (e) {
    } finally {
      setLoading(false);
    }
  };

  /** Find the ancestor at `targetLevel` for a given node. */
  const findAncestorAtLevel = useCallback(
    (node: KPNode, targetLevel: string): KPNode | null => {
      const nodeMap = new Map(allNodes.map(n => [n.id, n]));
      let cur: KPNode | undefined = node;
      while (cur) {
        if (cur.level === targetLevel) return cur;
        cur = cur.parent ? nodeMap.get(cur.parent) : undefined;
      }
      return null;
    },
    [allNodes],
  );

  const handleNodeSelect = useCallback(async (node: KPNode) => {
    if (isMobile) {
      navigate(`/knowledge-map/node/${node.id}`);
      return;
    }

    // Auto-focus graph on the section (小节) containing this node
    if (node.level === 'kp') {
      const sec = findAncestorAtLevel(node, 'sec');
      if (sec) setGraphRootId(sec.id.toString());
      else {
        const ch = findAncestorAtLevel(node, 'ch');
        if (ch) setGraphRootId(ch.id.toString());
        else {
          const sub = findAncestorAtLevel(node, 'sub');
          if (sub) setGraphRootId(sub.id.toString());
        }
      }
    } else if (node.level === 'sec') {
      setGraphRootId(node.id.toString());
    } else if (node.level === 'ch') {
      setGraphRootId(node.id.toString());
    } else if (node.level === 'sub') {
      setGraphRootId(node.id.toString());
    }

    setSelectedNode(node);
    setDetailsLoading(true);
    try {
      const [cRes, aRes, qRes] = await Promise.all([
        api.get('/courses/', { params: { kp: node.id } }),
        api.get('/articles/', { params: { kp: node.id } }),
        api.get('/quizzes/questions/', { params: { kp: node.id } }),
      ]);
      setNodeDetails({
        courses: cRes.data.items ?? cRes.data ?? [],
        articles: aRes.data.articles || aRes.data || [],
        questions: qRes.data || [],
      });
    } catch (e) {
    } finally {
      setDetailsLoading(false);
    }
  }, [isMobile, navigate, findAncestorAtLevel]);

  const handleClearSelection = useCallback(() => {
    setSelectedNode(null);
    setNodeDetails({ courses: [], articles: [], questions: [] });
  }, []);

  // Branch filter: subjects for the toolbar dropdown
  const rootOptions = useMemo(() => allNodes.filter(n => n.level === 'sub'), [allNodes]);

  // Filter graph nodes by selected branch
  const displayNodes = useMemo(() => {
    if (graphRootId === 'all') return allNodes;
    const rootId = parseInt(graphRootId);
    const validIds = new Set<number>([rootId]);
    let added = true;
    while (added) {
      added = false;
      for (const node of allNodes) {
        if (node.parent && validIds.has(node.parent) && !validIds.has(node.id)) {
          validIds.add(node.id);
          added = true;
        }
      }
    }
    return allNodes.filter(n => validIds.has(n.id));
  }, [allNodes, graphRootId]);

  // List-view nodes (kps only, searchable)
  const listNodes = useMemo(
    () => displayNodes.filter(n => n.level === 'kp' && n.name.toLowerCase().includes(treeSearch.toLowerCase())),
    [displayNodes, treeSearch],
  );

  if (loading) {
    return (
      <PageWrapper title={t('pageTitle')} subtitle={t('pageLoadingSubtitle')}>
        <div className="text-center text-[10px] font-medium text-muted-foreground/30 py-32">Mapping...</div>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper title={t('pageTitle')} subtitle={t('pageSubtitle')}>
      <div className="w-full text-left animate-in fade-in duration-700">
        {isMobile ? (
          /* ── Mobile: toggle between tree panel and grid list ── */
          <div className="space-y-3">
            {/* Toggle + Search */}
            <div className="flex items-center gap-2">
              <Button
                variant={mobileTreeOpen ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => setMobileTreeOpen(!mobileTreeOpen)}
                className="rounded-xl h-9 text-xs font-bold shrink-0"
              >
                {mobileTreeOpen ? <List className="h-3.5 w-3.5 mr-1" /> : <GitMerge className="h-3.5 w-3.5 mr-1" />}
                {mobileTreeOpen ? '网格' : '知识树'}
              </Button>
              {!mobileTreeOpen && (
                <div className="relative flex-1">
                  <MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder={t('mobile.searchPlaceholder')}
                    value={treeSearch}
                    onChange={e => setTreeSearch(e.target.value)}
                    className="w-full rounded-2xl bg-card border-border shadow-sm h-11 pl-10 pr-4 font-bold"
                  />
                </div>
              )}
            </div>

            {mobileTreeOpen ? (
              <div className="h-[calc(100dvh-12rem)] overflow-hidden rounded-2xl">
                <KnowledgeTreePanel
                  nodes={allNodes}
                  selectedId={selectedNode?.id ?? null}
                  onSelect={handleNodeSelect}
                  searchQuery={treeSearch}
                  onSearchChange={setTreeSearch}
                  masteryData={masteryData}
                />
              </div>
            ) : (
              <div className="h-[calc(100dvh-12rem)] overflow-y-auto overscroll-contain rounded-2xl bg-muted/50 p-2">
                <div className="grid grid-cols-2 gap-2 content-start">
                  {(() => {
                    const filtered = allNodes.filter(n => n.name.toLowerCase().includes(treeSearch.toLowerCase()));
                    const visible = filtered.slice(0, mobileVisibleCount);
                    return (
                      <>
                        {visible.map(node => (
                          <button
                            key={node.id}
                            onClick={() => handleNodeSelect(node)}
                            className="flex items-center justify-between bg-card border border-border/50 hover:border-indigo-500/30 hover:shadow-md px-2.5 py-2 rounded-xl transition-all active:scale-[0.99] text-left min-h-[58px]"
                          >
                            <span className="text-[12px] font-bold truncate pr-2 leading-snug">{node.name}</span>
                          </button>
                        ))}
                        {visible.length < filtered.length && (
                          <div ref={mobileSentinelRef} className="col-span-2 h-4" />
                        )}
                      </>
                    );
                  })()}
                </div>
              </div>
            )}
          </div>
        ) : (
          /* ── Desktop: three-panel layout ── */
          <div className="flex gap-4" style={{ height: 'calc(100vh - 7rem)' }}>
            {/* ── Left: Tree Panel ── */}
            <div className="w-[300px] shrink-0 self-stretch">
              <KnowledgeTreePanel
                nodes={allNodes}
                selectedId={selectedNode?.id ?? null}
                onSelect={handleNodeSelect}
                searchQuery={treeSearch}
                onSearchChange={setTreeSearch}
                masteryData={masteryData}
              />
            </div>

            {/* ── Center: Graph / List ── */}
            <div className="flex-1 min-w-0 flex flex-col gap-3 self-stretch">
              {/* Toolbar */}
              <div className="flex items-center gap-3 shrink-0">
                <Select value={graphRootId} onValueChange={setGraphRootId}>
                  <SelectTrigger className="w-[200px] h-10 bg-card rounded-xl font-bold border-border shadow-sm text-xs">
                    <GitMerge className="w-3.5 h-3.5 mr-2 text-indigo-500" />
                    <SelectValue placeholder={t('toolbar.allBranches')} />
                  </SelectTrigger>
                  <SelectContent className="rounded-xl">
                    <SelectItem value="all" className="font-bold text-xs">{t('toolbar.allBranches')}</SelectItem>
                    {rootOptions.map(opt => (
                      <SelectItem key={opt.id} value={opt.id.toString()} className="text-xs">
                        {opt.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                {viewMode === 'list' && (
                  <Input
                    placeholder={t('toolbar.searchKp')}
                    value={treeSearch}
                    onChange={e => setTreeSearch(e.target.value)}
                    className="flex-1 rounded-xl bg-card border-border shadow-sm h-10 px-4 font-bold text-xs"
                  />
                )}

                <div className="flex bg-muted/30 p-1 rounded-xl border border-border/50 ml-auto shrink-0">
                  <Button
                    variant={viewMode === 'graph' ? 'secondary' : 'ghost'}
                    onClick={() => setViewMode('graph')}
                    className="rounded-lg h-8 text-xs font-bold px-4"
                  >
                    <GitMerge className="w-3.5 h-3.5 mr-1.5" /> {t('toolbar.graphView')}
                  </Button>
                  <Button
                    variant={viewMode === 'list' ? 'secondary' : 'ghost'}
                    onClick={() => setViewMode('list')}
                    className="rounded-lg h-8 text-xs font-bold px-3"
                  >
                    <List className="w-3.5 h-3.5 mr-1.5" /> {t('toolbar.listView')}
                  </Button>
                </div>
              </div>

              {/* Content */}
              <div className="flex-1 min-h-0">
                {viewMode === 'graph' ? (
                  <KnowledgeGraph
                    nodes={displayNodes}
                    selectedId={selectedNode?.id ?? null}
                    onNodeClick={handleNodeSelect}
                    masteryData={masteryData}
                  />
                ) : (
                  <div className="h-full bg-muted/30 rounded-2xl border border-border/50 p-4">
                    <ScrollArea className="h-full">
                      <div className="flex flex-wrap gap-2 content-start">
                        {listNodes.map(node => (
                          <button
                            key={node.id}
                            onClick={() => handleNodeSelect(node)}
                            className={cn(
                              'flex items-center gap-2 bg-card border hover:shadow-md px-3 py-2 rounded-xl transition-all active:scale-95 text-left',
                              selectedNode?.id === node.id
                                ? 'border-amber-300 bg-amber-50'
                                : 'border-border/50 hover:border-indigo-500/30',
                            )}
                          >
                            <span className="text-xs font-bold">{node.name}</span>
                            {node.questions_count !== undefined && node.questions_count > 0 && (
                              <Badge variant="secondary" className="text-[9px] rounded-full px-1.5 py-0 h-4 bg-indigo-50 text-indigo-500 border-none font-bold">
                                {node.questions_count}
                              </Badge>
                            )}
                          </button>
                        ))}
                        {listNodes.length === 0 && (
                          <div className="w-full text-center text-xs font-bold text-muted-foreground py-20">
                            {t('toolbar.noMatch')}
                          </div>
                        )}
                      </div>
                    </ScrollArea>
                  </div>
                )}
              </div>
            </div>

            {/* ── Right: Detail Panel ── */}
            <div className="w-[320px] shrink-0 self-stretch">
              <NodeDetailPanel
                node={selectedNode}
                details={nodeDetails}
                loading={detailsLoading}
                onQuestionClick={setSelectedQuestion}
                onClear={handleClearSelection}
                masteryData={masteryData}
              />
            </div>
          </div>
        )}
      </div>

      {/* Training Dialog */}
      <KnowledgeTrainingDialog
        question={selectedQuestion}
        onClose={() => setSelectedQuestion(null)}
      />
    </PageWrapper>
  );
};
