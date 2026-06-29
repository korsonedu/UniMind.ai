import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, Link } from 'react-router-dom';
import { PageWrapper } from '@/components/PageWrapper';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Progress } from '@/components/ui/progress';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { CalendarCheck, ChatCircle, Trash, Clock, ArrowLeft, Plus, Check } from '@phosphor-icons/react';
import api from '@/lib/api';
import { toast } from 'sonner';
import { useConfirm } from '@/components/useConfirm';

interface PlanTask {
  id: string;
  title: string;
  description?: string;
  day: number;
  subject?: string;
  estimated_minutes?: number;
  target_accuracy?: number;
  question_count?: number;
  status: 'pending' | 'completed' | 'skipped';
  completed_at?: string | null;
  action?: string;
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

let taskIdCounter = Date.now();

function newTaskId(): string {
  return `task_${++taskIdCounter}`;
}

export function StudyPlan() {
  const { t } = useTranslation('plan');
  const navigate = useNavigate();
  const [plans, setPlans] = useState<StudyPlan[]>([]);
  const safePlans = Array.isArray(plans) ? plans : [];
  const [selectedPlan, setSelectedPlan] = useState<StudyPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  const [savedFields, setSavedFields] = useState<Record<string, boolean>>({});
  const { confirm, Dialog } = useConfirm();

  useEffect(() => {
    fetchPlans();
  }, []);

  const flashSaved = (fieldKey: string) => {
    setSavedFields(prev => ({ ...prev, [fieldKey]: true }));
    setTimeout(() => {
      setSavedFields(prev => ({ ...prev, [fieldKey]: false }));
    }, 1500);
  };

  const apiErrorMsg = (e: any, fallback: string) => {
    const status = e?.response?.status;
    const detail = e?.response?.data?.detail || e?.response?.data?.error || e?.response?.data?.message;
    if (detail) return detail;
    if (!status || status >= 500) return fallback;
    if (status === 403) return t('error403');
    if (status === 404) return t('error404');
    return fallback;
  };

  const fetchPlans = async () => {
    try {
      const res = await api.get('/ai/plans/');
      const raw = res.data;
      const list: StudyPlan[] = Array.isArray(raw) ? raw : Array.isArray(raw?.results) ? raw.results : [];
      setPlans(list);
      const active = list.find((p: StudyPlan) => p.status === 'active');
      if (active) fetchPlanDetail(active.id);
    } catch (e: any) {
      console.error('fetchPlans failed:', e?.response?.status, e?.response?.data || e?.message);
      toast.error(apiErrorMsg(e, '加载计划失败'));
    } finally {
      setLoading(false);
    }
  };

  const fetchPlanDetail = async (id: number) => {
    try {
      const res = await api.get(`/ai/plans/${id}/`);
      setSelectedPlan(res.data);
    } catch (e: any) {
      console.error('fetchPlanDetail failed:', e?.response?.status, e?.response?.data || e?.message);
      toast.error(apiErrorMsg(e, '加载计划详情失败'));
    }
  };

  // Atomic field update via PATCH
  const updateTaskField = async (taskId: string, field: string, value: any) => {
    if (!selectedPlan) return;
    const fieldKey = `${taskId}_${field}`;
    try {
      const res = await api.patch(`/ai/plans/${selectedPlan.id}/tasks/${taskId}/`, { [field]: value });
      setSelectedPlan(res.data);
      setPlans(prev => (Array.isArray(prev) ? prev : []).map(p => p.id === res.data.id ? { ...p, task_progress: res.data.task_progress, status: res.data.status } : p));
      flashSaved(fieldKey);
    } catch (e: any) {
      console.error('updateTaskField failed:', e?.response?.status, e?.response?.data || e?.message);
      toast.error(apiErrorMsg(e, '更新失败'));
    }
  };

  const deleteTask = async (taskId: string) => {
    if (!selectedPlan) return;
    if (!(await confirm(t('deleteTaskConfirm')))) return;
    try {
      const res = await api.delete(`/ai/plans/${selectedPlan.id}/tasks/${taskId}/`);
      setSelectedPlan(res.data);
      setPlans(prev => (Array.isArray(prev) ? prev : []).map(p => p.id === res.data.id ? { ...p, task_progress: res.data.task_progress, status: res.data.status } : p));
      toast.success('已删除');
    } catch (e: any) {
      console.error('deleteTask failed:', e?.response?.status, e?.response?.data || e?.message);
      toast.error(apiErrorMsg(e, '删除失败'));
    }
  };

  const addTask = async (day: number) => {
    if (!selectedPlan) return;
    const newTask: PlanTask = {
      id: newTaskId(),
      title: t('newTaskDefaultTitle'),
      day,
      status: 'pending',
    };
    const updatedPlanData = {
      ...selectedPlan.plan_data,
      tasks: [...(selectedPlan.plan_data?.tasks || []), newTask],
    };
    try {
      const res = await api.put(`/ai/plans/${selectedPlan.id}/`, {
        plan_data: updatedPlanData,
      });
      setSelectedPlan(res.data);
      setPlans(prev => (Array.isArray(prev) ? prev : []).map(p => p.id === res.data.id ? { ...p, task_progress: res.data.task_progress, status: res.data.status } : p));
      toast.success('任务已添加');
    } catch (e: any) {
      console.error('addTask failed:', e?.response?.status, e?.response?.data || e?.message);
      toast.error(apiErrorMsg(e, '添加失败'));
    }
  };

  const deletePlan = async (id: number) => {
    if (!(await confirm(t('deleteConfirm')))) return;
    try {
      await api.delete(`/ai/plans/${id}/`);
      setPlans(prev => prev.filter(p => p.id !== id));
      if (selectedPlan?.id === id) setSelectedPlan(null);
      toast.success('已删除');
    } catch (e: any) {
      console.error('deletePlan failed:', e?.response?.status, e?.response?.data || e?.message);
      toast.error(apiErrorMsg(e, '删除失败'));
    }
  };

  const progressPct = selectedPlan
    ? (selectedPlan.task_progress?.total ?? 0) > 0
      ? Math.round((selectedPlan.task_progress.completed / selectedPlan.task_progress.total) * 100)
      : 0
    : 0;

  const tasksByDay = (selectedPlan?.plan_data?.tasks || []).reduce<Record<number, PlanTask[]>>((acc, task) => {
    const day = typeof task.day === 'number' && task.day > 0 ? task.day : 1;
    (acc[day] ||= []).push(task);
    return acc;
  }, {});

  const sortedDays = Object.keys(tasksByDay).map(Number).sort((a, b) => a - b);

  // Determine if we need to add a new day at the end (for the "add" button after last day)
  const lastDay = sortedDays.length > 0 ? sortedDays[sortedDays.length - 1] : 0;

  const SavedIndicator = ({ fieldKey }: { fieldKey: string }) => {
    if (!savedFields[fieldKey]) return null;
    return (
      <span className="inline-flex items-center gap-1 text-[10px] text-emerald-600 font-bold animate-in fade-in duration-200">
        <Check className="h-3 w-3" />
        {t('saved')}
      </span>
    );
  };

  if (loading) {
    return <PageWrapper title={t('pageTitle')} subtitle={t('pageSubtitle')}><div className="flex items-center justify-center h-64">加载中...</div></PageWrapper>;
  }

  // Plan detail view
  if (selectedPlan) {
    return (
      <PageWrapper title="" subtitle="">
        <div className="max-w-2xl mx-auto py-8 md:py-12">
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
              <Button variant="outline" size="sm" className="rounded-full" onClick={() => navigate('/xiaoyu')}>
                <ChatCircle className="w-4 h-4 mr-1" />
                {t('viewInChat')}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => deletePlan(selectedPlan.id)}>
                <Trash className="w-4 h-4" />
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
              {(selectedPlan.plan_data?.subjects_covered || []).map(s => (
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
                  {(tasksByDay[day] || []).map(task => (
                    <Card key={task.id} className={`border-border/50 shadow-sm ${task.status === 'completed' ? 'opacity-60' : ''}`}>
                      <CardContent className="p-4 flex items-start gap-3">
                        <Checkbox
                          checked={task.status === 'completed'}
                          onCheckedChange={() => updateTaskField(task.id, 'status', task.status === 'completed' ? 'pending' : 'completed')}
                          className="mt-0.5"
                        />
                        <div className="flex-1 min-w-0 space-y-2">
                          {/* Row 1: Task title (inline editable) + saved indicator */}
                          <div className="flex items-center gap-2">
                            {editingTaskId === task.id ? (
                              <Input
                                autoFocus
                                value={task.title}
                                onChange={e => {
                                  setSelectedPlan(prev => {
                                    if (!prev) return prev;
                                    const newTasks = (prev.plan_data?.tasks || []).map(t =>
                                      t.id === task.id ? { ...t, title: e.target.value } : t
                                    );
                                    return { ...prev, plan_data: { ...prev.plan_data, tasks: newTasks } };
                                  });
                                }}
                                onBlur={() => {
                                  setEditingTaskId(null);
                                  updateTaskField(task.id, 'title', task.title);
                                }}
                                onKeyDown={e => {
                                  if (e.key === 'Enter') {
                                    setEditingTaskId(null);
                                    updateTaskField(task.id, 'title', task.title);
                                  }
                                  if (e.key === 'Escape') setEditingTaskId(null);
                                }}
                                className="h-8 text-sm font-medium rounded-lg"
                              />
                            ) : (
                              <span
                                className={`font-medium text-sm cursor-pointer hover:text-indigo-600 transition-colors ${task.status === 'completed' ? 'line-through text-muted-foreground' : ''}`}
                                onDoubleClick={() => setEditingTaskId(task.id)}
                                title={t('doubleClickToEdit')}
                              >
                                {task.action ? (
                                  <Link to={task.action} className="hover:underline">{task.title}</Link>
                                ) : (
                                  task.title
                                )}
                              </span>
                            )}
                            <SavedIndicator fieldKey={`${task.id}_title`} />
                          </div>

                          {/* Task meta: subject only */}
                          {task.subject && (
                            <Badge variant="secondary" className="text-[10px]">{task.subject}</Badge>
                          )}
                          {task.description && (
                            <p className="text-[12px] text-muted-foreground/60 leading-relaxed">{task.description}</p>
                          )}
                        </div>
                        <div className="flex items-center gap-0.5 shrink-0">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 rounded-lg text-muted-foreground hover:text-red-500"
                            onClick={() => deleteTask(task.id)}
                          >
                            <Trash className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  ))}

                  {/* Add task button for this day */}
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full rounded-xl h-10 text-xs font-bold border-dashed border-border/70 text-muted-foreground hover:text-foreground hover:border-indigo-300"
                    onClick={() => addTask(day)}
                  >
                    <Plus className="h-3.5 w-3.5 mr-1.5" />
                    {t('addTask')}
                  </Button>
                </div>
              </div>
            ))}

            {/* Add task to new day */}
            <div>
              <Button
                variant="outline"
                size="sm"
                className="w-full rounded-xl h-10 text-xs font-bold border-dashed border-border/70 text-muted-foreground hover:text-foreground hover:border-indigo-300"
                onClick={() => addTask(lastDay + 1)}
              >
                <Plus className="h-3.5 w-3.5 mr-1.5" />
                {t('addTask')}（第 {lastDay + 1} 天）
              </Button>
            </div>
          </div>
        </div>
        {Dialog}
      </PageWrapper>
    );
  }

