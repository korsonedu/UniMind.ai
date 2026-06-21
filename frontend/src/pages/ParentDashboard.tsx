import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '@/lib/api';
import { toast } from 'sonner';
import { PageWrapper } from '@/components/PageWrapper';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Label } from '@/components/ui/label';
import { useAuthStore } from '@/store/useAuthStore';
import {
  User,
  Heart,
  BookOpen,
  CalendarCheck,
  FileText,
  Plus,
  ArrowRight,
  Lightning,
  Trophy,
} from '@phosphor-icons/react';

interface ChildLink {
  id: number;
  student: number;
  student_name: string;
  verified: boolean;
  created_at: string;
  verified_at: string | null;
}

interface ChildProgress {
  student_id: number;
  student_name: string;
  health: {
    score: number;
    level: string;
    components: Record<string, number>;
    details: Record<string, any>;
  };
  weekly_reviews: number;
  mastered_kp_count: number;
  streak: number;
}

interface WeeklyReport {
  student_name: string;
  week_start: string;
  week_end: string;
  reviews: number;
  accuracy: number;
  new_mastered_kps: number;
  checkins: number;
  exams_taken: number;
  total_minutes: number;
}

const HEALTH_LABELS: Record<string, { label: string; color: string }> = {
  healthy: { label: '健康', color: 'bg-emerald-100 text-emerald-700' },
  at_risk: { label: '需关注', color: 'bg-amber-100 text-amber-700' },
  critical: { label: '预警', color: 'bg-red-100 text-red-700' },
};

