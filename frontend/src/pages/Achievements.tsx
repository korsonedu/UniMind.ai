import React, { useState, useEffect } from 'react';
import api from '@/lib/api';
import { toast } from 'sonner';
import { PageWrapper } from '@/components/PageWrapper';
import { InlineError } from '@/components/InlineError';
import { EmptyState } from '@/components/EmptyState';
import { Card, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Medal, Trophy } from '@phosphor-icons/react';

// ── Types ──

interface AchievementData {
  id: number;
  key: string;
  name: string;
  description: string;
  icon: string;
  category: string;
  category_label: string;
  threshold: number;
  is_unlocked: boolean;
  unlocked_at: string | null;
  progress: number;
}

const CATEGORIES = [
  { key: 'all', label: '全部' },
  { key: 'streak', label: '连续打卡' },
  { key: 'question', label: '刷题里程碑' },
  { key: 'diagnostic', label: '首次诊断' },
  { key: 'mastery', label: '掌握知识点' },
  { key: 'exam', label: '考试成绩' },
];

// ── Helper ──

function formatUnlockedAt(iso: string): string {
  const d = new Date(iso);
  const m = d.getMonth() + 1;
  const day = d.getDate();
  return `${m}月${day}日解锁`;
}

// ── AchievementCard ──

function AchievementCard({
  a,
  index,
}: {
  a: AchievementData;
  index: number;
}) {
  const pct = a.threshold > 0 ? Math.round((a.progress / a.threshold) * 100) : 0;

  if (a.is_unlocked) {
    return (
      <Card
        variant="elevated"
        className="rounded-2xl border-emerald-200/60 overflow-hidden animate-achievement-pop"
        style={{ animationDelay: `${index * 80}ms` }}
      >
        <CardContent className="p-4 flex flex-col items-center text-center gap-2">
          <span className="text-3xl">{a.icon}</span>
          <p className="text-sm font-bold text-foreground/90">{a.name}</p>
          <p className="text-[11px] text-muted-foreground/60 leading-relaxed">
            {a.description}
          </p>
          <Badge variant="apple-green" className="text-[10px] px-2 py-0 h-5">
            已解锁
          </Badge>
          {a.unlocked_at && (
            <p className="text-[10px] text-muted-foreground/40">
              {formatUnlockedAt(a.unlocked_at)}
            </p>
          )}
        </CardContent>
      </Card>
    );
  }

  // locked
  return (
    <Card
      variant="ghost"
      className="rounded-2xl border-border/30 overflow-hidden animate-achievement-pop"
      style={{ animationDelay: `${index * 80}ms` }}
    >
      <CardContent className="p-4 flex flex-col items-center text-center gap-2">
        <span className="text-3xl opacity-30 saturate-0">{a.icon}</span>
        <p className="text-sm font-semibold text-muted-foreground">{a.name}</p>
        <p className="text-[11px] text-muted-foreground/40 leading-relaxed">
          {a.description}
        </p>
        <div className="w-full space-y-1">
          <Progress value={pct} className="h-1.5" />
          <p className="text-[10px] text-muted-foreground/50">
            {a.progress} / {a.threshold}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Skeleton Grid ──

function SkeletonGrid() {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
      {Array.from({ length: 6 }).map((_, i) => (
        <Skeleton key={i} className="h-40 rounded-2xl" />
      ))}
    </div>
  );
}

// ── Main Page ──

export function Achievements() {
  const [data, setData] = useState<AchievementData[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [category, setCategory] = useState('all');

  const fetchData = () => {
    setLoading(true);
    setError(null);
    api
      .get('/users/achievements/')
      .then((res) => {
        setData(res.data);
        const unlocked = res.data.filter((a: AchievementData) => a.is_unlocked).length;
        if (unlocked > 0) {
          toast.success(`🏆 已解锁 ${unlocked} 个成就`, { id: 'achievement-count' });
        }
      })
      .catch(() => setError('加载成就失败'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchData();
  }, []);

  // ── Render states ──

  if (loading) {
    return (
      <PageWrapper title="成就勋章" subtitle="解锁成就，记录你的学习旅程">
        <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
          <Skeleton className="h-8 w-48 rounded-lg" />
          <SkeletonGrid />
        </div>
      </PageWrapper>
    );
  }

  if (error) {
    return (
      <PageWrapper title="成就勋章" subtitle="解锁成就，记录你的学习旅程">
        <div className="max-w-5xl mx-auto px-4 py-6">
          <InlineError message={error} onRetry={fetchData} />
        </div>
      </PageWrapper>
    );
  }

  if (!data || data.length === 0) {
    return (
      <PageWrapper title="成就勋章" subtitle="解锁成就，记录你的学习旅程">
        <div className="max-w-5xl mx-auto px-4 py-6">
          <EmptyState icon={Medal} title="暂无成就" description="成就系统尚未配置" />
        </div>
      </PageWrapper>
    );
  }

  // ── Derived ──

  const unlocked = data.filter((a) => a.is_unlocked);
  const filtered = category === 'all' ? data : data.filter((a) => a.category === category);
  const unlockedPct = Math.round((unlocked.length / data.length) * 100);

  return (
    <PageWrapper title="成就勋章" subtitle="解锁成就，记录你的学习旅程">
      <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
        {/* Stats header */}
        <div className="flex items-center gap-4 p-4 rounded-2xl bg-card border border-border/40">
          <div className="w-12 h-12 rounded-xl bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center shrink-0">
            <Trophy className="w-6 h-6 text-amber-600" weight="fill" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-baseline gap-1">
              <span className="text-2xl font-black tabular-nums text-foreground">
                {unlocked.length}
              </span>
              <span className="text-[12px] text-muted-foreground">
                / {data.length} 个成就已解锁
              </span>
            </div>
            <Progress value={unlockedPct} className="h-1.5 mt-1.5" />
          </div>
        </div>

        {/* Category tabs */}
        <Tabs value={category} onValueChange={setCategory}>
          <TabsList className="w-full justify-start overflow-x-auto scrollbar-none bg-transparent gap-1 p-0 h-auto">
            {CATEGORIES.map((c) => (
              <TabsTrigger
                key={c.key}
                value={c.key}
                className="shrink-0 text-[12px] px-3 py-1.5 rounded-lg data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
              >
                {c.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        {/* Achievement grid */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {filtered.map((a, i) => (
            <AchievementCard key={a.key} a={a} index={i} />
          ))}
        </div>

        {filtered.length === 0 && (
          <p className="text-center text-[12px] text-muted-foreground py-8">
            该分类下暂无成就
          </p>
        )}
      </div>
    </PageWrapper>
  );
}
