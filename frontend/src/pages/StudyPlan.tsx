import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { PageWrapper } from '@/components/PageWrapper';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Progress } from '@/components/ui/progress';
import { Card, CardContent } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { CalendarCheck, MessageCircle, Trash2, Clock, ArrowLeft } from 'lucide-react';
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
  completed_at?: string | null;
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
  auto_generated: boolean;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  task_progress: { total: number; completed: number; skipped: number };
}

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-green-100 text-green-700',
  completed: 'bg-blue-100 text-blue-700',
  archived: 'bg-gray-100 text-gray-500',
};

export function StudyPlan() {
  const { t } = useTranslation('plan');
  const navigate = useNavigate();
  const [plans, setPlans] = useState<StudyPlan[]>([]);
  const [selectedPlan, setSelectedPlan] = useState<StudyPlan | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchPlans();
  }, []);

  const fetchPlans = async () => {
    try {
      const res = await api.get('/ai/plans/');
      const list = res.data.results || res.data;
      setPlans(list);
      const active = list.find((p: StudyPlan) => p.status === 'active');
      if (active) fetchPlanDetail(active.id);
    } catch {
    } finally {
      setLoading(false);
    }
  };

  const fetchPlanDetail = async (id: number) => {
    try {
      const res = await api.get(`/ai/plans/${id}/`);
      setSelectedPlan(res.data);
    } catch {
    }
  };

  const toggleTask = async (taskId: string, currentStatus: string) => {
    if (!selectedPlan) return;
    const newStatus = currentStatus === 'completed' ? 'pending' : 'completed';
    try {
      const res = await api.patch(`/ai/plans/${selectedPlan.id}/tasks/${taskId}/`, { status: newStatus });
      setSelectedPlan(res.data);
      setPlans(prev => prev.map(p => p.id === res.data.id ? { ...p, task_progress: res.data.task_progress, status: res.data.status } : p));
    } catch {
      toast.error('更新失败');
    }
  };

  const deletePlan = async (id: number) => {
    if (!confirm(t('deleteConfirm'))) return;
    try {
      await api.delete(`/ai/plans/${id}/`);
      setPlans(prev => prev.filter(p => p.id !== id));
      if (selectedPlan?.id === id) setSelectedPlan(null);
      toast.success('已删除');
    } catch {
      toast.error('删除失败');
    }
  };

  const progressPct = selectedPlan
    ? selectedPlan.task_progress.total > 0
      ? Math.round((selectedPlan.task_progress.completed / selectedPlan.task_progress.total) * 100)
      : 0
    : 0;

  const tasksByDay = (selectedPlan?.plan_data?.tasks || []).reduce<Record<number, PlanTask[]>>((acc, task) => {
    (acc[task.day] ||= []).push(task);
    return acc;
  }, {});

  const sortedDays = Object.keys(tasksByDay).map(Number).sort((a, b) => a - b);

  if (loading) {
    return <PageWrapper title={t('pageTitle')} subtitle={t('pageSubtitle')}><div className="flex items-center justify-center h-64">加载中...</div></PageWrapper>;
  }

  // Plan detail view
  if (selectedPlan) {
    return (
      <PageWrapper title="" subtitle="">
        <div className="max-w-2xl mx-auto px-4 py-8 md:py-12">
          {/* Back + Actions */}
          <div className="flex items-center justify-between mb-8">
            <button
              onClick={() => setSelectedPlan(null)}
              className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              返回计划列表
            </button>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" className="rounded-full" onClick={() => navigate('/ai')}>
                <MessageCircle className="w-4 h-4 mr-1" />
                {t('viewInChat')}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => deletePlan(selectedPlan.id)}>
                <Trash2 className="w-4 h-4" />
              </Button>
            </div>
          </div>

          {/* Plan Header */}
          <div className="mb-8">
            <h1 className="text-2xl md:text-3xl font-bold tracking-tight mb-2">{selectedPlan.title}</h1>
            {selectedPlan.summary && (
              <p className="text-muted-foreground">{selectedPlan.summary}</p>
            )}
            <div className="flex items-center gap-2 mt-3 flex-wrap">
              <Badge className={`text-xs ${STATUS_COLORS[selectedPlan.status]}`}>
                {selectedPlan.status === 'active' ? t('active') : selectedPlan.status === 'completed' ? t('completed') : t('archived')}
              </Badge>
              {selectedPlan.plan_data.subjects_covered?.map(s => (
                <Badge key={s} variant="outline" className="text-xs">{s}</Badge>
              ))}
            </div>
          </div>

          {/* Progress Card */}
          <Card className="mb-8 border-border/50 shadow-sm">
            <CardContent className="p-5">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-medium">整体进度</span>
                <span className="text-sm text-muted-foreground">
                  {selectedPlan.task_progress.completed} / {selectedPlan.task_progress.total} 已完成
                  {selectedPlan.task_progress.skipped > 0 && ` · ${selectedPlan.task_progress.skipped} 跳过`}
                </span>
              </div>
              <Progress value={progressPct} className="h-2" />
            </CardContent>
          </Card>

          {/* Tasks by Day */}
          <div className="space-y-8">
            {sortedDays.map(day => (
              <div key={day}>
                <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3 flex items-center gap-2">
                  <CalendarCheck className="w-4 h-4" />
                  第 {day} 天
                </h3>
                <div className="space-y-2">
                  {tasksByDay[day].map(task => (
                    <Card key={task.id} className={`border-border/50 shadow-sm ${task.status === 'completed' ? 'opacity-60' : ''}`}>
                      <CardContent className="p-4 flex items-start gap-3">
                        <Checkbox
                          checked={task.status === 'completed'}
                          onCheckedChange={() => toggleTask(task.id, task.status)}
                          className="mt-0.5"
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className={`font-medium text-sm ${task.status === 'completed' ? 'line-through text-muted-foreground' : ''}`}>
                              {task.title}
                            </span>
                            {task.subject && (
                              <Badge variant="secondary" className="text-xs">{task.subject}</Badge>
                            )}
                          </div>
                          {task.description && (
                            <p className="text-sm text-muted-foreground mt-1">{task.description}</p>
                          )}
                          {task.estimated_minutes && (
                            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground mt-1.5">
                              <Clock className="w-3 h-3" />
                              {task.estimated_minutes} 分钟
                            </span>
                          )}
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </PageWrapper>
    );
  }

  // Plan list view
  return (
    <PageWrapper title="" subtitle="">
      <div className="max-w-2xl mx-auto px-4 py-8 md:py-12">
        {/* Header */}
        <div className="text-center mb-10">
          <h1 className="text-2xl md:text-3xl font-bold tracking-tight mb-2">学习计划</h1>
          <p className="text-muted-foreground">查看和管理你的个性化学习方案</p>
        </div>

        {plans.length === 0 ? (
          <div className="text-center py-16">
            <div className="w-16 h-16 rounded-2xl bg-muted flex items-center justify-center mx-auto mb-4">
              <CalendarCheck className="w-8 h-8 text-muted-foreground" />
            </div>
            <h3 className="text-lg font-medium mb-2">{t('emptyTitle')}</h3>
            <p className="text-muted-foreground text-sm mb-5">{t('emptyDesc')}</p>
            <Button onClick={() => navigate('/ai')} className="rounded-full px-6">
              <MessageCircle className="w-4 h-4 mr-2" />
              {t('chatWithXiaoyu')}
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            {plans.map(plan => (
              <Card
                key={plan.id}
                className="cursor-pointer border-border/50 shadow-sm hover:shadow-md transition-all duration-200"
                onClick={() => fetchPlanDetail(plan.id)}
              >
                <CardContent className="p-5">
                  <div className="flex items-start justify-between mb-3">
                    <h3 className="font-semibold">{plan.title}</h3>
                    <Badge className={`text-xs ${STATUS_COLORS[plan.status] || ''}`}>
                      {plan.status === 'active' ? t('active') : plan.status === 'completed' ? t('completed') : t('archived')}
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground mb-3">
                    {new Date(plan.created_at).toLocaleDateString()}
                  </p>
                  <Progress
                    value={plan.task_progress.total > 0 ? Math.round((plan.task_progress.completed / plan.task_progress.total) * 100) : 0}
                    className="h-1.5 mb-2"
                  />
                  <p className="text-xs text-muted-foreground">
                    {plan.task_progress.completed}/{plan.task_progress.total} {t('tasks')}
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </PageWrapper>
  );
}
