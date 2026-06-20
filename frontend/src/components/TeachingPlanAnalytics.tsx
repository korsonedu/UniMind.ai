import { useState, useEffect } from 'react';
import api from '@/lib/api';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Spinner, ChartBar, Warning, ArrowRight, Lightning } from '@phosphor-icons/react';
import { toast } from 'sonner';

interface KpPerf {
  kp_id: number; kp_name: string; kp_code: string;
  correct_rate: number; total_attempts: number; student_count: number;
  trend: string; mastery_avg?: number;
}

interface PrereqChain { chain: { kp_id: number; kp_name: string; correct_rate: number | null }[]; root_kp_id: number }
interface ForgettingRisk { kp_id: number; kp_name: string; avg_retrievability: number; review_count: number }

interface AnalyticsData {
  subject: string; class_name: string; student_count: number;
  performance: KpPerf[]; weak_kps: KpPerf[];
  prerequisite_chains: PrereqChain[]; forgetting_risk: ForgettingRisk[];
  ai_suggestions: string | null;
}

interface Props { planId: number }

export function TeachingPlanAnalytics({ planId }: Props) {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchAnalytics = async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/courses/teaching-plans/${planId}/analytics/`);
      setData(data);
    } catch { toast.error('加载学情分析失败'); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchAnalytics(); }, [planId]);

  if (loading) return (
    <div className="flex items-center justify-center py-8">
      <Spinner className="h-5 w-5 animate-spin text-muted-foreground" />
      <span className="ml-2 text-sm text-muted-foreground">正在分析班级学情…</span>
    </div>
  );

  if (!data || data.student_count === 0) return (
    <Card variant="flat" className="p-6 text-center text-sm text-muted-foreground">
      该班级暂无学习数据，开始使用后将自动分析
    </Card>
  );

  const perfSorted = [...data.performance].sort((a, b) => a.correct_rate - b.correct_rate);

  return (
    <div className="space-y-4 animate-in fade-in slide-in-from-top-2 duration-300">
      {/* summary */}
      <div className="grid grid-cols-3 gap-3">
        <Card variant="flat" className="p-3 text-center">
          <p className="text-[10px] text-muted-foreground uppercase tracking-wider">学生数</p>
          <p className="text-lg font-bold tabular-nums mt-0.5">{data.student_count}</p>
        </Card>
        <Card variant="flat" className="p-3 text-center">
          <p className="text-[10px] text-muted-foreground uppercase tracking-wider">平均正确率</p>
          <p className="text-lg font-bold tabular-nums mt-0.5">
            {data.performance.length > 0
              ? Math.round(data.performance.reduce((s, p) => s + p.correct_rate, 0) / data.performance.length)
              : '-'}%
          </p>
        </Card>
        <Card variant="flat" className="p-3 text-center">
          <p className="text-[10px] text-muted-foreground uppercase tracking-wider">薄弱知识点</p>
          <p className="text-lg font-bold tabular-nums mt-0.5 text-amber-600">{data.weak_kps.length}</p>
        </Card>
      </div>

      {/* knowledge point performance bar */}
      {perfSorted.length > 0 && (
        <div>
          <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-2">
            <ChartBar className="w-3.5 h-3.5 inline mr-1" />知识点掌握度
          </p>
          <div className="space-y-1.5 max-h-64 overflow-y-auto">
            {perfSorted.slice(0, 15).map(kp => {
              const color = kp.correct_rate >= 80 ? 'bg-emerald-500' : kp.correct_rate >= 60 ? 'bg-amber-500' : 'bg-red-500';
              return (
                <div key={kp.kp_id} className="flex items-center gap-2 text-xs">
                  <span className="w-28 truncate text-muted-foreground">{kp.kp_name}</span>
                  <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                    <div className={`h-full rounded-full transition-all duration-500 ${color}`}
                      style={{ width: `${Math.max(kp.correct_rate, 2)}%` }} />
                  </div>
                  <span className="w-10 text-right tabular-nums font-medium">{kp.correct_rate}%</span>
                  <span className="w-8 text-right text-[10px] text-muted-foreground">{kp.total_attempts}次</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* weak KPs */}
      {data.weak_kps.length > 0 && (
        <div>
          <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-2">
            <Warning className="w-3.5 h-3.5 inline mr-1 text-amber-500" />需重点强化
          </p>
          <div className="flex flex-wrap gap-1.5">
            {data.weak_kps.map(kp => (
              <Badge key={kp.kp_id} variant="outline"
                className="text-[10px] border-amber-500/30 bg-amber-50 dark:bg-amber-950/20">
                {kp.kp_name} <span className="ml-1 text-amber-600">{kp.correct_rate}%</span>
              </Badge>
            ))}
          </div>
        </div>
      )}

      {/* prerequisite chains */}
      {data.prerequisite_chains.length > 0 && (
        <div>
          <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-2">
            <ArrowRight className="w-3.5 h-3.5 inline mr-1" />知识前驱链
          </p>
          <div className="space-y-1.5">
            {data.prerequisite_chains.slice(0, 3).map((pc, i) => (
              <div key={i} className="flex items-center gap-1 flex-wrap text-[11px]">
                {pc.chain.map((n, j) => (
                  <span key={n.kp_id} className="flex items-center gap-1">
                    <Badge variant={n.correct_rate !== null && n.correct_rate < 60 ? 'destructive' : 'secondary'}
                      className="text-[10px]">{n.kp_name}</Badge>
                    {j < pc.chain.length - 1 && <span className="text-muted-foreground">→</span>}
                  </span>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* forgetting risk */}
      {data.forgetting_risk.length > 0 && (
        <div>
          <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-2">遗忘风险</p>
          <div className="flex flex-wrap gap-1.5">
            {data.forgetting_risk.slice(0, 5).map(r => (
              <Badge key={r.kp_id} variant="outline"
                className="text-[10px] border-purple-500/30 bg-purple-50 dark:bg-purple-950/20">
                {r.kp_name} <span className="ml-1 text-purple-600">{Math.round(r.avg_retrievability * 100)}%</span>
              </Badge>
            ))}
          </div>
        </div>
      )}

      {/* AI suggestions */}
      {data.ai_suggestions && (
        <Card variant="apple" className="p-4">
          <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-2">
            <Lightning className="w-3.5 h-3.5 inline mr-1 text-primary" />AI 教学建议
          </p>
          <p className="text-sm whitespace-pre-wrap leading-relaxed text-muted-foreground">{data.ai_suggestions}</p>
        </Card>
      )}
    </div>
  );
}
