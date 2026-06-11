import React, { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { X, Check, EyeSlash, CaretRight } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';
import api from '@/lib/api';
import type { KEdge, EdgeType } from './types';
import { EDGE_COLORS, EDGE_LABELS } from './types';

interface Props {
  subject: string;
  onApprove: () => void;
  onClose: () => void;
}

export const ReviewSidebar: React.FC<Props> = ({ subject, onApprove, onClose }) => {
  const [items, setItems] = useState<KEdge[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const res = await api.get('/quizzes/knowledge-edges/review/', { params: { subject } });
      setItems(res.data || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [subject]);

  useEffect(() => { load(); }, [load]);

  const handleAction = async (edgeId: number, action: 'approve' | 'reject') => {
    try {
      await api.post('/quizzes/knowledge-edges/review/action/', { edge_id: edgeId, action });
      setItems(prev => prev.filter(i => i.id !== edgeId));
      onApprove();
    } catch (err) {
      console.error(err);
    }
  };

  const handleBatchApprove = async () => {
    for (const item of items) {
      try {
        await api.post('/quizzes/knowledge-edges/review/action/', {
          edge_id: item.id, action: 'approve',
        });
      } catch (err) {
        console.error(`Failed to approve ${item.id}:`, err);
      }
    }
    setItems([]);
    onApprove();
  };

  // 按置信度排序（高→低）
  const sorted = [...items].sort((a, b) => b.weight - a.weight);

  const getConfidenceLevel = (w: number) => {
    if (w >= 0.75) return { label: '高', cls: 'bg-green-50 text-green-700 border-green-200' };
    if (w >= 0.5) return { label: '中', cls: 'bg-amber-50 text-amber-700 border-amber-200' };
    return { label: '低', cls: 'bg-gray-50 text-gray-500 border-gray-200' };
  };

  return (
    <div className="w-80 border-l bg-white flex flex-col shrink-0">
      {/* 头部 */}
      <div className="flex items-center justify-between px-4 py-3 border-b bg-gray-50/50">
        <span className="font-semibold text-sm">
          待审核
          {items.length > 0 && (
            <span className="ml-2 px-1.5 py-0.5 rounded-full bg-indigo-100 text-indigo-700 text-xs font-bold">
              {items.length}
            </span>
          )}
        </span>
        <div className="flex items-center gap-1">
          {items.length > 0 && (
            <Button variant="outline" size="sm" className="h-7 text-xs" onClick={handleBatchApprove}>
              <Check className="w-3 h-3 mr-1" />全部确认
            </Button>
          )}
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose}>
            <X className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* 内容 */}
      <ScrollArea className="flex-1">
        {loading ? (
          <div className="p-4 text-sm text-gray-400 animate-pulse text-center">加载中...</div>
        ) : sorted.length === 0 ? (
          <div className="p-8 text-center">
            <div className="text-3xl mb-2">🎉</div>
            <div className="text-sm text-gray-500">没有待审核的边</div>
            <div className="text-xs text-gray-300 mt-1">运行 LLM 分析来生成建议</div>
          </div>
        ) : (
          <div className="divide-y">
            {sorted.map(edge => {
              const confidence = getConfidenceLevel(edge.weight);
              return (
                <div key={edge.id} className={cn('p-3', confidence.cls.split(' ')[0])}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 mb-1">
                        <Badge
                          variant="secondary"
                          className="text-[10px] px-1.5 py-0 font-medium"
                          style={{
                            borderColor: EDGE_COLORS[edge.edge_type as EdgeType],
                            color: EDGE_COLORS[edge.edge_type as EdgeType],
                          }}
                        >
                          {EDGE_LABELS[edge.edge_type as EdgeType]}
                        </Badge>
                        <Badge variant="outline" className={cn('text-[10px] px-1.5 py-0', confidence.cls)}>
                          {confidence.label}置信 · {edge.weight.toFixed(2)}
                        </Badge>
                      </div>
                      <div className="text-sm font-medium leading-snug">
                        <span className="text-indigo-600">{edge.source_name}</span>
                        <CaretRight className="inline w-3 h-3 mx-0.5 text-gray-300" />
                        <span className="text-emerald-600">{edge.target_name}</span>
                      </div>
                    </div>
                  </div>
                  {/* 操作 */}
                  <div className="flex gap-1.5 mt-2.5">
                    <Button
                      variant="default"
                      size="sm"
                      className="h-7 text-xs flex-1 bg-indigo-500 hover:bg-indigo-600"
                      onClick={() => handleAction(edge.id, 'approve')}
                    >
                      <Check className="w-3 h-3 mr-1" />确认
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 text-xs"
                      onClick={() => handleAction(edge.id, 'reject')}
                    >
                      <EyeSlash className="w-3 h-3 mr-1" />忽略
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </ScrollArea>
    </div>
  );
};