export const ParentDashboard: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAuthStore();

  // Bind section
  const [studentEmail, setStudentEmail] = useState('');
  const [binding, setBinding] = useState(false);

  // Children list
  const [children, setChildren] = useState<ChildLink[]>([]);
  const [loadingChildren, setLoadingChildren] = useState(true);

  // Selected child progress
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [progress, setProgress] = useState<ChildProgress | null>(null);
  const [loadingProgress, setLoadingProgress] = useState(false);

  // Weekly report
  const [report, setReport] = useState<WeeklyReport | null>(null);
  const [loadingReport, setLoadingReport] = useState(false);
  const [showReport, setShowReport] = useState(false);

  const abortRef = useRef<AbortController | null>(null);

  const fetchChildren = async () => {
    setLoadingChildren(true);
    try {
      const res = await api.get('/users/parent/children/');
      const list: ChildLink[] = res.data;
      setChildren(list);
      if (list.length > 0 && !selectedId) {
        setSelectedId(list[0].student);
      }
    } catch {
      toast.error('获取孩子列表失败');
    } finally {
      setLoadingChildren(false);
    }
  };

  const fetchProgress = async (childId: number) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const signal = controller.signal;

    setLoadingProgress(true);
    setShowReport(false);
    try {
      const res = await api.get(`/users/parent/children/${childId}/progress/`, { signal });
      if (!signal.aborted) {
        setProgress(res.data);
      }
    } catch (err: any) {
      if (err?.name !== 'CanceledError' && err?.code !== 'ERR_CANCELED') {
        toast.error('获取学习进度失败');
      }
    } finally {
      if (!signal.aborted) {
        setLoadingProgress(false);
      }
    }
  };

  const fetchReport = async (childId: number) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const signal = controller.signal;

    setLoadingReport(true);
    try {
      const res = await api.get(`/users/parent/children/${childId}/weekly-report/`, { signal });
      if (!signal.aborted) {
        setReport(res.data);
        setShowReport(true);
      }
    } catch (err: any) {
      if (err?.name !== 'CanceledError' && err?.code !== 'ERR_CANCELED') {
        toast.error('获取周报失败');
      }
    } finally {
      if (!signal.aborted) {
        setLoadingReport(false);
      }
    }
  };

  const handleBind = async () => {
    if (!studentEmail.trim()) {
      toast.error('请输入学生邮箱');
      return;
    }
    setBinding(true);
    try {
      const res = await api.post('/users/parent/link-request/', { student_email: studentEmail.trim() });
      toast.success(res.data.message);
      setStudentEmail('');
      fetchChildren();
    } catch (e: any) {
      toast.error(e.response?.data?.error || '绑定失败');
    } finally {
      setBinding(false);
    }
  };

  useEffect(() => {
    if (user?.role !== 'parent') {
      navigate('/settings', { replace: true });
      return;
    }
    fetchChildren();
  }, [user]);

  useEffect(() => {
    if (selectedId) {
      fetchProgress(selectedId);
    }
  }, [selectedId]);

  return (
    <PageWrapper title="家长模式" subtitle="实时了解孩子的学习情况">
      <div className="max-w-5xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-8 text-left animate-in fade-in duration-700">
        {/* Left Sidebar — Children list */}
        <div className="lg:col-span-4 space-y-6">
          <Card className="border-none shadow-sm rounded-3xl bg-card p-6 border border-border/30">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-bold text-foreground">我的孩子</h3>
              <span className="text-[10px] font-bold text-muted-foreground bg-muted px-2 py-1 rounded-full">
                {children.length} 位
              </span>
            </div>

            {loadingChildren ? (
              <div className="space-y-3">
                <Skeleton className="h-14 w-full rounded-xl" />
                <Skeleton className="h-14 w-full rounded-xl" />
              </div>
            ) : children.length === 0 ? (
              <p className="text-xs text-muted-foreground text-center py-4">
                尚未绑定任何孩子
              </p>
            ) : (
              <div className="space-y-2">
                {children.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => setSelectedId(c.student)}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-colors text-left ${
                      selectedId === c.student
                        ? 'bg-primary/10 text-primary font-bold'
                        : 'hover:bg-muted text-foreground/80'
                    }`}
                  >
                    <Avatar className="h-8 w-8 shrink-0">
                      <AvatarImage src={null as any} />
                      <AvatarFallback className="text-[11px] font-bold bg-primary/10 text-primary">
                        {c.student_name[0]}
                      </AvatarFallback>
                    </Avatar>
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-bold truncate">{c.student_name}</p>
                      <p className="text-[10px] text-muted-foreground">
                        {c.verified ? '已绑定' : '待验证'}
                      </p>
                    </div>
                    {selectedId === c.student && (
                      <ArrowRight className="h-3.5 w-3.5 shrink-0 text-primary" />
                    )}
                  </button>
                ))}
              </div>
            )}
          </Card>

          {/* Bind new child */}
          <Card className="border-none shadow-sm rounded-3xl bg-card p-6 border border-border/30">
            <h3 className="text-sm font-bold text-foreground mb-4 flex items-center gap-2">
              <Plus className="h-4 w-4" />
              绑定孩子
            </h3>
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label className="text-[10px] font-bold uppercase tracking-widest opacity-40 ml-1">
                  学生邮箱
                </Label>
                <Input
                  value={studentEmail}
                  onChange={(e) => setStudentEmail(e.target.value)}
                  placeholder="输入孩子的注册邮箱"
                  className="bg-muted border-none h-10 rounded-xl text-xs font-bold px-4"
                  autoComplete="email"
                />
              </div>
              <Button
                onClick={handleBind}
                disabled={binding}
                className="w-full h-10 rounded-xl text-xs font-bold"
              >
                {binding ? '发送中...' : '发送绑定验证码'}
              </Button>
              <p className="text-[10px] text-muted-foreground leading-relaxed">
                系统将生成验证码，请让孩子在设置页面的"绑定家长"区域输入该验证码完成绑定。
              </p>
            </div>
          </Card>
        </div>

        {/* Right — Progress / Report */}
        <div className="lg:col-span-8 space-y-6">
          {!selectedId ? (
            <Card className="border-none shadow-sm rounded-3xl bg-card p-12 border border-border/30">
              <div className="text-center space-y-3">
                <User className="h-10 w-10 mx-auto text-muted-foreground/30" />
                <p className="text-sm text-muted-foreground font-bold">
                  请先绑定孩子，或从左侧选择一个已绑定的孩子
                </p>
              </div>
            </Card>
          ) : showReport && report ? (
            /* ── 学习周报 ── */
            <Card className="border-none shadow-sm rounded-3xl bg-card p-8 border border-border/30">
              <div className="flex items-center justify-between mb-6">
                <div>
                  <h3 className="text-lg font-bold text-foreground">学习周报</h3>
                  <p className="text-[11px] text-muted-foreground">
                    {report.week_start} ~ {report.week_end}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-xs font-bold"
                  onClick={() => setShowReport(false)}
                >
                  返回概览
                </Button>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <StatCard icon={BookOpen} label="本周复习" value={`${report.reviews} 次`} color="text-blue-500" />
                <StatCard icon={Trophy} label="正确率" value={`${report.accuracy}%`} color="text-emerald-500" />
                <StatCard icon={Lightning} label="新掌握知识点" value={`${report.new_mastered_kps} 个`} color="text-amber-500" />
                <StatCard icon={CalendarCheck} label="签到天数" value={`${report.checkins} 天`} color="text-violet-500" />
                <StatCard icon={FileText} label="参加考试" value={`${report.exams_taken} 次`} color="text-rose-500" />
                <StatCard icon={Heart} label="学习时长" value={`${report.total_minutes} 分钟`} color="text-cyan-500" />
              </div>
            </Card>
          ) : loadingProgress ? (
            <div className="space-y-4">
              <Skeleton className="h-32 w-full rounded-3xl" />
              <Skeleton className="h-24 w-full rounded-3xl" />
              <Skeleton className="h-24 w-full rounded-3xl" />
            </div>
          ) : progress ? (
            <>
              {/* Health Score Card */}
              <Card className="border-none shadow-sm rounded-3xl bg-card p-8 border border-border/30">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                      学习健康度
                    </p>
                    <div className="flex items-baseline gap-2 mt-1">
                      <span className="text-3xl font-black text-foreground">
                        {progress.health.score}
                      </span>
                      <span className="text-sm text-muted-foreground font-bold">/ 100</span>
                    </div>
                  </div>
                  <Badge
                    className={`text-[11px] px-3 py-1 rounded-full font-bold ${
                      HEALTH_LABELS[progress.health.level]?.color || 'bg-slate-100 text-slate-700'
                    }`}
                  >
                    {HEALTH_LABELS[progress.health.level]?.label || progress.health.level}
                  </Badge>
                </div>
                {/* Health breakdown bars */}
                <div className="mt-5 grid grid-cols-4 gap-3">
                  {progress.health?.components ? Object.entries(progress.health.components).map(([key, value]) => (
                    <div key={key} className="text-center">
                      <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden mb-1.5">
                        <div
                          className="h-full bg-primary rounded-full transition-all"
                          style={{ width: `${Math.round((value / 40) * 100)}%` }}
                        />
                      </div>
                      <p className="text-[9px] font-bold text-muted-foreground uppercase">
                        {key === 'recency' ? '活跃' : key === 'memorix' ? '记忆' : key === 'streak' ? '签到' : '趋势'}
                      </p>
                      <p className="text-[10px] font-bold text-foreground">{value}</p>
                    </div>
                  )) : null}
                </div>
              </Card>

              {/* Stats row */}
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <StatCard
                  icon={BookOpen}
                  label="本周复习"
                  value={`${progress.weekly_reviews} 次`}
                  color="text-blue-500"
                />
                <StatCard
                  icon={Lightning}
                  label="已掌握知识点"
                  value={`${progress.mastered_kp_count} 个`}
                  color="text-amber-500"
                />
                <StatCard
                  icon={CalendarCheck}
                  label="连续签到"
                  value={`${progress.streak} 天`}
                  color="text-violet-500"
                />
              </div>

              {/* Weekly Report Button */}
              <Button
                variant="outline"
                className="w-full h-12 rounded-2xl text-sm font-bold border-border/50 hover:bg-muted"
                onClick={() => fetchReport(selectedId!)}
                disabled={loadingReport}
              >
                <FileText className="mr-2 h-4 w-4" />
                {loadingReport ? '加载中...' : '查看学习周报'}
              </Button>
            </>
          ) : null}
        </div>
      </div>
    </PageWrapper>
  );
};

function StatCard({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  color: string;
}) {
  return (
    <Card className="border-none shadow-sm rounded-2xl bg-card p-5 border border-border/30">
      <div className="flex items-center gap-3">
        <div className={`h-9 w-9 rounded-xl bg-muted flex items-center justify-center ${color}`}>
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">
            {label}
          </p>
          <p className="text-sm font-bold text-foreground mt-0.5">{value}</p>
        </div>
      </div>
    </Card>
  );
}
