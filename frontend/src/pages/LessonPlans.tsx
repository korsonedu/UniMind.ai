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
import { TeachingPlanAnalytics } from '@/components/TeachingPlanAnalytics';
import {
  Plus, Pencil, Trash, CaretDown, CaretRight,
  Spinner, Books, CalendarCheck, Users, FilePdf,
  ChartBar, ArrowSquareOut,
} from '@phosphor-icons/react';
import { toast } from 'sonner';
import { useConfirm } from '@/components/useConfirm';
import { useNavigate } from 'react-router-dom';

/* ── types ── */

interface WeekPlan { week: number; topic: string; objectives: string; kp_ids: number[]; materials: string }
interface WeeklyPlansData {
  id: number; class_obj: number; class_name: string;
  title: string; description: string; subject: string; semester: string;
  week_count: number; weekly_plans: WeekPlan[] | null;
  goal?: string; deadline?: string; target_score?: number; current_level?: string;
}
interface Klass { id: number; name: string }

/* ── helpers ── */

const plannedWeeks = (plan: WeeklyPlansData) =>
  (plan.weekly_plans || []).filter(w => w.topic).length;

/* ══════ page ══════ */

export default function LessonPlans() {
  const [plans, setPlans] = useState<WeeklyPlansData[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [expandedWeeks, setExpandedWeeks] = useState<Set<number>>(new Set());
  const [showAnalytics, setShowAnalytics] = useState(false);

  // external data
  const [classes, setClasses] = useState<Klass[]>([]);
  const [subjects, setSubjects] = useState<string[]>([]);

  // plan dialog
  const [planDialog, setPlanDialog] = useState(false);
  const [editingPlan, setEditingPlan] = useState<WeeklyPlansData | null>(null);
  const [planClassId, setPlanClassId] = useState('');
  const [planSubject, setPlanSubject] = useState('');

  // inline week edit
  const [editingWeek, setEditingWeek] = useState<number | null>(null);
  const [weekForm, setWeekForm] = useState<WeekPlan>({ week: 0, topic: '', objectives: '', kp_ids: [], materials: '' });

  // loading
  const [saving, setSaving] = useState(false);
  const [aiLoading, setAiLoading] = useState('');

  const { confirm, Dialog: ConfirmDialog } = useConfirm();
  const navigate = useNavigate();

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
      goal: fd.get('goal') || '', deadline: fd.get('deadline') || null,
      target_score: fd.get('target_score') ? Number(fd.get('target_score')) : null,
      current_level: fd.get('current_level') || '',
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
      setPlanDialog(false); setEditingPlan(null); setPlanClassId(''); setPlanSubject('');
      setSelectedId(id); setExpandedWeeks(new Set()); setShowAnalytics(false);

      // auto-generate weeks for new plan
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

  const deletePlan = async (plan: WeeklyPlansData) => {
    if (!(await confirm(`删除「${plan.title}」？`))) return;
    await api.delete(`/courses/teaching-plans/${plan.id}/`);
    setPlans(prev => prev.filter(p => p.id !== plan.id));
    if (selectedId === plan.id) setSelectedId(null);
    toast.success('已删除');
  };

  /* ── inline week edit ── */

  const startEditWeek = (wp: WeekPlan) => { setEditingWeek(wp.week); setWeekForm({ ...wp }); setExpandedWeeks(prev => new Set(prev).add(wp.week)); };
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

  /* ── actions ── */

  const downloadPDF = async (planId: number, title: string) => {
    try {
      const res = await api.get(`/courses/teaching-plans/${planId}/pdf/`, { responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `教学计划-${title}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success('PDF 已下载');
    } catch { toast.error('PDF 导出失败'); }
  };

  const goToWorkbench = (planId: number, weekNumber: number) => {
    // navigate to workbench with teaching plan context
    const searchParams = new URLSearchParams({
      teaching_plan_id: String(planId),
      week_number: String(weekNumber),
    });
    navigate(`/workbench?${searchParams.toString()}`);
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
  };

  /* ── stats ── */

  const stats = {
    totalPlans: plans.length,
    totalWeeks: plans.reduce((s, p) => s + (p.weekly_plans || []).length, 0),
    plannedWeeks: plans.reduce((s, p) => s + plannedWeeks(p), 0),
  };

  /* ── render ── */

  if (loading) return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <Spinner className="h-6 w-6 animate-spin text-muted-foreground" />
    </div>
  );

  if (plans.length === 0) {
    return (
      <PageWrapper title="教案管理" subtitle="教学计划与学情追踪">
        <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
          <Books className="w-12 h-12 mb-4 text-muted-foreground/30" />
          <p className="text-sm font-bold">还没有教学计划</p>
          <p className="text-xs mt-1 text-muted-foreground/70">为班级创建教学计划，AI 自动生成周进度，追踪学情</p>
          <Button className="mt-6 gap-1.5" variant="apple" onClick={() => { setEditingPlan(null); setPlanClassId(''); setPlanSubject(''); setPlanDialog(true); }}>
            <Plus className="w-4 h-4" />创建教学计划
          </Button>
        </div>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper title="教案管理" subtitle="教学计划 · 学情追踪 · 联动出题">
      {/* ── stats bar ── */}
      <div className="grid grid-cols-3 gap-3 mb-6">
        <Card>
          <CardHeader className="pb-1"><CardTitle className="text-xs font-medium text-muted-foreground">教学计划</CardTitle></CardHeader>
          <CardContent className="pb-4"><p className="text-2xl font-bold tabular-nums">{stats.totalPlans}</p></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1"><CardTitle className="text-xs font-medium text-muted-foreground">总周数</CardTitle></CardHeader>
          <CardContent className="pb-4"><p className="text-2xl font-bold tabular-nums">{stats.totalWeeks}</p></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1"><CardTitle className="text-xs font-medium text-muted-foreground">已规划周</CardTitle></CardHeader>
          <CardContent className="pb-4"><p className="text-2xl font-bold tabular-nums">{stats.plannedWeeks}</p></CardContent>
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
                onClick={() => { setSelectedId(isSelected ? null : plan.id); setExpandedWeeks(new Set()); setShowAnalytics(false); }}
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
                      <span className="flex items-center gap-1"><Books className="w-3 h-3" />{pw}/{plan.week_count}周已规划</span>
                    </div>
                    {plan.goal && (
                      <p className="text-xs text-muted-foreground/70 mt-1.5 line-clamp-1">目标：{plan.goal}</p>
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
                    <div className="flex items-center gap-2">
                      <Button variant="ghost" size="sm" className="gap-1" onClick={() => downloadPDF(plan.id, plan.title)}>
                        <FilePdf className="w-3.5 h-3.5" />导出 PDF
                      </Button>
                      <Button variant="apple-outline" size="sm" className="gap-1"
                        onClick={ai.weeks} disabled={!!aiLoading}>
                        {aiLoading === `plan-${plan.id}` ? 'AI 分析中…' : '重新生成周计划'}
                      </Button>
                    </div>
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

                          <div className="flex-1 flex items-center gap-2 min-w-0">
                            <span className={`text-sm truncate ${!wp?.topic ? 'text-muted-foreground/50 italic' : 'font-medium'}`}>
                              {wp?.topic || '未设置'}
                            </span>
                            {wp?.materials && <span className="text-[11px] text-muted-foreground truncate hidden sm:inline max-w-[140px]">{wp.materials}</span>}
                            <div className="ml-auto flex items-center gap-1 shrink-0">
                              <Button size="sm" variant="ghost" className="h-7" onClick={e => { e.stopPropagation(); wp ? startEditWeek(wp) : startEditWeek({ week, topic: '', objectives: '', kp_ids: [], materials: '' }); }}>
                                <Pencil className="w-3 h-3" />
                              </Button>
                            </div>
                          </div>
                        </button>

                        {/* expanded week content */}
                        {isExpanded && (
                          <div className="px-4 pb-4 space-y-3 border-t border-border/50 pt-3 animate-in fade-in slide-in-from-top-2 duration-200">
                            {isEditing ? (
                              <div className="space-y-3 bg-background rounded-lg p-4 border border-border/50">
                                <div>
                                  <Label htmlFor={`week-topic-${week}`} className="text-xs">周主题</Label>
                                  <Input id={`week-topic-${week}`} placeholder="如：函数基础" value={weekForm.topic}
                                    onChange={e => setWeekForm({ ...weekForm, topic: e.target.value })} />
                                </div>
                                <div>
                                  <Label htmlFor={`week-obj-${week}`} className="text-xs">教学目标</Label>
                                  <Textarea id={`week-obj-${week}`} rows={2} placeholder="本周学生应掌握的知识和技能" value={weekForm.objectives}
                                    onChange={e => setWeekForm({ ...weekForm, objectives: e.target.value })} />
                                </div>
                                <div>
                                  <Label htmlFor={`week-mat-${week}`} className="text-xs">教学材料</Label>
                                  <Input id={`week-mat-${week}`} placeholder="如：PPT、实验器材、练习题" value={weekForm.materials}
                                    onChange={e => setWeekForm({ ...weekForm, materials: e.target.value })} />
                                </div>
                                <div className="flex items-center gap-2 pt-1">
                                  <Button size="sm" variant="apple" onClick={saveWeekInline}>保存</Button>
                                  <Button size="sm" variant="ghost" onClick={cancelEditWeek}>取消</Button>
                                </div>
                              </div>
                            ) : wp?.topic ? (
                              <div className="text-xs space-y-1 bg-background rounded-lg p-3 border border-border/50">
                                <p><span className="font-bold text-muted-foreground">教学目标：</span>{wp.objectives || '未设置'}</p>
                                <p><span className="font-bold text-muted-foreground">教学材料：</span>{wp.materials || '未设置'}</p>
                              </div>
                            ) : (
                              <p className="text-xs text-muted-foreground/50 italic px-3">未设置周主题，点击编辑按钮开始规划</p>
                            )}

                            {/* action — go to workbench */}
                            <div className="flex items-center gap-2 pt-1">
                              <Button size="sm" variant="outline" className="gap-1"
                                onClick={() => goToWorkbench(plan.id, week)}>
                                <ArrowSquareOut className="w-3.5 h-3.5" />
                                基于本周出题
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
                  <Select value={planSubject} onValueChange={setPlanSubject}>
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

            {/* goal */}
            <div className="space-y-3 pt-1 border-t border-border/50">
              <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">学习目标</p>
              <div>
                <Label htmlFor="pg">目标描述</Label>
                <Textarea id="pg" name="goal" rows={2}
                  defaultValue={editingPlan?.goal || ''}
                  placeholder="如：1年内达到高考数学130分" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label htmlFor="pdl">截止日期</Label>
                  <Input id="pdl" name="deadline" type="date"
                    defaultValue={editingPlan?.deadline || ''} />
                </div>
                <div>
                  <Label htmlFor="pts">目标分数</Label>
                  <Input id="pts" name="target_score" type="number"
                    defaultValue={editingPlan?.target_score || ''} min={0} max={750} />
                </div>
              </div>
              <div>
                <Label htmlFor="pcl">学生当前水平</Label>
                <Input id="pcl" name="current_level"
                  defaultValue={editingPlan?.current_level || ''}
                  placeholder="如：已掌握基础代数，薄弱在函数和解析几何" />
              </div>
            </div>

            {/* scope */}
            <div className="space-y-3 pt-1 border-t border-border/50">
              <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">教学范围</p>
              <div>
                <Label htmlFor="pd">教学描述</Label>
                <Textarea id="pd" name="description" rows={3}
                  defaultValue={editingPlan?.description || ''}
                  placeholder="描述本学期要覆盖的核心内容，AI 会据此生成更精准的周计划。" />
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setPlanDialog(false)}>取消</Button>
              <Button type="submit" variant="apple" disabled={saving || !planClassId || !planSubject} className="gap-1.5">
                {saving ? '保存中…' : editingPlan ? '保存修改' : '创建并生成周计划'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Confirm Dialog */}
      {ConfirmDialog}
    </PageWrapper>
  );
}
