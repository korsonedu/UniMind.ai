/**
 * 学生端 - 成绩报告
 */
import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
} from 'recharts';
import { PageWrapper } from '@/components/PageWrapper';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/EmptyState';
import { InlineError } from '@/components/InlineError';
import { cn } from '@/lib/utils';
import { useAuthStore } from '@/store/useAuthStore';
import api from '@/lib/api';
import { Download, FileText, Trophy, Target, Fire, GraduationCap, Medal } from '@phosphor-icons/react';

interface ReportData {
  student: { id: number; nickname: string; elo_score: number; date_joined: string };
  stats: { total_attempted: number; total_distinct: number; correct_count: number; wrong_count: number; mastered_count: number; accuracy: number; study_streak: number; checkin_streak: number };
  radar: { subject: string; avg_mastery: number; kp_count: number }[];
  daily_activity: { date: string; count: number }[];
  exams: { id: number; total_score: number; max_score: number; percentage: number; elo_change: number; created_at: string }[];
  achievements: { key: string; name: string; description: string; icon: string; category: string; unlocked_at: string }[];
}

export const ReportCard: React.FC = () => {
  const user = useAuthStore(s => s.user);
  const { t } = useTranslation('common');
  const [data, setData] = useState<ReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    api.get('/users/me/report-card/')
      .then(r => { setData(r.data); setLoading(false); })
      .catch(err => { setError(err.message || '加载失败'); setLoading(false); });
  }, []);

  const handleDownloadPDF = async () => {
    setDownloading(true);
    try {
      const res = await api.get('/users/me/report-card/pdf/', { responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `report_${data?.student?.nickname || 'student'}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // ignore
    } finally {
      setDownloading(false);
    }
  };

  if (loading) return (
    <PageWrapper title="成绩报告" subtitle="">
      <div className="max-w-3xl mx-auto py-8 space-y-6">
        <div className="grid grid-cols-3 gap-3">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-28 rounded-2xl" />)}
        </div>
        <Skeleton className="h-64 rounded-2xl" />
        <Skeleton className="h-48 rounded-2xl" />
      </div>
    </PageWrapper>
  );

  if (error) return (
    <PageWrapper title="成绩报告" subtitle="">
      <InlineError message={error} onRetry={() => window.location.reload()} />
    </PageWrapper>
  );

  if (!data) return (
    <PageWrapper title="成绩报告" subtitle="">
      <EmptyState icon={FileText} title="暂无数据" description="开始学习后这里将显示你的成绩报告" />
    </PageWrapper>
  );

  const { student, stats, radar, exams, achievements } = data;

  return (
    <PageWrapper
      title="成绩报告"
      subtitle=""
      action={
        <Button onClick={handleDownloadPDF} disabled={downloading} variant="outline" size="sm" className="rounded-lg gap-2">
          <Download className="w-4 h-4" weight="bold" />
          {downloading ? '生成中...' : '下载 PDF'}
        </Button>
      }
    >
      <div className="max-w-3xl mx-auto space-y-8 pb-8">
        {/* Student identity */}
        <div className="flex items-center gap-3 pt-2">
          <div className="h-10 w-10 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
            <GraduationCap className="h-5 w-5 text-primary" weight="fill" />
          </div>
          <div className="min-w-0">
            <h2 className="text-lg font-bold truncate">{student.nickname}</h2>
            <p className="text-xs text-muted-foreground">ELO {student.elo_score}</p>
          </div>
        </div>

        {/* Stats overview */}
        <div className="grid grid-cols-3 gap-3">
          <div className="rounded-2xl bg-card border border-border/60 p-4 text-center">
            <div className="w-8 h-8 rounded-lg bg-blue-50 dark:bg-blue-950/30 flex items-center justify-center mx-auto mb-2.5">
              <Target className="w-4 h-4 text-blue-600 dark:text-blue-400" weight="fill" />
            </div>
            <p className="text-[28px] font-bold tabular-nums leading-none">{stats.total_attempted}</p>
            <p className="text-[11px] text-muted-foreground mt-1.5 font-medium">累计答题</p>
          </div>
          <div className="rounded-2xl bg-card border border-border/60 p-4 text-center">
            <div className="w-8 h-8 rounded-lg bg-emerald-50 dark:bg-emerald-950/30 flex items-center justify-center mx-auto mb-2.5">
              <Trophy className="w-4 h-4 text-emerald-600 dark:text-emerald-400" weight="fill" />
            </div>
            <p className="text-[28px] font-bold tabular-nums leading-none">{stats.accuracy}%</p>
            <p className="text-[11px] text-muted-foreground mt-1.5 font-medium">正确率</p>
          </div>
          <div className="rounded-2xl bg-card border border-border/60 p-4 text-center">
            <div className="w-8 h-8 rounded-lg bg-amber-50 dark:bg-amber-950/30 flex items-center justify-center mx-auto mb-2.5">
              <Fire className="w-4 h-4 text-amber-600 dark:text-amber-400" weight="fill" />
            </div>
            <p className="text-[28px] font-bold tabular-nums leading-none">{stats.study_streak}</p>
            <p className="text-[11px] text-muted-foreground mt-1.5 font-medium">连续学习</p>
          </div>
        </div>

        {/* Knowledge radar */}
        {radar.length > 0 && (
          <section>
            <h3 className="text-sm font-bold mb-4 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-primary/60" />
              知识点掌握度
            </h3>
            <div className="rounded-2xl border border-border/60 bg-card p-5">
              <div className="w-full h-64">
                <ResponsiveContainer>
                  <RadarChart data={radar.map(r => ({ ...r, fullMark: 100 }))}>
                    <PolarGrid stroke="currentColor" strokeWidth={0.5} className="text-border/60" />
                    <PolarAngleAxis
                      dataKey="subject"
                      tick={{ fontSize: 11, fontWeight: 600, fill: 'currentColor' }}
                      className="text-muted-foreground"
                    />
                    <PolarRadiusAxis angle={90} domain={[0, 100]} tick={false} />
                    <Radar
                      name="掌握度"
                      dataKey="avg_mastery"
                      stroke="hsl(var(--primary))"
                      fill="hsl(var(--primary))"
                      fillOpacity={0.1}
                      strokeWidth={2}
                    />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
              <div className="flex flex-wrap gap-2 mt-4">
                {radar.map(r => (
                  <div key={r.subject} className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-muted/40 text-[11px] font-medium">
                    <span>{r.subject}</span>
                    <span className="text-muted-foreground">{r.avg_mastery}%</span>
                  </div>
                ))}
              </div>
            </div>
          </section>
        )}

        {/* Exam scores */}
        {exams.length > 0 && (
          <section>
            <h3 className="text-sm font-bold mb-4 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-primary/60" />
              考试成绩趋势
            </h3>
            <div className="rounded-2xl border border-border/60 bg-card p-5">
              <div className="w-full h-48">
                <ResponsiveContainer>
                  <BarChart data={exams.slice().reverse()}>
                    <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-border/40" />
                    <XAxis
                      dataKey="created_at"
                      tickFormatter={(v: string) => v.slice(5, 10)}
                      tick={{ fontSize: 11, fontWeight: 500, fill: 'currentColor' }}
                      className="text-muted-foreground"
                    />
                    <YAxis
                      domain={[0, 100]}
                      tick={{ fontSize: 11, fontWeight: 500, fill: 'currentColor' }}
                      className="text-muted-foreground"
                    />
                    <Tooltip
                      formatter={(val: any) => [`${val}%`, '得分率']}
                      labelFormatter={(l: any) => `考试 ${l}`}
                    />
                    <Bar dataKey="percentage" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </section>
        )}

        {/* Detail stats */}
        <div className="grid grid-cols-2 gap-3">
          {[
            { icon: GraduationCap, label: '已掌握', value: stats.mastered_count, unit: '道题', color: 'text-emerald-600 dark:text-emerald-400' },
            { icon: Fire, label: '签到', value: stats.checkin_streak, unit: '天', color: 'text-amber-600 dark:text-amber-400' },
            { icon: Medal, label: '成就', value: achievements.length, unit: '个', color: 'text-blue-600 dark:text-blue-400' },
            { icon: Target, label: '总做题', value: stats.total_attempted, unit: '次', color: 'text-primary' },
          ].map(item => (
            <div key={item.label} className="rounded-2xl border border-border/60 bg-card p-4 flex items-center gap-3">
              <div className="h-9 w-9 rounded-lg bg-muted/40 flex items-center justify-center shrink-0">
                <item.icon className={cn('h-4 w-4', item.color)} weight="fill" />
              </div>
              <div>
                <p className="text-xl font-bold tabular-nums leading-none">
                  {item.value}
                  <span className="text-xs text-muted-foreground font-normal ml-0.5">{item.unit}</span>
                </p>
                <p className="text-[11px] text-muted-foreground mt-0.5 font-medium">{item.label}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Achievements */}
        {achievements.length > 0 && (
          <section>
            <h3 className="text-sm font-bold mb-4 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-amber-400/80" />
              已解锁成就
            </h3>
            <div className="flex flex-wrap gap-2">
              {achievements.map(a => (
                <div
                  key={a.key}
                  className="flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl bg-card border border-border/60 hover:border-border transition-colors"
                >
                  <span className="text-lg leading-none">{a.icon}</span>
                  <div className="min-w-0">
                    <p className="text-[12px] font-semibold truncate">{a.name}</p>
                    <p className="text-[10px] text-muted-foreground/50 truncate">{a.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </PageWrapper>
  );
};

export default ReportCard;
