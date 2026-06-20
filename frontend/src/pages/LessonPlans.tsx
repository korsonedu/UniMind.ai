import { useState, useEffect, useCallback } from 'react';
import api from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { PageWrapper } from '@/components/PageWrapper';
import {
  Plus, Pencil, Trash, Sparkle, CaretDown, CaretRight,
  Spinner, Books, CheckCircle, CalendarCheck, Users, Clock, Lightning, ChartBar,
} from '@phosphor-icons/react';
import { toast } from 'sonner';
import { TeachingPlanAnalytics } from '@/components/TeachingPlanAnalytics';

/* ── types ── */

interface Activity { name: string; duration: number; description: string }
interface LessonPlan {
  id: number; teaching_plan: number | null; title: string;
  objectives: string; knowledge_point_names: string[];
  activities: Activity[] | null; materials: string[] | null;
  ai_generated: { generated_at: string; content: string; model: string } | null;
  duration_minutes: number; week_number: number | null; order: number;
}
interface WeekPlan { week: number; topic: string; objectives: string; kp_ids: number[]; materials: string }
interface TeachingPlan {
  id: number; class_obj: number; class_name: string;
  title: string; description: string; subject: string; semester: string;
  week_count: number; weekly_plans: WeekPlan[] | null; lesson_plans: LessonPlan[];
}
interface Klass { id: number; name: string }
interface KP { id: number; name: string }

/* ── helpers ── */

const EMPTY_ACTIVITY: Activity = { name: '', duration: 5, description: '' };
const weekLessons = (plan: TeachingPlan, w: number) =>
  (plan.lesson_plans || []).filter(l => l.week_number === w).sort((a, b) => a.order - b.order);
const plannedWeeks = (plan: TeachingPlan) =>
  (plan.weekly_plans || []).filter(w => w.topic).length;

/* ══════ page ══════ */

