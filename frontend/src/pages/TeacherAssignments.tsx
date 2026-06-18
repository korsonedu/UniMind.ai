/**
 * 教师端 - 作业管理
 */
import { useState, useEffect } from 'react';
import {
  CheckCircle, Spinner, Brain, Users, CalendarCheck,
  CaretDown, CaretRight, GraduationCap, Plus, X,
} from '@phosphor-icons/react';
import api from '@/lib/api';
import { cn } from '@/lib/utils';
import { PageWrapper } from '@/components/PageWrapper';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { toast } from 'sonner';

interface AssignmentItem {
  id: number;
  title: string;
  status: string;
  due_date: string | null;
  question_count: number;
  class_names: string[];
  submitted_count: number;
  graded_count: number;
  total_students: number;
  created_at: string;
}

interface SubmissionItem {
  id: number;
  student_name: string;
  student_id: number;
  submitted_at: string;
  score: number | null;
  graded: boolean;
}

interface QuestionBrief {
  id: number;
  text: string;
  q_type: string;
  difficulty_level: string;
  knowledge_point_detail?: { name: string };
  kp_name?: string;
}

interface ClassBrief {
  id: number;
  name: string;
  student_count: number;
}

export function TeacherAssignments() {
  const [assignments, setAssignments] = useState<AssignmentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [submissions, setSubmissions] = useState<Record<number, SubmissionItem[]>>({});
  const [gradingId, setGradingId] = useState<number | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  const [allQuestions, setAllQuestions] = useState<QuestionBrief[]>([]);
  const [allClasses, setAllClasses] = useState<ClassBrief[]>([]);
  const [selectedQids, setSelectedQids] = useState<Set<number>>(new Set());
  const [selectedCids, setSelectedCids] = useState<Set<number>>(new Set());
  const [formTitle, setFormTitle] = useState('');
  const [formDesc, setFormDesc] = useState('');
  const [formDue, setFormDue] = useState('');
  const [formSaving, setFormSaving] = useState(false);
  const [qSearch, setQSearch] = useState('');

  useEffect(() => {
    api.get('/assignments/teacher/')
      .then(res => setAssignments(res.data || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const openCreate = async () => {
    setCreateOpen(true);
    try {
      const [qRes, cRes] = await Promise.all([
        api.get('/quizzes/questions/?limit=100'),
        api.get('/users/institution/me/classes/'),
      ]);
      setAllQuestions(qRes.data.results || qRes.data || []);
      setAllClasses(cRes.data.results || cRes.data || []);
    } catch {}
  };

  const handleCreate = async () => {
    if (!formTitle.trim() || selectedQids.size === 0) {
      toast.error('请填写标题并选择题目');
      return;
    }
    setFormSaving(true);
    try {
      await api.post('/assignments/create/', {
        title: formTitle.trim(),
        description: formDesc.trim(),
        question_ids: Array.from(selectedQids),
        class_ids: Array.from(selectedCids),
        due_date: formDue ? new Date(formDue).toISOString() : null,
      });
      toast.success('作业已发布');
      setCreateOpen(false);
      const res = await api.get('/assignments/teacher/');
      setAssignments(res.data || []);
      setFormTitle('');
      setFormDue('');
      setSelectedQids(new Set());
      setSelectedCids(new Set());
    } catch { toast.error('创建失败'); }
    setFormSaving(false);
  };

  const loadSubmissions = async (assignmentId: number) => {
    if (submissions[assignmentId]) return;
    try {
      const res = await api.get(`/assignments/${assignmentId}/submissions/`);
      setSubmissions(prev => ({ ...prev, [assignmentId]: res.data.submissions || res.data.results || res.data || [] }));
    } catch {}
  };

  const toggleExpand = (id: number) => {
    if (expandedId === id) { setExpandedId(null); }
    else { setExpandedId(id); loadSubmissions(id); }
  };

  const aiGrade = async (submissionId: number, assignmentId: number) => {
    setGradingId(submissionId);
    try {
      await api.post(`/assignments/submissions/${submissionId}/grade/`, { action: 'ai_grade' });
      toast.success('AI 判分完成');
      const res = await api.get(`/assignments/${assignmentId}/submissions/`);
      setSubmissions(prev => ({ ...prev, [assignmentId]: res.data.submissions || res.data.results || res.data || [] }));
    } catch { toast.error('判分失败'); }
    setGradingId(null);
  };

  if (loading) return <Spinner className="h-8 w-8 animate-spin text-primary mx-auto mt-20" />;

  return (
    <PageWrapper title="作业管理" subtitle="">
      <div className="max-w-6xl mx-auto space-y-4 md:space-y-6">
        <div className="flex items-center justify-end">
          <Button size="sm" className="gap-1.5" onClick={openCreate}>
          <Plus className="h-3.5 w-3.5" />
          布置作业
        </Button>
      </div>

      {assignments.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
          <CalendarCheck className="h-12 w-12 mb-3 opacity-20" />
          <p className="text-sm font-bold">暂无作业</p>
          <p className="text-xs mt-1">点击「布置作业」手动创建，或在工作台对话框中告诉 Agent</p>
        </div>
      ) : (
        <div className="space-y-3">
          {assignments.map(a => {
            const isExpanded = expandedId === a.id;
            const subs = submissions[a.id] || [];
            return (
              <div key={a.id} className="rounded-xl border border-border bg-card overflow-hidden">
                <button onClick={() => toggleExpand(a.id)}
                  className="w-full flex items-center gap-3 px-4 py-3.5 hover:bg-muted/30 transition-colors text-left">
                  <span className={cn(
                    "text-[10px] font-bold px-2 py-0.5 rounded",
                    a.status === 'published' ? 'bg-emerald-100 text-emerald-700' :
                    a.status === 'draft' ? 'bg-muted text-muted-foreground' : 'bg-red-100 text-red-700'
                  )}>
                    {a.status === 'published' ? '已发布' : a.status === 'draft' ? '草稿' : '已关闭'}
                  </span>
                  <span className="text-sm font-bold flex-1 truncate">{a.title}</span>
                  <span className="text-xs text-muted-foreground">
                    <Users className="h-3 w-3 inline mr-1" />{a.submitted_count}/{a.total_students} 提交
                  </span>
                  <span className="text-xs text-muted-foreground">
                    <CheckCircle className="h-3 w-3 inline mr-1" />{a.graded_count}/{a.submitted_count} 批改
                  </span>
                  {isExpanded ? <CaretDown className="h-4 w-4 text-muted-foreground" /> : <CaretRight className="h-4 w-4 text-muted-foreground" />}
                </button>

                <div className="px-4 pb-2 flex gap-4 text-[10px] text-muted-foreground">
                  <span>{a.question_count} 题</span>
                  {a.class_names?.length > 0 && <span>班级：{a.class_names.join('、')}</span>}
                  {a.due_date && <span>截止：{new Date(a.due_date).toLocaleDateString('zh-CN')}</span>}
                </div>

                {isExpanded && (
                  <div className="border-t border-border">
                    {subs.length === 0 ? (
                      <div className="px-4 py-6 text-center text-xs text-muted-foreground">暂无提交</div>
                    ) : (
                      <div className="divide-y divide-border">
                        {subs.map((s: any) => (
                          <div key={s.id} className="flex items-center gap-3 px-4 py-2.5 hover:bg-muted/20 transition-colors">
                            <GraduationCap className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                            <span className="text-xs font-bold flex-1">{s.student_name || `学生 #${s.student_id}`}</span>
                            <span className="text-[10px] text-muted-foreground">
                              {s.submitted_at ? new Date(s.submitted_at).toLocaleDateString('zh-CN') : '-'}
                            </span>
                            {s.graded ? (
                              <span className="text-xs font-bold text-emerald-600">{s.score}分</span>
                            ) : (
                              <Button size="sm" variant="outline" className="h-6 text-[10px] gap-1"
                                disabled={gradingId === s.id} onClick={() => aiGrade(s.id, a.id)}>
                                {gradingId === s.id ? <Spinner className="h-3 w-3 animate-spin" /> : <Brain className="h-3 w-3" />}
                                AI 批改
                              </Button>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Create Assignment Dialog — horizontal two-pane */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-5xl p-0 overflow-hidden" showClose={false}>
          <div className="flex items-center justify-between px-8 pt-6 pb-5">
            <div className="space-y-0.5">
              <DialogTitle className="text-lg font-black tracking-tight">布置作业</DialogTitle>
              <p className="text-xs text-muted-foreground">选择题目和目标班级，一键发布</p>
            </div>
            <button onClick={() => setCreateOpen(false)}
              className="p-2 -mr-2 rounded-xl text-muted-foreground hover:text-foreground hover:bg-muted transition-colors">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="border-t border-border" />
          <div className="grid grid-cols-[340px_1fr] divide-x divide-border">
            {/* Left: config */}
            <div className="space-y-6 p-6">
              <div className="space-y-4">
                <div className="space-y-1.5">
                  <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">
                    作业标题 <span className="text-red-400">*</span>
                  </label>
                  <Input value={formTitle} onChange={e => setFormTitle(e.target.value)} placeholder="第三章课后练习" className="h-9 text-sm" />
                </div>
                <div className="space-y-1.5">
                  <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">描述</label>
                  <Input value={formDesc} onChange={e => setFormDesc(e.target.value)} placeholder="作业要求（可选）" className="h-9 text-sm" />
                </div>
              </div>
              <div className="space-y-4">
                <div className="space-y-1.5">
                  <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">截止日期</label>
                  <Input type="date" value={formDue} onChange={e => setFormDue(e.target.value)} className="h-9 text-sm" />
                </div>
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">目标班级</label>
                    {selectedCids.size > 0 && <span className="text-[10px] font-bold text-primary">{selectedCids.size} 个</span>}
                  </div>
                  {allClasses.length > 0 ? (
                    <div className="space-y-1">
                      {allClasses.map(c => {
                        const active = selectedCids.has(c.id);
                        return (
                          <button key={c.id} onClick={() => { const next = new Set(selectedCids); next.has(c.id) ? next.delete(c.id) : next.add(c.id); setSelectedCids(next); }}
                            className={cn(
                              'w-full flex items-center justify-between px-3 py-2.5 rounded-xl border text-left transition-all duration-150 active:scale-[0.99]',
                              active ? 'border-primary/40 bg-primary/5 text-primary shadow-sm' : 'border-border bg-card text-muted-foreground hover:border-primary/20 hover:text-foreground',
                            )}>
                            <span className="text-xs font-bold truncate">{c.name}</span>
                            <span className={cn('text-[10px] font-bold shrink-0 ml-2', active ? 'text-primary/60' : 'text-muted-foreground/40')}>{c.student_count}人</span>
                          </button>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="rounded-xl border border-dashed border-border bg-muted/20 py-5 text-center">
                      <Users className="h-5 w-5 mx-auto text-muted-foreground/15 mb-1.5" />
                      <p className="text-xs text-muted-foreground">暂无班级</p>
                    </div>
                  )}
                </div>
              </div>
              <div className="space-y-3 pt-2">
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1"><span className="h-1 w-1 rounded-full bg-primary/60" />题目 {selectedQids.size} 道</span>
                  {selectedCids.size > 0 && <span className="flex items-center gap-1"><span className="h-1 w-1 rounded-full bg-amber-400" />班级 {selectedCids.size} 个</span>}
                  {formDue && <span className="flex items-center gap-1"><span className="h-1 w-1 rounded-full bg-emerald-400" />截止 {new Date(formDue).toLocaleDateString('zh-CN')}</span>}
                </div>
                <Button onClick={handleCreate} disabled={formSaving || !formTitle.trim() || selectedQids.size === 0} className="w-full h-10 text-sm font-bold gap-2">
                  {formSaving ? <><Spinner className="h-4 w-4 animate-spin" />发布中…</> : <><CalendarCheck className="h-4 w-4" />发布作业</>}
                </Button>
              </div>
            </div>

            {/* Right: question picker */}
            <div className="flex flex-col min-h-0 bg-muted/10">
              <div className="px-5 py-4 border-b border-border space-y-3">
                <div className="flex items-center justify-between">
                  <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">选择题目</label>
                  <span className={cn('text-xs font-bold transition-colors', selectedQids.size > 0 ? 'text-primary' : 'text-muted-foreground')}>已选 {selectedQids.size} 道</span>
                </div>
                <div className="relative">
                  <Input value={qSearch} onChange={e => setQSearch(e.target.value)} placeholder="搜索题目关键词…" className="h-9 text-sm pl-9" />
                  <svg className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/30 pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                </div>
              </div>
              <div className="flex-1 overflow-y-auto overscroll-contain max-h-[420px]">
                {allQuestions.length > 0 ? (
                  <div className="divide-y divide-border/30">
                    {allQuestions.filter(q => !qSearch || q.text.includes(qSearch)).slice(0, 80).map(q => {
                      const kpName = q.knowledge_point_detail?.name || q.kp_name || '';
                      const diffLabel: Record<string, string> = { entry: '入门', easy: '简单', normal: '适中', hard: '困难', extreme: '极限' };
                      const isSel = selectedQids.has(q.id);
                      const diffColor: Record<string, string> = {
                        entry: 'bg-slate-100 text-slate-600 dark:bg-slate-900/50 dark:text-slate-400',
                        easy: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400',
                        normal: 'bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-400',
                        hard: 'bg-red-100 text-red-700 dark:bg-red-950/50 dark:text-red-400',
                        extreme: 'bg-pink-100 text-pink-700 dark:bg-pink-950/50 dark:text-pink-400',
                      };
                      return (
                        <button key={q.id} onClick={() => { const next = new Set(selectedQids); next.has(q.id) ? next.delete(q.id) : next.add(q.id); setSelectedQids(next); }}
                          className={cn('w-full text-left px-5 py-3.5 transition-colors flex items-start gap-3', isSel ? 'bg-primary/[0.06]' : 'hover:bg-background/60')}>
                          <div className={cn('h-5 w-5 rounded-lg border-2 flex items-center justify-center shrink-0 mt-px transition-all', isSel ? 'bg-primary border-primary' : 'border-muted-foreground/15')}>
                            {isSel && <svg className="h-3 w-3 text-primary-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={4}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="text-[13px] leading-relaxed line-clamp-2 font-medium">{q.text}</div>
                            <div className="flex items-center gap-2 mt-2">
                              <span className={cn('text-[10px] font-bold px-1.5 py-0.5 rounded-md', q.q_type === 'objective' ? 'bg-blue-100 text-blue-700 dark:bg-blue-950/50 dark:text-blue-400' : 'bg-purple-100 text-purple-700 dark:bg-purple-950/50 dark:text-purple-400')}>
                                {q.q_type === 'objective' ? '选择' : '主观'}
                              </span>
                              <span className={cn('text-[10px] font-bold px-1.5 py-0.5 rounded-md', diffColor[q.difficulty_level] || 'text-muted-foreground')}>
                                {diffLabel[q.difficulty_level] || q.difficulty_level}
                              </span>
                              {kpName && <span className="text-[10px] text-muted-foreground/40 truncate ml-auto">{kpName}</span>}
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
                    <Brain className="h-8 w-8 text-muted-foreground/10 mb-3" />
                    <p className="text-sm font-bold">暂无题目</p>
                    <p className="text-xs mt-1 text-muted-foreground/50">请在题库中创建题目</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>
      </div>
    </PageWrapper>
  );
}
