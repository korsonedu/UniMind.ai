import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import { X, Link2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { EdgeType } from './types';
import { EDGE_LABELS, EDGE_COLORS, EDGE_DEFAULTS } from './types';

interface Props {
  sourceName: string;
  targetName: string;
  onCreate: (type: EdgeType, weight: number) => void;
  onClose: () => void;
}

const EDGE_TYPES: { type: EdgeType; desc: string }[] = [
  { type: 'similar', desc: '概念相近，复习时互相激活' },
  { type: 'prerequisite', desc: '必须先学 A 才能学 B' },
  { type: 'derivation', desc: 'B 可以从 A 推导出来' },
  { type: 'confusion', desc: '学生经常混淆这两个概念' },
  { type: 'contrast', desc: '两个概念互相对立或互补' },
  { type: 'co_occur', desc: '经常同时出现，但无强因果' },
];

const WEIGHT_HINTS: [number, string][] = [
  [0, '微弱'], [0.25, '中等'], [0.5, '显著'], [0.75, '强关联'],
];

export const EdgeCreateModal: React.FC<Props> = ({ sourceName, targetName, onCreate, onClose }) => {
  const [edgeType, setEdgeType] = useState<EdgeType>('similar');
  const [weight, setWeight] = useState(EDGE_DEFAULTS.similar);

  const handleTypeSelect = (type: EdgeType) => {
    setEdgeType(type);
    setWeight(EDGE_DEFAULTS[type]);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-xl border w-[420px] overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* 头部 */}
        <div className="flex items-center justify-between px-5 py-4 border-b bg-gray-50/50">
          <div className="flex items-center gap-2">
            <Link2 className="w-4 h-4 text-indigo-500" />
            <span className="font-semibold text-sm">创建知识关联</span>
          </div>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose}>
            <X className="w-4 h-4" />
          </Button>
        </div>

        {/* 连接的节点 */}
        <div className="px-5 py-3 border-b bg-white">
          <div className="flex items-center gap-2 text-sm">
            <span className="px-2.5 py-1 rounded-lg bg-blue-50 text-blue-700 font-medium text-xs">{sourceName}</span>
            <span className="text-gray-300">→</span>
            <span className="px-2.5 py-1 rounded-lg bg-emerald-50 text-emerald-700 font-medium text-xs">{targetName}</span>
          </div>
        </div>

        {/* 关系类型选择 */}
        <div className="p-5 space-y-4">
          <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider">关系类型</label>
          <div className="grid grid-cols-2 gap-2">
            {EDGE_TYPES.map(({ type, desc }) => (
              <button
                key={type}
                onClick={() => handleTypeSelect(type)}
                className={cn(
                  'text-left px-3 py-2.5 rounded-xl border transition-all duration-150',
                  edgeType === type
                    ? 'border-2 shadow-sm'
                    : 'border-gray-200 hover:border-gray-300 bg-white',
                )}
                style={edgeType === type ? { borderColor: EDGE_COLORS[type] } : {}}
              >
                <div className="flex items-center gap-1.5">
                  <div
                    className="w-2 h-2 rounded-full flex-shrink-0"
                    style={{ backgroundColor: EDGE_COLORS[type] }}
                  />
                  <span className="text-sm font-semibold">{EDGE_LABELS[type]}</span>
                </div>
                <div className="text-[11px] text-gray-400 mt-0.5 leading-tight">{desc}</div>
              </button>
            ))}
          </div>

          {/* 权重滑块 */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider">扩散权重</label>
              <span className="text-sm font-mono font-bold" style={{ color: EDGE_COLORS[edgeType] }}>
                {weight.toFixed(2)}
              </span>
            </div>
            <Slider
              value={[weight]}
              onValueChange={([v]) => setWeight(v)}
              min={0.05}
              max={1}
              step={0.05}
              className="w-full"
            />
            <div className="flex justify-between text-[10px] text-gray-300">
              {WEIGHT_HINTS.map(([v, label]) => (
                <span key={v}>{label}</span>
              ))}
            </div>
          </div>
        </div>

        {/* 底部按钮 */}
        <div className="px-5 py-4 border-t bg-gray-50/50 flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onClose}>取消</Button>
          <Button size="sm" onClick={() => onCreate(edgeType, weight)}>
            确认创建
          </Button>
        </div>
      </div>
    </div>
  );
};