  // Plan list view
  return (
    <PageWrapper title="" subtitle="">
      <div className="max-w-2xl mx-auto py-8 md:py-12">
        {/* Header */}
        <div className="text-center mb-10">
          <h1 className="text-2xl md:text-3xl font-bold tracking-tight mb-2">学习计划</h1>
          <p className="text-muted-foreground">查看和管理你的个性化学习方案</p>
        </div>

        {safePlans.length === 0 ? (
          <div className="text-center py-16">
            <div className="w-16 h-16 rounded-2xl bg-muted flex items-center justify-center mx-auto mb-4">
              <CalendarCheck className="w-8 h-8 text-muted-foreground" />
            </div>
            <h3 className="text-lg font-medium mb-2">{t('emptyTitle')}</h3>
            <p className="text-muted-foreground text-sm mb-5">{t('emptyDesc')}</p>
            <Button onClick={() => navigate('/xiaoyu')} className="rounded-full px-6">
              <ChatCircle className="w-4 h-4 mr-2" />
              {t('chatWithXiaoyu')}
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            {safePlans.map(plan => (
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
                    value={plan.task_progress?.total > 0 ? Math.round((plan.task_progress.completed / plan.task_progress.total) * 100) : 0}
                    className="h-1.5 mb-2"
                  />
                  <p className="text-xs text-muted-foreground">
                    {plan.task_progress?.completed ?? 0}/{plan.task_progress?.total ?? 0} {t('tasks')}
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
      {Dialog}
    </PageWrapper>
  );
}
