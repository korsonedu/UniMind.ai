import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Loader2, TrendingUp, TrendingDown, Minus, Target } from 'lucide-react';
import api from '@/lib/api';
import { cn } from '@/lib/utils';

interface KpData {
  kp_id: number;
  kp_name: string;
  kp_code: string;
  correct_rate: number;
  total_attempts: number;
  student_count: number;
  trend: 'up' | 'down' | 'stable';
}

interface SuggestedTopic {
  kp_id: number;
  kp_name: string;
  kp_code: string;
  correct_rate: number;
  total_attempts: number;
  student_count: number;
  priority: 'high' | 'medium' | 'low';
  suggested_action: string;
}

const TREND_ICON = {
  up: TrendingUp,
  down: TrendingDown,
  stable: Minus,
};

const TREND_COLOR = {
  up: 'text-unimind-green',
  down: 'text-red-500',
  stable: 'text-unimind-text-quaternary',
};

const PRIORITY_BADGE = {
  high: 'bg-red-100 text-red-700',
  medium: 'bg-amber-100 text-amber-700',
  low: 'bg-green-100 text-green-700',
};

export default function ClassPerformancePanel() {
  const navigate = useNavigate();
  const [kpList, setKpList] = useState<KpData[]>([]);
  const [suggested, setSuggested] = useState<SuggestedTopic[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get('/users/institution/me/analytics/class-performance/'),
      api.get('/users/institution/me/analytics/suggested-topics/'),
    ])
      .then(([perfRes, sugRes]) => {
        setKpList(perfRes.data.results || []);
        setSuggested(sugRes.data.suggested_topics || []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (kpList.length === 0) {
    return null;
  }

  const maxRate = Math.max(...kpList.map(k => k.correct_rate), 1);
  // Show top 12 weakest KPs in the bar chart
  const displayKps = kpList.slice(0, 12);

  return (
    <div className="space-y-4">
      {/* Bar chart */}
      <Card variant="apple" className="p-6">
        <h3 className="text-sm font-extrabold text-foreground mb-4">
          各知识点正确率
          <span className="text-xs font-normal text-unimind-text-quaternary ml-2">
            共 {kpList.length} 个知识点
          </span>
        </h3>
        <div className="space-y-2.5">
          {displayKps.map((kp) => {
            const TrendIcon = TREND_ICON[kp.trend];
            const barWidth = maxRate > 0 ? (kp.correct_rate / maxRate) * 100 : 0;
            const barColor =
              kp.correct_rate < 40 ? 'bg-red-400' :
              kp.correct_rate < 60 ? 'bg-amber-400' :
              'bg-primary';

            return (
              <div key={kp.kp_id} className="flex items-center gap-3">
                <div className="w-32 shrink-0 truncate text-xs font-medium text-foreground" title={kp.kp_name}>
                  {kp.kp_code ? `${kp.kp_code} ` : ''}{kp.kp_name}
                </div>
                <div className="flex-1 h-5 bg-muted rounded-full overflow-hidden relative">
                  <div
                    className={cn('h-full rounded-full transition-all duration-500', barColor)}
                    style={{ width: `${barWidth}%` }}
                  />
                </div>
                <div className="w-14 text-right text-xs font-bold text-foreground">
                  {kp.correct_rate}%
                </div>
                <TrendIcon className={cn('h-3.5 w-3.5 shrink-0', TREND_COLOR[kp.trend])} />
              </div>
            );
          })}
        </div>
      </Card>

      {/* Suggested topics */}
      {suggested.length > 0 && (
        <Card variant="apple" className="p-6">
          <h3 className="text-sm font-extrabold text-foreground mb-3">
            <Target className="h-4 w-4 inline mr-1.5 text-primary" />
            重点关注
          </h3>
          <div className="space-y-3">
            {suggested.map((topic) => (
              <div key={topic.kp_id} className="flex items-start gap-3 p-3 rounded-lg bg-muted/50">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-foreground truncate">
                      {topic.kp_name}
                    </span>
                    <span className={cn(
                      'text-[10px] font-bold px-1.5 py-0.5 rounded',
                      PRIORITY_BADGE[topic.priority],
                    )}>
                      {topic.priority === 'high' ? '紧急' : topic.priority === 'medium' ? '中等' : '关注'}
                    </span>
                  </div>
                  <p className="text-xs text-unimind-text-tertiary mt-0.5">
                    {topic.suggested_action}
                  </p>
                  <p className="text-[11px] text-unimind-text-quaternary mt-1">
                    正确率 {topic.correct_rate}% · {topic.student_count} 名学生 · {topic.total_attempts} 次作答
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  className="shrink-0 text-xs"
                  onClick={() => navigate(`/workbench?kp=${topic.kp_id}`)}
                >
                  针对出题
                </Button>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
