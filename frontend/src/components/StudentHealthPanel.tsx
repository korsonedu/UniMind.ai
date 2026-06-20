/**
 * 学生健康度面板 — 流失风险预警。
 * 基于活跃度 + Memorix 复习率 + 连续签到 + 学习趋势四维评分。
 */
import { useEffect, useState, useCallback } from 'react';
import { Warning, CheckCircle, XCircle, Spinner, Users, CaretDown, CaretRight } from '@phosphor-icons/react';
import api from '@/lib/api';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface HealthEntry {
  student_id: number;
  name: string;
  email: string;
  avatar_url: string | null;
  score: number;
  level: 'healthy' | 'at_risk' | 'critical';
  components: { recency: number; memorix: number; streak: number; trend: number };
  details: {
    days_since_active: number;
    overdue_rate: number;
    current_streak: number;
    weekly_trend: string;
    this_week_reviews: number;
    last_week_reviews: number;
  };
}

interface HealthData {
  results: HealthEntry[];
  summary: { total: number; healthy: number; at_risk: number; critical: number };
}

const LEVEL_CONFIG = {
  healthy: { icon: CheckCircle, color: 'text-emerald-500', bg: 'bg-emerald-500/6', label: '健康' },
  at_risk: { icon: Warning, color: 'text-amber-500', bg: 'bg-amber-500/6', label: '需关注' },
  critical: { icon: XCircle, color: 'text-red-500', bg: 'bg-red-500/6', label: '高危' },
};

export function StudentHealthPanel() {
  const [data, setData] = useState<HealthData | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(true);

  const fetchHealth = useCallback(async () => {
    try {
      const { data: res } = await api.get('/users/institution/me/student-health/?include_children=true');
      setData(res);
    } catch {
      // page not accessible for non-admin
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchHealth(); }, [fetchHealth]);

  if (loading) return <div className="py-4"><Spinner className="animate-spin h-4 w-4 text-muted-foreground" /></div>;
  if (!data || data.results.length === 0) return null;

  const { summary, results } = data;
  const riskStudents = results.filter(r => r.level !== 'healthy');

  return (
    <Card variant="apple" className="p-5 space-y-4">
      {/* Summary bar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Users className="h-5 w-5 text-primary" />
          <h3 className="font-bold">学员健康度</h3>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span className="flex items-center gap-1">
            <CheckCircle className="h-4 w-4 text-emerald-500" />
            {summary.healthy} 健康
          </span>
          <span className="flex items-center gap-1">
            <Warning className="h-4 w-4 text-amber-500" />
            {summary.at_risk} 关注
          </span>
          <span className="flex items-center gap-1">
            <XCircle className="h-4 w-4 text-red-500" />
            {summary.critical} 高危
          </span>
        </div>
        {riskStudents.length > 0 && (
          <Button variant="ghost" size="sm" onClick={() => setExpanded(v => !v)}>
            {expanded ? <CaretDown className="h-4 w-4" /> : <CaretRight className="h-4 w-4" />}
            {riskStudents.length} 人需关注
          </Button>
        )}
      </div>

      {/* Detail list */}
      {expanded && (
        <div className="space-y-2 max-h-80 overflow-y-auto">
          {riskStudents.map(s => {
            const cfg = LEVEL_CONFIG[s.level];
            const Icon = cfg.icon;
            return (
              <div key={s.student_id} className="flex items-center gap-3 p-3 rounded-xl bg-muted/40">
                <div className={cn('h-8 w-8 rounded-full flex items-center justify-center text-xs font-bold', cfg.bg, cfg.color)}>
                  {s.name[0]}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-sm truncate">{s.name}</span>
                    <Badge className={cn('text-[10px]', cfg.bg, cfg.color)}>
                      <Icon className="mr-1 h-3 w-3" />
                      {cfg.label} · {s.score}分
                    </Badge>
                  </div>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {s.details.days_since_active}天未活跃 · 复习逾期{Math.round(s.details.overdue_rate * 100)}% ·
                    连续{s.details.current_streak}天 · 趋势{s.details.weekly_trend === 'up' ? '↑' : s.details.weekly_trend === 'down' ? '↓' : '→'}
                  </div>
                </div>
                <div className="flex gap-1 text-xs text-muted-foreground">
                  <span title="活跃度">活{s.components.recency}</span>
                  <span title="记忆健康">记{s.components.memorix}</span>
                  <span title="连续签到">签{s.components.streak}</span>
                  <span title="学习趋势">势{s.components.trend}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
