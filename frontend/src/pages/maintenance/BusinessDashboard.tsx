/**
 * 机构管理 — 业务数据看板。
 * 学生数 / 月活 / 作业数 / 留存率。
 */
import { useEffect, useState } from 'react';
import { Spinner, Users, UserCircle, ClipboardText, ChartLine, TrendUp, TrendDown, CurrencyDollar, ClockCounterClockwise, CreditCard } from '@phosphor-icons/react';
import api from '@/lib/api';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

interface BusinessDashboardData {
  student_count: number;
  active_students_this_month: number;
  total_assignments: number;
  retention_rate: number | null;
  revenue: number;
  revenue_this_month: number;
  mrr: number;
  arr: number;
  active_subscriptions: number;
  subscriptions_by_plan?: Record<string, number>;
  arpu: number;
  renewal_rate: number;
  paying_users: number;
  trends?: {
    students_trend?: 'up' | 'down' | 'flat';
    active_trend?: 'up' | 'down' | 'flat';
    assignments_trend?: 'up' | 'down' | 'flat';
    retention_trend?: 'up' | 'down' | 'flat';
  };
}

const STAT_CARDS = [
  { key: 'student_count' as const, label: '总学生数', icon: Users, trendKey: 'students_trend' as const },
  { key: 'active_students_this_month' as const, label: '本月活跃', icon: UserCircle, trendKey: 'active_trend' as const },
  { key: 'mrr' as const, label: 'MRR (月经常收入)', icon: CurrencyDollar, prefix: '¥', isCurrency: true },
  { key: 'arr' as const, label: 'ARR (年经常收入)', icon: ChartLine, prefix: '¥', isCurrency: true },
  { key: 'active_subscriptions' as const, label: '活跃订阅', icon: CreditCard },
  { key: 'total_assignments' as const, label: '作业总数', icon: ClipboardText, trendKey: 'assignments_trend' as const },
  { key: 'retention_rate' as const, label: '留存率', icon: ClockCounterClockwise, trendKey: 'retention_trend' as const, suffix: '%' },
  { key: 'renewal_rate' as const, label: '续费率', icon: TrendUp, suffix: '%' },
];

function TrendIcon({ trend }: { trend?: 'up' | 'down' | 'flat' }) {
  if (trend === 'up') return <TrendUp className="h-3.5 w-3.5 text-emerald-500" />;
  if (trend === 'down') return <TrendDown className="h-3.5 w-3.5 text-red-500" />;
  return null;
}

export function BusinessDashboard() {
  const [data, setData] = useState<BusinessDashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(false);
    api
      .get('/users/institution/me/business-dashboard/')
      .then((res) => {
        setData(res.data);
      })
      .catch(() => {
        toast.error('加载业务数据失败');
        setError(true);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto p-4 md:p-6 space-y-6">
        <Skeleton className="h-7 w-40" />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <Card key={i}>
              <CardHeader className="pb-2">
                <Skeleton className="h-4 w-20" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-8 w-16" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-sm text-muted-foreground">加载失败，请稍后重试</p>
      </div>
    );
  }

  const stats = data!;

  return (
    <div className="max-w-4xl mx-auto p-4 md:p-6 space-y-6">
      <h1 className="text-lg font-bold">业务数据</h1>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {STAT_CARDS.map((card) => {
          const Icon = card.icon;
          const value = stats[card.key];
          const trend = stats.trends?.[card.trendKey as keyof typeof stats.trends];
          let display = '—';
          if (value != null) {
            if (card.isCurrency) {
              display = `¥${Number(value).toLocaleString()}`;
            } else {
              display = `${card.prefix || ''}${value}${card.suffix || ''}`;
            }
          }
          return (
            <Card key={card.key}>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
                  <Icon className="h-3.5 w-3.5" />
                  {card.label}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-end gap-2">
                  <p className="text-2xl font-bold">{display}</p>
                  <TrendIcon trend={trend} />
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
