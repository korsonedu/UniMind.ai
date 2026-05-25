import { useState } from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Check, X, ChevronDown, ChevronUp } from 'lucide-react';
import { cn } from '@/lib/utils';

interface QuestionData {
  question: string;
  q_type: string;
  subjective_type?: string | null;
  options?: string[] | null;
  answer: string;
  grading_points?: string[] | null;
  difficulty_level: string;
  kp_name?: string;
  kp_code?: string;
  review_score?: number;
  review_feedback?: string;
  review_dimensions?: {
    discrimination?: number;
    clarity?: number;
    coverage?: number;
  };
  detected_difficulty?: string;
  difficulty_match?: boolean;
  bloom_level?: string;
  knowledge_tags?: string[];
  answer_correct?: boolean;
  quality_warning?: boolean;
}

interface Props {
  index: number;
  data: QuestionData;
  selected: boolean;
  onToggle: (index: number) => void;
}

const DIFFICULTY_COLORS: Record<string, string> = {
  entry: 'bg-gray-100 text-gray-600',
  easy: 'bg-green-100 text-green-700',
  normal: 'bg-blue-100 text-blue-700',
  hard: 'bg-orange-100 text-orange-700',
  extreme: 'bg-red-100 text-red-700',
};

const BLOOM_LABELS: Record<string, string> = {
  remember: '记忆',
  understand: '理解',
  apply: '应用',
  analyze: '分析',
  evaluate: '评价',
  create: '创造',
};

export default function QuestionReviewCard({ index, data, selected, onToggle }: Props) {
  const [expanded, setExpanded] = useState(false);

  const scoreColor =
    (data.review_score ?? 0) >= 0.8 ? 'text-unimind-green' :
    (data.review_score ?? 0) >= 0.6 ? 'text-amber-600' : 'text-red-500';

  return (
    <Card variant="apple" className={cn('p-4 transition-all', selected && 'ring-2 ring-primary')}>
      <div className="flex items-start gap-3">
        <input
          type="checkbox"
          checked={selected}
          onChange={() => onToggle(index)}
          className="mt-1 h-4 w-4 rounded border-gray-300"
        />
        <div className="flex-1 min-w-0">
          {/* Header badges */}
          <div className="flex items-center gap-2 flex-wrap mb-2">
            <span className="text-xs font-bold text-unimind-text-quaternary">#{index + 1}</span>
            {data.kp_name && (
              <Badge variant="outline" className="text-[10px]">
                {data.kp_code ? `${data.kp_code} ` : ''}{data.kp_name}
              </Badge>
            )}
            <Badge className={cn('text-[10px]', DIFFICULTY_COLORS[data.difficulty_level] || 'bg-gray-100')}>
              {data.difficulty_level}
            </Badge>
            <Badge variant="outline" className="text-[10px]">
              {data.q_type === 'objective' ? '客观题' : data.subjective_type || '主观题'}
            </Badge>
            {data.bloom_level && (
              <Badge variant="outline" className="text-[10px]">
                {BLOOM_LABELS[data.bloom_level] || data.bloom_level}
              </Badge>
            )}
            {data.quality_warning && (
              <Badge className="text-[10px] bg-amber-100 text-amber-700">质量警告</Badge>
            )}
          </div>

          {/* Question text */}
          <p className="text-sm text-foreground leading-relaxed">{data.question}</p>

          {/* Options (objective) */}
          {data.options && data.options.length > 0 && (
            <div className="mt-2 space-y-1">
              {data.options.map((opt, i) => (
                <p key={i} className="text-xs text-unimind-text-secondary pl-4">{opt}</p>
              ))}
            </div>
          )}

          {/* Answer */}
          <div className="mt-2 p-2 rounded bg-muted/50">
            <p className="text-xs font-bold text-foreground mb-0.5">参考答案</p>
            <p className="text-xs text-unimind-text-secondary">{data.answer}</p>
          </div>

          {/* ARC metadata row */}
          <div className="mt-2 flex items-center gap-3 flex-wrap">
            {data.review_score != null && (
              <span className={cn('text-xs font-bold', scoreColor)}>
                质量分 {(data.review_score * 100).toFixed(0)}%
              </span>
            )}
            {data.detected_difficulty && (
              <span className="text-xs text-unimind-text-quaternary">
                AI 检测难度: {data.detected_difficulty}
                {data.difficulty_match === false && <span className="text-red-500 ml-1">(不匹配)</span>}
              </span>
            )}
            {data.answer_correct === false && (
              <span className="text-xs text-red-500 font-bold">答案存疑</span>
            )}
          </div>

          {/* Expand for details */}
          {(data.review_feedback || data.review_dimensions || data.grading_points?.length) && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="mt-2 flex items-center gap-1 text-xs text-primary hover:underline"
            >
              {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
              {expanded ? '收起详情' : '查看详情'}
            </button>
          )}

          {expanded && (
            <div className="mt-2 space-y-2 text-xs">
              {data.review_dimensions && (
                <div className="flex gap-4 text-unimind-text-secondary">
                  <span>区分度: {((data.review_dimensions.discrimination ?? 0) * 100).toFixed(0)}%</span>
                  <span>清晰度: {((data.review_dimensions.clarity ?? 0) * 100).toFixed(0)}%</span>
                  <span>覆盖度: {((data.review_dimensions.coverage ?? 0) * 100).toFixed(0)}%</span>
                </div>
              )}
              {data.review_feedback && (
                <p className="text-unimind-text-tertiary p-2 bg-muted/50 rounded">{data.review_feedback}</p>
              )}
              {data.grading_points && data.grading_points.length > 0 && (
                <div>
                  <p className="font-bold text-foreground mb-1">评分要点:</p>
                  <ul className="list-disc pl-4 space-y-0.5 text-unimind-text-secondary">
                    {data.grading_points.map((pt, i) => <li key={i}>{pt}</li>)}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