export default function LessonPlans() {
  const [plans, setPlans] = useState<TeachingPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [expandedWeeks, setExpandedWeeks] = useState<Set<number>>(new Set());
  const [showAnalytics, setShowAnalytics] = useState(false);

  // external data
  const [classes, setClasses] = useState<Klass[]>([]);
  const [subjects, setSubjects] = useState<string[]>([]);
  const [kps, setKps] = useState<KP[]>([]);
  const [selectedKPs, setSelectedKPs] = useState<number[]>([]);

  // plan dialog
  const [planDialog, setPlanDialog] = useState(false);
  const [editingPlan, setEditingPlan] = useState<TeachingPlan | null>(null);
  const [planClassId, setPlanClassId] = useState('');
  const [planSubject, setPlanSubject] = useState('');

  // lesson dialog
  const [lessonDialog, setLessonDialog] = useState(false);
  const [editingLesson, setEditingLesson] = useState<LessonPlan | null>(null);
  const [targetWeek, setTargetWeek] = useState<number | null>(null);

  // inline week edit
  const [editingWeek, setEditingWeek] = useState<number | null>(null);
  const [weekForm, setWeekForm] = useState<WeekPlan>({ week: 0, topic: '', objectives: '', kp_ids: [], materials: '' });

  // loading
  const [saving, setSaving] = useState(false);
  const [aiLoading, setAiLoading] = useState('');

  const selectedPlan = plans.find(p => p.id === selectedId) || null;

  /* ── data fetching ── */

  const fetchPlans = useCallback(async () => {
    try { const { data } = await api.get('/courses/teaching-plans/'); setPlans(data); }
    catch { toast.error('加载失败'); }
    finally { setLoading(false); }
  }, []);

  const fetchMeta = useCallback(async () => {
    try {
      const [cls, subj] = await Promise.all([
        api.get('/users/institution/me/classes/'),
        api.get('/quizzes/knowledge-points/subjects/'),
      ]);
      setClasses(cls.data);
      setSubjects(subj.data.subjects || []);
    } catch { /* non-critical */ }
  }, []);

  useEffect(() => { fetchPlans(); fetchMeta(); }, [fetchPlans, fetchMeta]);

  const fetchKPs = useCallback(async (subject: string) => {
    if (!subject) { setKps([]); setSelectedKPs([]); return; }
    try {
      const { data } = await api.get('/quizzes/knowledge-points/', { params: { subject, page_size: 200 } });
      setKps(data.results || data);
    } catch { setKps([]); }
  }, []);

  const refreshPlan = useCallback(async (id: number) => {
    try { const { data } = await api.get(`/courses/teaching-plans/${id}/`); setPlans(prev => prev.map(p => p.id === data.id ? data : p)); }
    catch { /* ignore */ }
  }, []);

  /* ── plan CRUD ── */

  const savePlan = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault(); setSaving(true);
    const fd = new FormData(e.currentTarget);
    const payload: Record<string, unknown> = {
      class_obj: Number(planClassId), title: fd.get('title'),
      subject: planSubject, semester: fd.get('semester'),
      description: fd.get('description'), week_count: Number(fd.get('week_count')) || 18,
    };
    try {
      let id: number;
      if (editingPlan) {
        const { data } = await api.put(`/courses/teaching-plans/${editingPlan.id}/`, payload);
        setPlans(prev => prev.map(p => p.id === data.id ? data : p)); id = data.id;
        toast.success('已更新');
      } else {
        const { data } = await api.post('/courses/teaching-plans/', payload);
        setPlans(prev => [data, ...prev]); id = data.id;
        toast.success('计划已创建');
      }
      setPlanDialog(false); setEditingPlan(null); setPlanClassId(''); setPlanSubject(''); setSelectedKPs([]);
      setSelectedId(id); setExpandedWeeks(new Set());

      // auto-generate weeks
      if (!editingPlan) {
        setAiLoading(`plan-${id}`);
        try {
          await api.post(`/courses/teaching-plans/${id}/ai-generate-weeks/`);
          refreshPlan(id);
          toast.success('AI 已生成周计划，请查看调整');
        } catch { /* user can trigger manually */ }
        finally { setAiLoading(''); }
      }
    } catch { toast.error('保存失败'); }
    finally { setSaving(false); }
  };

  const deletePlan = async (plan: TeachingPlan) => {
    if (!confirm(`删除「${plan.title}」及所有教案？`)) return;
    await api.delete(`/courses/teaching-plans/${plan.id}/`);
    setPlans(prev => prev.filter(p => p.id !== plan.id));
    if (selectedId === plan.id) setSelectedId(null);
    toast.success('已删除');
  };

  /* ── lesson CRUD ── */

  const saveLesson = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault(); setSaving(true);
    const fd = new FormData(e.currentTarget);
    const payload = {
      teaching_plan: selectedId, title: fd.get('title') as string,
      objectives: fd.get('objectives') as string,
      duration_minutes: Number(fd.get('duration_minutes')) || 45,
      week_number: targetWeek, order: Number(fd.get('order')) || 0,
    };
    try {
      if (editingLesson) { await api.put(`/courses/lesson-plans/${editingLesson.id}/`, payload); }
      else { await api.post('/courses/lesson-plans/', payload); }
      setLessonDialog(false); setEditingLesson(null); setTargetWeek(null);
      if (selectedId) refreshPlan(selectedId);
      toast.success(editingLesson ? '已更新' : '已创建');
    } catch { toast.error('保存失败'); }
    finally { setSaving(false); }
  };

  const deleteLesson = async (l: LessonPlan) => {
    if (!confirm(`删除「${l.title}」？`)) return;
    await api.delete(`/courses/lesson-plans/${l.id}/`);
    if (selectedId) refreshPlan(selectedId);
    toast.success('已删除');
  };

  /* ── inline week edit ── */

  const startEditWeek = (wp: WeekPlan) => { setEditingWeek(wp.week); setWeekForm({ ...wp }); };
  const cancelEditWeek = () => setEditingWeek(null);

  const saveWeekInline = async () => {
    if (!selectedPlan) return;
    const existing = selectedPlan.weekly_plans || [];
    const updated = [...existing.filter(w => w.week !== weekForm.week), weekForm]
      .sort((a, b) => a.week - b.week);
    await api.put(`/courses/teaching-plans/${selectedPlan.id}/`, { weekly_plans: updated });
    setEditingWeek(null); refreshPlan(selectedPlan.id);
    toast.success('已保存');
  };

  /* ── AI actions ── */

  const ai = {
    weeks: async () => {
      if (!selectedPlan) return;
      setAiLoading(`plan-${selectedPlan.id}`);
      try { await api.post(`/courses/teaching-plans/${selectedPlan.id}/ai-generate-weeks/`); refreshPlan(selectedPlan.id); toast.success('周计划已生成'); }
      catch { toast.error('AI 生成失败'); }
      finally { setAiLoading(''); }
    },
    weekLessons: async (week: number) => {
      if (!selectedPlan) return;
      setAiLoading(`week-${selectedPlan.id}-${week}`);
      try { await api.post(`/courses/teaching-plans/${selectedPlan.id}/ai-generate-lessons/`, { week_number: week }); refreshPlan(selectedPlan.id); setExpandedWeeks(prev => new Set(prev).add(week)); toast.success(`第${week}周教案已生成`); }
      catch { toast.error('AI 生成失败'); }
      finally { setAiLoading(''); }
    },
    lesson: async (l: LessonPlan) => {
      setAiLoading(`lesson-${l.id}`);
      try { await api.post('/courses/lesson-plans/ai-generate/', { lesson_plan_id: l.id }); if (selectedId) refreshPlan(selectedId); toast.success('教案内容已生成'); }
      catch { toast.error('AI 生成失败'); }
      finally { setAiLoading(''); }
    },
  };

  /* ── stats ── */

  const stats = {
    totalPlans: plans.length,
    totalLessons: plans.reduce((s, p) => s + (p.lesson_plans || []).length, 0),
    plannedWeeks: plans.reduce((s, p) => s + plannedWeeks(p), 0),
    aiGenerated: plans.reduce((s, p) => s + (p.lesson_plans || []).filter(l => l.ai_generated).length, 0),
  };

  /* ── render ── */

  if (loading) return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <Spinner className="h-6 w-6 animate-spin text-muted-foreground" />
    </div>
  );

  if (plans.length === 0) {
    return (
      <PageWrapper title="教案管理" subtitle="AI 驱动的教学计划与教案协同编辑">
        <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
          <Books className="w-12 h-12 mb-4 text-muted-foreground/30" />
          <p className="text-sm font-bold">还没有教学计划</p>
          <p className="text-xs mt-1 text-muted-foreground/70">为班级创建教学计划，AI 自动生成周进度和教案</p>
          <Button className="mt-6 gap-1.5" variant="apple" onClick={() => { setEditingPlan(null); setPlanClassId(''); setPlanSubject(''); setPlanDialog(true); }}>
            <Plus className="w-4 h-4" />创建教学计划
          </Button>
        </div>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper title="教案管理" subtitle="AI 生成 · 手动精修 · 协同编辑">
      {/* ── stats bar ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Card>
          <CardHeader className="pb-1"><CardTitle className="text-xs font-medium text-muted-foreground">教学计划</CardTitle></CardHeader>
          <CardContent className="pb-4"><p className="text-2xl font-bold tabular-nums">{stats.totalPlans}</p></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1"><CardTitle className="text-xs font-medium text-muted-foreground">总课时</CardTitle></CardHeader>
          <CardContent className="pb-4"><p className="text-2xl font-bold tabular-nums">{stats.totalLessons}</p></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1"><CardTitle className="text-xs font-medium text-muted-foreground">已规划周</CardTitle></CardHeader>
          <CardContent className="pb-4"><p className="text-2xl font-bold tabular-nums">{stats.plannedWeeks}</p></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1"><CardTitle className="text-xs font-medium text-muted-foreground">AI 教案</CardTitle></CardHeader>
          <CardContent className="pb-4"><p className="text-2xl font-bold tabular-nums">{stats.aiGenerated}</p></CardContent>
        </Card>
      </div>

      {/* ── action bar ── */}
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-muted-foreground">
          {selectedPlan ? `正在查看「${selectedPlan.title}」，点击其他计划切换` : '点击计划查看详情'}
        </p>
        <Button size="sm" className="gap-1.5" variant="apple" onClick={() => { setEditingPlan(null); setPlanClassId(''); setPlanSubject(''); setPlanDialog(true); }}>
          <Plus className="w-4 h-4" />新建计划
        </Button>
      </div>

      {/* ── plan list ── */}
      <div className="space-y-3">
        {plans.map(plan => {
          const isSelected = selectedId === plan.id;
          const pw = plannedWeeks(plan);
          return (
            <div key={plan.id}>
              <Card
                variant={isSelected ? 'apple' : 'outlined'}
                className={`cursor-pointer transition-colors ${isSelected ? 'ring-2 ring-primary/20' : 'hover:border-primary/30'}`}
                onClick={() => { setSelectedId(isSelected ? null : plan.id); setExpandedWeeks(new Set()); }}
              >
                <div className="p-4 flex items-center justify-between">
                  <div className="min-w-0 mr-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="font-semibold text-sm">{plan.title}</h3>
                      <Badge variant="secondary" className="text-[10px]">{plan.subject}</Badge>
                      <Badge variant="outline" className="text-[10px]">{plan.semester}</Badge>
                      <Badge variant="outline" className="text-[10px]"><Users className="w-3 h-3 mr-0.5" />{plan.class_name}</Badge>
                    </div>
                    <div className="flex items-center gap-3 mt-2 text-[11px] text-muted-foreground">
                      <span className="flex items-center gap-1"><CalendarCheck className="w-3 h-3" />{plan.week_count}周</span>
                      <span className="flex items-center gap-1"><Books className="w-3 h-3" />{(plan.lesson_plans || []).length}课时</span>
                      <span className="flex items-center gap-1"><CheckCircle className="w-3 h-3" />{pw}/{plan.week_count}周已规划</span>
                      {pw > 0 && (
                        <span className="flex items-center gap-1 text-emerald-600">
                          <Sparkle className="w-3 h-3" />
                          {(plan.lesson_plans || []).filter(l => l.ai_generated).length}节AI
                        </span>
                      )}
                    </div>
                    {plan.description && (
                      <p className="text-xs text-muted-foreground/70 mt-1.5 line-clamp-1">{plan.description}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-0.5 shrink-0" onClick={e => e.stopPropagation()}>
                    <Button size="sm" variant="ghost" onClick={() => { setEditingPlan(plan); setPlanClassId(String(plan.class_obj)); setPlanSubject(plan.subject); setPlanDialog(true); }}>
                      <Pencil className="w-4 h-4" />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => deletePlan(plan)}>
                      <Trash className="w-4 h-4 text-destructive" />
                    </Button>
                  </div>
                </div>
              </Card>

              {/* ── expanded detail ── */}
              {isSelected && (
                <div className="mt-3 ml-2 pl-3 border-l-2 border-primary/20 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-bold tracking-tight">{plan.title}</h3>
                      <Badge variant="secondary" className="text-[10px]">{plan.subject}</Badge>
                    </div>
                    <Button variant="apple-outline" size="sm" className="gap-1"
                      onClick={ai.weeks} disabled={!!aiLoading}>
                      <Sparkle className={`w-3.5 h-3.5 ${aiLoading === `plan-${plan.id}` ? 'animate-spin' : ''}`} />
                      {aiLoading === `plan-${plan.id}` ? 'AI 正在分析学期内容…' : plan.weekly_plans?.length ? '重新生成周计划' : 'AI 生成整学期周计划'}
                    </Button>
                  </div>

                  {/* analytics toggle */}
                  <Button variant="ghost" size="sm" className="gap-1"
                    onClick={() => setShowAnalytics(!showAnalytics)}>
                    <ChartBar className="w-3.5 h-3.5" />
                    {showAnalytics ? '收起学情分析' : '学情分析'}
                  </Button>
                  {showAnalytics && <TeachingPlanAnalytics planId={plan.id} />}

                  {/* weeks */}
                  {Array.from({ length: plan.week_count }, (_, i) => i + 1).map(week => {
                    const wp = plan.weekly_plans?.find(w => w.week === week);
                    const lessons = weekLessons(plan, week);
                    const isExpanded = expandedWeeks.has(week);
                    const isEditing = editingWeek === week;

                    return (
                      <Card key={week} variant="flat" className="overflow-hidden">
                        {/* week header */}
                        <button type="button"
                          className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-muted/40 transition-colors"
                          onClick={() => setExpandedWeeks(prev => { const n = new Set(prev); n.has(week) ? n.delete(week) : n.add(week); return n; })}>
                          {isExpanded ? <CaretDown className="w-4 h-4 shrink-0 text-muted-foreground" /> : <CaretRight className="w-4 h-4 shrink-0 text-muted-foreground" />}
                          <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground w-16 shrink-0">第 {week} 周</span>

                          {isEditing ? (
                            <div className="flex-1 flex items-center gap-2" onClick={e => e.stopPropagation()}>
                              <Input className="h-7 text-xs flex-1" placeholder="主题" value={weekForm.topic}
                                onChange={e => setWeekForm({ ...weekForm, topic: e.target.value })} />
                              <Input className="h-7 text-xs flex-1" placeholder="教学目标"
                                value={weekForm.objectives} onChange={e => setWeekForm({ ...weekForm, objectives: e.target.value })} />
                              <Input className="h-7 text-xs w-32" placeholder="材料"
                                value={weekForm.materials} onChange={e => setWeekForm({ ...weekForm, materials: e.target.value })} />
                              <Button size="sm" variant="apple" className="h-7 text-[10px]" onClick={saveWeekInline}>保存</Button>
                              <Button size="sm" variant="ghost" className="h-7 text-[10px]" onClick={cancelEditWeek}>取消</Button>
                            </div>
                          ) : (
                            <div className="flex-1 flex items-center gap-2 min-w-0">
                              <span className={`text-sm truncate ${!wp?.topic ? 'text-muted-foreground/50 italic' : 'font-medium'}`}>
                                {wp?.topic || '未设置'}
                              </span>
                              {wp?.materials && <span className="text-[11px] text-muted-foreground truncate hidden sm:inline max-w-[140px]">{wp.materials}</span>}
                              <div className="ml-auto flex items-center gap-1 shrink-0">
                                {lessons.length > 0 && <Badge variant="secondary" className="text-[10px]">{lessons.length}课时</Badge>}
                                <Button size="sm" variant="ghost" className="h-7" onClick={e => { e.stopPropagation(); wp ? startEditWeek(wp) : startEditWeek({ week, topic: '', objectives: '', kp_ids: [], materials: '' }); }}>
                                  <Pencil className="w-3 h-3" />
                                </Button>
                              </div>
                            </div>
                          )}
                        </button>

                        {/* expanded week content */}
                        {isExpanded && (
                          <div className="px-4 pb-4 space-y-3 border-t border-border/50 pt-3 animate-in fade-in slide-in-from-top-2 duration-200">
                            {!isEditing && wp?.topic && (
                              <div className="text-xs space-y-1 bg-background rounded-lg p-3 border border-border/50">
                                <p><span className="font-bold text-muted-foreground">教学目标：</span>{wp.objectives || '未设置'}</p>
                                <p><span className="font-bold text-muted-foreground">教学材料：</span>{wp.materials || '未设置'}</p>
                              </div>
                            )}

                            {/* lessons */}
                            {lessons.map(lesson => (
                              <div key={lesson.id} className="flex items-start gap-3 p-3 rounded-lg border border-border/50 bg-background hover:border-primary/20 transition-colors">
                                <div className="min-w-0 flex-1">
                                  <div className="flex items-center gap-2">
                                    <span className="font-medium text-sm">{lesson.title}</span>
                                    <span className="text-[10px] text-muted-foreground"><Clock className="w-3 h-3 inline mr-0.5" />{lesson.duration_minutes}′</span>
                                    {lesson.ai_generated && (
                                      <Badge className="text-[10px] bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400">AI 已生成</Badge>
                                    )}
                                  </div>
                                  {lesson.objectives && (
                                    <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{lesson.objectives}</p>
                                  )}
                                  {lesson.activities && lesson.activities.length > 0 && (
                                    <div className="mt-2 space-y-0.5">
                                      {lesson.activities.map((a, i) => (
                                        <div key={i} className="text-[11px] flex gap-2">
                                          <Badge variant="secondary" className="text-[10px] shrink-0 h-4">{a.duration}′</Badge>
                                          <span className="font-medium shrink-0">{a.name}</span>
                                          <span className="text-muted-foreground truncate">{a.description}</span>
                                        </div>
                                      ))}
                                    </div>
                                  )}
                                  {lesson.materials && lesson.materials.length > 0 && (
                                    <div className="flex gap-1 mt-2 flex-wrap">
                                      {lesson.materials.map((m, i) => <Badge key={i} variant="outline" className="text-[10px]">{m}</Badge>)}
                                    </div>
                                  )}
                                </div>
                                <div className="flex items-center gap-0.5 shrink-0">
                                  <Button size="sm" variant="ghost" disabled={!!aiLoading}
                                    onClick={() => ai.lesson(lesson)} title="AI 生成详细内容">
                                    <Lightning className={`w-3.5 h-3.5 ${aiLoading === `lesson-${lesson.id}` ? 'animate-pulse text-amber-500' : ''}`} />
                                  </Button>
                                  <Button size="sm" variant="ghost" onClick={() => { setEditingLesson(lesson); setTargetWeek(week); setLessonDialog(true); }}>
                                    <Pencil className="w-3.5 h-3.5" />
                                  </Button>
                                  <Button size="sm" variant="ghost" onClick={() => deleteLesson(lesson)}>
                                    <Trash className="w-3.5 h-3.5 text-destructive" />
                                  </Button>
                                </div>
                              </div>
                            ))}

                            <div className="flex items-center gap-2 pt-1">
                              <Button size="sm" variant="outline" className="gap-1"
                                onClick={() => { setEditingLesson(null); setTargetWeek(week); setLessonDialog(true); }}>
                                <Plus className="w-3.5 h-3.5" />添加教案
                              </Button>
                              <Button size="sm" variant="ghost" className="gap-1"
                                disabled={aiLoading === `week-${plan.id}-${week}`}
                                onClick={() => ai.weekLessons(week)}>
                                <Sparkle className={`w-3.5 h-3.5 ${aiLoading === `week-${plan.id}-${week}` ? 'animate-spin' : ''}`} />
                                生成本周教案
                              </Button>
                            </div>
                          </div>
                        )}
                      </Card>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* ══════ Plan Dialog ══════ */}
      <Dialog open={planDialog} onOpenChange={setPlanDialog}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{editingPlan ? '编辑教学计划' : '新建教学计划'}</DialogTitle>
            <DialogDescription>设置基本信息，AI 将据此生成整学期周计划</DialogDescription>
          </DialogHeader>
          <form onSubmit={savePlan} className="space-y-5">
            {/* basic info */}
            <div className="space-y-3">
              <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">基本信息</p>
              <div>
                <Label htmlFor="pt">计划名称 *</Label>
                <Input id="pt" name="title" required defaultValue={editingPlan?.title || ''}
                  placeholder={planSubject ? `${planSubject}教学计划` : '输入计划名称'} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label htmlFor="pc">班级 *</Label>
                  <Select value={planClassId} onValueChange={setPlanClassId}>
                    <SelectTrigger id="pc"><SelectValue placeholder="选择班级" /></SelectTrigger>
                    <SelectContent>
                      {classes.map(c => <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label htmlFor="pw">教学周数</Label>
                  <Input id="pw" name="week_count" type="number" defaultValue={editingPlan?.week_count || 18} min={1} max={30} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label htmlFor="ps">学科 *</Label>
                  <Select value={planSubject} onValueChange={v => { setPlanSubject(v); fetchKPs(v); }}>
                    <SelectTrigger id="ps"><SelectValue placeholder="选择学科" /></SelectTrigger>
                    <SelectContent>
                      {subjects.map(s => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label htmlFor="pm">学期</Label>
                  <Input id="pm" name="semester" required defaultValue={editingPlan?.semester || '2026-春季'} />
                </div>
              </div>
            </div>

            {/* scope */}
            <div className="space-y-3 pt-1 border-t border-border/50">
              <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">教学范围</p>
              <div>
                <Label htmlFor="pd">教学描述</Label>
                <Textarea id="pd" name="description" rows={3}
                  defaultValue={editingPlan?.description || ''}
                  placeholder="描述本学期要覆盖的核心内容和教学目标。AI 会据此生成更精准的周计划。" />
              </div>
              {kps.length > 0 && (
                <div>
                  <Label className="text-xs text-muted-foreground">知识点覆盖（可选，勾选后 AI 重点关注）</Label>
                <p className="text-[10px] text-muted-foreground/60 mb-1.5">勾选本学期重点覆盖的知识点，AI 生成时会优先安排</p>
                <div className="flex flex-wrap gap-1 max-h-28 overflow-y-auto border border-border rounded-lg p-2">
                  {kps.map(kp => (
                    <Badge key={kp.id}
                      variant={selectedKPs.includes(kp.id) ? 'default' : 'outline'}
                      className="cursor-pointer text-[10px] select-none"
                      onClick={() => setSelectedKPs(prev => prev.includes(kp.id) ? prev.filter(id => id !== kp.id) : [...prev, kp.id])}>
                      {kp.name}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setPlanDialog(false)}>取消</Button>
              <Button type="submit" variant="apple" disabled={saving || !planClassId || !planSubject} className="gap-1.5">
                <Sparkle className="w-4 h-4" />
                {saving ? '保存中…' : editingPlan ? '保存修改' : '创建并生成周计划'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* ══════ Lesson Dialog ══════ */}
      <Dialog open={lessonDialog} onOpenChange={setLessonDialog}>
        <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingLesson ? '编辑教案' : '新建教案'}</DialogTitle>
            <DialogDescription>
              {targetWeek ? `第${targetWeek}周` : ''}{selectedPlan ? ` · ${selectedPlan.title}` : ''}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={saveLesson} className="space-y-4">
            <div>
              <Label htmlFor="lt">课题 *</Label>
              <Input id="lt" name="title" required defaultValue={editingLesson?.title || ''} placeholder="如：货币的时间价值" />
            </div>
            <div>
              <Label htmlFor="lo">教学目标</Label>
              <Textarea id="lo" name="objectives" rows={2} defaultValue={editingLesson?.objectives || ''} placeholder="学生能够理解并掌握…" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label htmlFor="ld">课时(分钟)</Label><Input id="ld" name="duration_minutes" type="number" defaultValue={editingLesson?.duration_minutes || 45} min={5} max={180} /></div>
              <div><Label htmlFor="lr">排序</Label><Input id="lr" name="order" type="number" defaultValue={editingLesson?.order || 0} min={0} /></div>
            </div>

            {editingLesson && (
              <>
                <div className="space-y-3 pt-2 border-t">
                  <div className="flex items-center justify-between">
                    <Label className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">教学活动</Label>
                    <Button type="button" size="sm" variant="ghost"
                      onClick={async () => {
                        const updated = [...(editingLesson.activities || []), { ...EMPTY_ACTIVITY }];
                        await api.put(`/courses/lesson-plans/${editingLesson.id}/`, { activities: updated });
                        if (selectedId) refreshPlan(selectedId);
                      }}><Plus className="w-3 h-3 mr-1" />添加环节</Button>
                  </div>
                  {(editingLesson.activities || []).map((a, i) => (
                    <div key={i} className="grid grid-cols-12 gap-1.5 items-start bg-muted/20 p-2 rounded-lg">
                      <Input className="col-span-3 h-7 text-[11px]" placeholder="环节" value={a.name}
                        onChange={e => { const acts = [...(editingLesson.activities || [])]; acts[i] = { ...acts[i], name: e.target.value }; setEditingLesson({ ...editingLesson, activities: acts }); }} />
                      <Input className="col-span-2 h-7 text-[11px]" type="number" placeholder="分钟" value={a.duration}
                        onChange={e => { const acts = [...(editingLesson.activities || [])]; acts[i] = { ...acts[i], duration: Number(e.target.value) || 0 }; setEditingLesson({ ...editingLesson, activities: acts }); }} />
                      <Input className="col-span-5 h-7 text-[11px]" placeholder="内容" value={a.description}
                        onChange={e => { const acts = [...(editingLesson.activities || [])]; acts[i] = { ...acts[i], description: e.target.value }; setEditingLesson({ ...editingLesson, activities: acts }); }} />
                      <Button type="button" variant="ghost" size="icon" className="col-span-2 h-7 w-7"
                        onClick={async () => {
                          const acts = (editingLesson.activities || []).filter((_, j) => j !== i);
                          await api.put(`/courses/lesson-plans/${editingLesson.id}/`, { activities: acts.length > 0 ? acts : null });
                          if (selectedId) refreshPlan(selectedId);
                        }}><Trash className="w-3 h-3 text-destructive" /></Button>
                    </div>
                  ))}
                  {editingLesson.activities && editingLesson.activities.length > 0 && (
                    <Button type="button" size="sm" variant="outline"
                      onClick={async () => {
                        await api.put(`/courses/lesson-plans/${editingLesson.id}/`, { activities: editingLesson.activities });
                        if (selectedId) refreshPlan(selectedId); toast.success('活动已保存');
                      }}>保存活动</Button>
                  )}
                </div>
                <div>
                  <Label className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">教学材料</Label>
                  <Input placeholder="逗号分隔，如：PPT, 视频, 实验器材"
                    defaultValue={(editingLesson.materials || []).join(', ')}
                    onBlur={async e => {
                      const arr = e.target.value.split(',').map(s => s.trim()).filter(Boolean);
                      await api.put(`/courses/lesson-plans/${editingLesson.id}/`, { materials: arr.length > 0 ? arr : null });
                      if (selectedId) refreshPlan(selectedId);
                    }} />
                </div>
                {editingLesson.ai_generated && (
                  <div className="bg-purple-50 dark:bg-purple-950/30 rounded-lg p-3 max-h-40 overflow-y-auto border border-purple-200/50">
                    <p className="text-[10px] font-bold text-purple-700 dark:text-purple-400 mb-1">AI 生成内容</p>
                    <p className="text-[11px] whitespace-pre-wrap text-purple-900/70 dark:text-purple-300/70">{editingLesson.ai_generated.content.slice(0, 800)}</p>
                  </div>
                )}
              </>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setLessonDialog(false)}>取消</Button>
              <Button type="submit" variant="apple" disabled={saving}>{saving ? '保存中…' : '保存'}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </PageWrapper>
  );
}
