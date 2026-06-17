import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts';
import { PageWrapper } from '@/components/PageWrapper';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/EmptyState';
import { InlineError } from '@/components/InlineError';
import { cn } from '@/lib/utils';
import { useAuthStore } from '@/store/useAuthStore';
import api from '@/lib/api';
import { Download, FileText, Trophy, Target, Fire } from '@phosphor-icons/react';

interface ReportData {
  student: { id: number; nickname: string; elo_score: number; date_joined: string };
  stats: { total_attempted: number; total_distinct: number; correct_count: number; wrong_count: number; mastered_count: number; accuracy: number; study_streak: number; checkin_streak: number };
  radar: { subject: string; avg_mastery: number; kp_count: number }[];
  daily_activity: { date: string; count: number }[];
  exams: { id: number; total_score: number; max_score: number; percentage: number; elo_change: number; created_at: string }[];
  achievements: { key: string; name: string; description: string; icon: string; category: string; unlocked_at: string }[];
}

export const ReportCard: React.FC = () => {
  const { user } = useAuthStore();
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
    <PageWrapper title="成绩报告" subtitle="你的学习成果总览">
      <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
        <div className="grid grid-cols-3 gap-4">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-24 rounded-2xl" />)}
        </div>
        <Skeleton className="h-64 rounded-2xl" />
        <Skeleton className="h-48 rounded-2xl" />
      </div>
    </PageWrapper>
  );

  if (error) return (
    <PageWrapper title="成绩报告" subtitle="你的学习成果总览">
      <InlineError message={error} onRetry={() => window.location.reload()} />
    </PageWrapper>
  );

  if (!data) return (
    <PageWrapper title="成绩报告" subtitle="你的学习成果总览">
      <EmptyState icon={FileText} title="暂无数据" description="开始学习后这里将显示你的成绩报告" />
    </PageWrapper>
  );

  const { student, stats, radar, exams, achievements } = data;

  return (
    <PageWrapper
      title="成绩报告"
      subtitle={`${student.nickname} · ELO ${student.elo_score}`}
      action={
        <Button onClick={handleDownloadPDF} disabled={downloading} variant="outline" className="rounded-xl gap-2">
          <Download className="w-4 h-4" />
          {downloading ? '生成中...' : '下载 PDF'}
        </Button>
      }
    >
      <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
        {/* ── 统计卡 Bento Grid ── */}
        <div className="grid grid-cols-3 gap-4">
          <Card className="rounded-2xl border-border/40">
            <CardContent className="p-4 text-center">
              <div className="w-8 h-8 rounded-lg bg-blue-50 dark:bg-blue-900/20 flex items-center justify-center mx-auto mb-2">
                <Target className="w-4 h-4 text-blue-600" />
              </div>
              <p className="text-2xl font-black tabular-nums">{stats.total_attempted}</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">累计答题</p>
            </CardContent>
          </Card>
          <Card className="rounded-2xl border-border/40">
            <CardContent className="p-4 text-center">
              <div className="w-8 h-8 rounded-lg bg-emerald-50 dark:bg-emerald-900/20 flex items-center justify-center mx-auto mb-2">
                <Trophy className="w-4 h-4 text-emerald-600" />
              </div>
              <p className="text-2xl font-black tabular-nums">{stats.accuracy}%</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">正确率</p>
            </CardContent>
          </Card>
          <Card className="rounded-2xl border-border/40">
            <CardContent className="p-4 text-center">
              <div className="w-8 h-8 rounded-lg bg-amber-50 dark:bg-amber-900/20 flex items-center justify-center mx-auto mb-2">
                <Fire className="w-4 h-4 text-amber-600" />
              </div>
              <p className="text-2xl font-black tabular-nums">{stats.study_streak}</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">连续学习（天）</p>
            </CardContent>
          </Card>
        </div>

        {/* ── 知识雷达图 ── */}
        {radar.length > 0 && (
          <Card className="rounded-2xl border-border/40">
            <CardContent className="p-5">
              <h3 className="text-sm font-bold text-foreground/80 mb-4">知识点掌握度</h3>
              <div className="w-full h-64">
                <ResponsiveContainer>
                  <RadarChart data={radar.map(r => ({ ...r, fullMark: 100 }))}>
                    <PolarGrid stroke="#e5e5e5" strokeWidth={0.5} />
                    <PolarAngleAxis dataKey="subject" tick={{ fontSize: 11, fontWeight: 500, fill: '#a3a3a3' }} />
                    <PolarRadiusAxis angle={90} domain={[0, 100]} tick={false} />
                    <Radar name="掌握度" dataKey="avg_mastery" stroke="#2d2b6b" fill="#2d2b6b" fillOpacity={0.12} strokeWidth={1.5} />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
              <div className="flex flex-wrap gap-2 mt-3">
                {radar.map(r => (
                  <div key={r.subject} className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-muted/40 text-[11px]">
                    <span className="font-semibold">{r.subject}</span>
                    <span className="text-muted-foreground">{r.avg_mastery}%</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* ── 考试成绩趋势 ── */}
        {exams.length > 0 && (
          <Card className="rounded-2xl border-border/40">
            <CardContent className="p-5">
              <h3 className="text-sm font-bold text-foreground/80 mb-4">考试成绩趋势</h3>
              <div className="w-full h-48">
                <ResponsiveContainer>
                  <BarChart data={exams.slice().reverse()}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="created_at" tickFormatter={(v: string) => v.slice(5, 10)} tick={{ fontSize: 10, fill: '#a3a3a3' }} />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: '#a3a3a3' }} />
                    <Tooltip formatter={(val: number) => [`${val}%`, '得分率']} labelFormatter={(l: string) => `考试 ${l}`} />
                    <Bar dataKey="percentage" fill="#2d2b6b" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>
        )}

        {/* ── 统计明细 ── */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: '已掌握', value: stats.mastered_count, sub: '道题' },
            { label: '签到 streak', value: stats.checkin_streak, sub: '天' },
            { label: '已解锁成就', value: achievements.length, sub: '个' },
            { label: '总做题数', value: stats.total_attempted, sub: '次' },
          ].map(item => (
            <div key={item.label} className="rounded-xl bg-muted/30 p-3 text-center">
              <p className="text-xl font-bold">{item.value}<span className="text-xs text-muted-foreground ml-0.5">{item.sub}</span></p>
              <p className="text-[10px] text-muted-foreground/60">{item.label}</p>
            </div>
          ))}
        </div>

        {/* ── 成就展示 ── */}
        {achievements.length > 0 && (
          <Card className="rounded-2xl border-border/40">
            <CardContent className="p-5">
              <h3 className="text-sm font-bold text-foreground/80 mb-3">已解锁成就</h3>
              <div className="flex flex-wrap gap-2">
                {achievements.map(a => (
                  <div key={a.key} className="flex items-center gap-2 px-3 py-2 rounded-xl bg-muted/40 border border-border/30">
                    <span className="text-base">{a.icon}</span>
                    <div>
                      <p className="text-[12px] font-semibold">{a.name}</p>
                      <p className="text-[10px] text-muted-foreground/50">{a.description}</p>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </PageWrapper>
  );
};

export default ReportCard;
