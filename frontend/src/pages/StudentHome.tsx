import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { PageWrapper } from '@/components/PageWrapper';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { CalendarCheck, ChatCircle, BookOpen, FileText, Trophy, Brain, ArrowRight, CheckCircle, Clock, Fire, Target, Lightning } from '@phosphor-icons/react';
import api from '@/lib/api';
import { toast } from 'sonner';

interface PlanTask {
  id: string;
  title: string;
  description?: string;
  day: number;
  subject?: string;
  estimated_minutes?: number;
  status: 'pending' | 'completed' | 'skipped';
}

interface StudyPlan {
  id: number;
  title: string;
  summary: string;
  status: string;
  plan_data: {
    tasks: PlanTask[];
    total_days?: number;
    subjects_covered?: string[];
  };
  task_progress: { total: number; completed: number; skipped: number };
}

interface DashboardStats {
  checkin_streak: number;
  total_attempted: number;
  correct_count: number;
  accuracy: number;
  mastered_count: number;
  study_streak: number;
}

export function StudentHome() {
  const navigate = useNavigate();
  const [activePlan, setActivePlan] = useState<StudyPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<DashboardStats | null>(null);

  useEffect(() => {
    api.get('/ai/plans/').catch(() => ({ data: { results: [] } })).then((res: any) => {
      const plans = res.data.results || res.data;
      const active = plans.find((p: StudyPlan) => p.status === 'active');
      if (active) {
        api.get(`/ai/plans/${active.id}/`).then(r => setActivePlan(r.data)).catch(() => {});
      }
    }).finally(() => setLoading(false));

    // Fetch learning stats
    api.get('/users/me/report-card/').then((r: any) => {
      setStats(r.data?.stats || null);
    }).catch(() => {});
  }, []);

  const todayTasks = activePlan
    ? (activePlan.plan_data?.tasks || []).filter(t => t.status === 'pending').slice(0, 5)
    : [];

  const quickLinks = [
    { label: '刷题训练', icon: Trophy, path: '/tests', color: 'text-orange-500', bg: 'bg-orange-50' },
    { label: '知识地图', icon: Brain, path: '/knowledge-map', color: 'text-purple-500', bg: 'bg-purple-50' },
    { label: '课程中心', icon: BookOpen, path: '/courses', color: 'text-blue-500', bg: 'bg-blue-50' },
    { label: '模拟考试', icon: FileText, path: '/mock-exam', color: 'text-red-500', bg: 'bg-red-50' },
  ];

  const toggleTask = async (taskId: string) => {
    if (!activePlan) return;
    try {
      const res = await api.patch(`/ai/plans/${activePlan.id}/tasks/${taskId}/`, { status: 'completed' });
      setActivePlan(res.data);
    } catch { toast.error('更新失败'); }
  };

  if (loading) {
    return <PageWrapper title="" subtitle=""><div /></PageWrapper>;
  }

  return (
    <PageWrapper title="" subtitle="">
      <div className="max-w-2xl mx-auto px-4 py-12 md:py-16">
        {/* Greeting */}
        <div className="text-center mb-10">
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight mb-3">
            今天学点什么？
          </h1>
          <p className="text-muted-foreground text-base md:text-lg">
            小宇已经为你准备好了学习计划
          </p>
        </div>

        {/* Central Prompt Area */}
        <div
          className="relative mb-10 cursor-pointer group"
          onClick={() => navigate('/xiaoyu')}
        >
          <div className="flex items-center gap-4 px-6 py-5 rounded-2xl border bg-card shadow-sm hover:shadow-md transition-all duration-200">
            <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
              <ChatCircle className="w-5 h-5 text-primary" />
            </div>
            <span className="text-muted-foreground text-base flex-1">和小宇聊聊你的学习目标...</span>
            <ArrowRight className="w-5 h-5 text-muted-foreground group-hover:text-primary group-hover:translate-x-0.5 transition-all" />
          </div>
        </div>

        {/* Quick Links — Pill Buttons */}
        <div className="flex flex-wrap justify-center gap-3 mb-12">
          {quickLinks.map(link => (
            <button
              key={link.path}
              onClick={() => navigate(link.path)}
              className={`inline-flex items-center gap-2 px-5 py-2.5 rounded-full border bg-card hover:shadow-sm transition-all duration-200 text-sm font-medium`}
            >
              <div className={`w-7 h-7 rounded-lg ${link.bg} flex items-center justify-center`}>
                <link.icon className={`w-4 h-4 ${link.color}`} />
              </div>
              {link.label}
            </button>
          ))}
        </div>

        {/* Stats Cards */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-10">
            <Card className="border-border/50">
              <CardContent className="p-4 flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-orange-50 flex items-center justify-center shrink-0">
                  <Fire className="w-5 h-5 text-orange-500" />
                </div>
                <div>
                  <p className="text-lg font-bold tabular-nums">{stats.checkin_streak}</p>
                  <p className="text-xs text-muted-foreground">连续打卡</p>
                </div>
              </CardContent>
            </Card>
            <Card className="border-border/50">
              <CardContent className="p-4 flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-blue-50 flex items-center justify-center shrink-0">
                  <Lightning className="w-5 h-5 text-blue-500" />
                </div>
                <div>
                  <p className="text-lg font-bold tabular-nums">{stats.total_attempted}</p>
                  <p className="text-xs text-muted-foreground">已练题目</p>
                </div>
              </CardContent>
            </Card>
            <Card className="border-border/50">
              <CardContent className="p-4 flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-green-50 flex items-center justify-center shrink-0">
                  <Target className="w-5 h-5 text-green-500" />
                </div>
                <div>
                  <p className="text-lg font-bold tabular-nums">{stats.accuracy != null ? `${Math.round(stats.accuracy)}%` : '—'}</p>
                  <p className="text-xs text-muted-foreground">正确率</p>
                </div>
              </CardContent>
            </Card>
            <Card className="border-border/50">
              <CardContent className="p-4 flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-purple-50 flex items-center justify-center shrink-0">
                  <Brain className="w-5 h-5 text-purple-500" />
                </div>
                <div>
                  <p className="text-lg font-bold tabular-nums">{stats.mastered_count}</p>
                  <p className="text-xs text-muted-foreground">已掌握</p>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Today's Tasks */}
        {todayTasks.length > 0 && (
          <div className="mb-10">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">今日任务</h2>
              <button
                className="text-sm text-primary font-medium hover:underline"
                onClick={() => navigate('/plan')}
              >
                查看全部
              </button>
            </div>
            <div className="space-y-3">
              {todayTasks.map(task => (
                <Card key={task.id} className="border-border/50 shadow-sm">
                  <CardContent className="p-4 flex items-center gap-3">
                    <Checkbox
                      checked={task.status === 'completed'}
                      onCheckedChange={() => toggleTask(task.id)}
                    />
                    <div className="flex-1 min-w-0">
                      <span className="font-medium text-sm">{task.title}</span>
                      {task.subject && (
                        <Badge variant="secondary" className="ml-2 text-xs">{task.subject}</Badge>
                      )}
                    </div>
                    {task.estimated_minutes && (
                      <span className="text-xs text-muted-foreground flex items-center gap-1 shrink-0">
                        <Clock className="w-3 h-3" /> {task.estimated_minutes}分钟
                      </span>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        )}

        {/* No plan state */}
        {!activePlan && (
          <div className="text-center py-10">
            <div className="w-16 h-16 rounded-2xl bg-muted flex items-center justify-center mx-auto mb-4">
              <CalendarCheck className="w-8 h-8 text-muted-foreground" />
            </div>
            <h3 className="text-lg font-medium mb-2">还没有学习计划</h3>
            <p className="text-muted-foreground text-sm mb-5">去和小宇聊聊，让它为你制定一份个性化学习方案</p>
            <Button onClick={() => navigate('/xiaoyu')} className="rounded-full px-6">
              <ChatCircle className="w-4 h-4 mr-2" />
              和小宇聊聊
            </Button>
          </div>
        )}

        {/* All tasks done */}
        {activePlan && todayTasks.length === 0 && (
          <div className="text-center py-10">
            <div className="w-16 h-16 rounded-2xl bg-green-50 flex items-center justify-center mx-auto mb-4">
              <CheckCircle className="w-8 h-8 text-green-500" />
            </div>
            <h3 className="text-lg font-medium mb-1">今日任务已完成</h3>
            <p className="text-muted-foreground text-sm">干得漂亮！继续保持</p>
          </div>
        )}
      </div>
    </PageWrapper>
  );
}
