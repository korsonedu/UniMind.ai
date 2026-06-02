import React, { useState, useEffect, useMemo } from 'react';
import { ChevronRight, ChevronDown, Search, X } from 'lucide-react';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';
import type { KPNode, TreeNodeData } from './types';
import { LEVEL_ORDER, LEVEL_COLORS } from './types';

const MASTERY_DOT_COLORS: Record<string, string> = {
  mastered: '#34C759',
  stable: '#0071E3',
  learning: '#FF9500',
  weak: '#FF3B30',
  unknown: '#AEAEB2',
};

export const KnowledgeTreePanel: React.FC<{
  nodes: KPNode[];
  selectedId: number | null;
  onSelect: (node: KPNode) => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  masteryData?: Record<string, string>;
}> = ({ nodes, selectedId, onSelect, searchQuery, onSearchChange, masteryData = {} }) => {
  const { t } = useTranslation('knowledgeMap');
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  const tree = useMemo(() => {
    const nodeMap = new Map<number, TreeNodeData>();
    const roots: TreeNodeData[] = [];

    for (const n of nodes) {
      nodeMap.set(n.id, { ...n, children: [] });
    }
    for (const n of nodes) {
      const tn = nodeMap.get(n.id)!;
      if (n.parent && nodeMap.has(n.parent)) {
        nodeMap.get(n.parent)!.children.push(tn);
      } else {
        roots.push(tn);
      }
    }
    const sortTree = (list: TreeNodeData[]) => {
      list.sort((a, b) => (LEVEL_ORDER[a.level ?? ''] ?? 99) - (LEVEL_ORDER[b.level ?? ''] ?? 99) || (a.order ?? 0) - (b.order ?? 0) || a.name.localeCompare(b.name));
      list.forEach(t => sortTree(t.children));
    };
    sortTree(roots);
    return roots;
  }, [nodes]);

  // Auto-expand to show selected node
  useEffect(() => {
    if (!selectedId) return;
    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    if (!nodeMap.has(selectedId)) return;
    const path: number[] = [];
    let cur: KPNode | undefined = nodeMap.get(selectedId);
    while (cur) {
      path.push(cur.id);
      cur = cur.parent ? nodeMap.get(cur.parent) : undefined;
    }
    setExpandedIds(prev => {
      const next = new Set(prev);
      path.forEach(id => next.add(id));
      return next;
    });
  }, [selectedId, nodes]);

  const toggleExpand = (id: number) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const filteredTree = useMemo(() => {
    if (!searchQuery.trim()) return tree;
    const q = searchQuery.toLowerCase();
    const matchSet = new Set<number>();
    for (const n of nodes) {
      if (n.name.toLowerCase().includes(q)) matchSet.add(n.id);
    }
    const keepSet = new Set<number>(matchSet);
    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    for (const id of matchSet) {
      let cur = nodeMap.get(id);
      while (cur?.parent) {
        keepSet.add(cur.parent);
        cur = nodeMap.get(cur.parent);
      }
    }
    const filterNodes = (list: TreeNodeData[]): TreeNodeData[] =>
      list.filter(t => keepSet.has(t.id)).map(t => ({ ...t, children: filterNodes(t.children) }));
    return filterNodes(tree);
  }, [tree, searchQuery, nodes]);

  const renderNode = (tn: TreeNodeData, depth: number) => {
    const hasChildren = tn.children.length > 0;
    const isExpanded = expandedIds.has(tn.id);
    const isSelected = tn.id === selectedId;
    const isKp = tn.level === 'kp';

    return (
      <div key={tn.id} style={{ contentVisibility: 'auto', containIntrinsicSize: 'auto 36px' }}>
        <button
          onClick={() => {
            if (hasChildren) toggleExpand(tn.id);
            if (isKp) onSelect(tn);
          }}
          className={cn(
            'w-full flex items-center gap-1.5 py-1.5 pr-2 rounded-lg text-left transition-colors group',
            isSelected && 'bg-amber-50 border border-amber-200',
            !isSelected && 'hover:bg-muted/50',
          )}
          style={{ paddingLeft: `${depth * 16 + 8}px` }}
        >
          {hasChildren ? (
            isExpanded ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
            : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
          ) : (
            <span className="w-3.5 shrink-0" />
          )}

          {isKp && (
            <span
              className="h-2.5 w-2.5 rounded-full shrink-0 border border-white/50 shadow-sm"
              style={{ backgroundColor: MASTERY_DOT_COLORS[masteryData[String(tn.id)]] || MASTERY_DOT_COLORS.unknown }}
            />
          )}

          <Badge
            variant="outline"
            className={cn(
              'text-[9px] py-0 h-4 px-1.5 font-bold uppercase shrink-0',
              LEVEL_COLORS[tn.level] || 'bg-muted',
            )}
          >
            {t(`levels.${tn.level}` as any) || tn.level}
          </Badge>

          <span
            className={cn(
              'text-xs font-bold truncate flex-1',
              isSelected && 'text-amber-700',
              isKp && 'cursor-pointer',
            )}
          >
            {tn.name}
          </span>

          {tn.questions_count !== undefined && tn.questions_count > 0 && (
            <Badge variant="secondary" className="text-[9px] rounded-full px-1.5 py-0 h-4 bg-indigo-50 text-indigo-500 border-none font-bold shrink-0">
              {tn.questions_count}
            </Badge>
          )}
        </button>

        {hasChildren && isExpanded && (
          <div>{tn.children.map(child => renderNode(child, depth + 1))}</div>
        )}
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full bg-card rounded-2xl border border-border/50 overflow-hidden">
      <div className="p-3 border-b border-border/30">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            placeholder={t('treePanel.searchPlaceholder')}
            value={searchQuery}
            onChange={e => onSearchChange(e.target.value)}
            className="h-9 pl-9 pr-8 rounded-xl bg-muted/50 border-none text-xs font-medium"
          />
          {searchQuery && (
            <button
              onClick={() => onSearchChange('')}
              className="absolute right-2 top-1/2 -translate-y-1/2"
            >
              <X className="h-3 w-3 text-muted-foreground" />
            </button>
          )}
        </div>
      </div>
      {/* Mastery legend */}
      <div className="px-3 py-2 border-t border-border/30 flex items-center gap-3 flex-wrap">
        {[
          { level: 'mastered', label: t('treePanel.legendMastered'), color: MASTERY_DOT_COLORS.mastered },
          { level: 'stable', label: t('treePanel.legendStable'), color: MASTERY_DOT_COLORS.stable },
          { level: 'learning', label: t('treePanel.legendLearning'), color: MASTERY_DOT_COLORS.learning },
          { level: 'weak', label: t('treePanel.legendWeak'), color: MASTERY_DOT_COLORS.weak },
        ].map(item => (
          <div key={item.level} className="flex items-center gap-1.5">
            <span
              className="h-2.5 w-2.5 rounded-full shrink-0 border border-white/50 shadow-sm"
              style={{ backgroundColor: item.color }}
            />
            <span className="text-[10px] font-bold text-muted-foreground">{item.label}</span>
          </div>
        ))}
      </div>
      <ScrollArea className="flex-1 p-2" type="always">
        <div className="space-y-0.5 min-w-max">
          {filteredTree.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-8">{t('treePanel.noMatch')}</p>
          ) : (
            filteredTree.map(root => renderNode(root, 0))
          )}
        </div>
        <ScrollBar orientation="horizontal" />
      </ScrollArea>
    </div>
  );
};
