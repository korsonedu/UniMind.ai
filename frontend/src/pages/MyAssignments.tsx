/**
 * 学生端 - 我的作业（重新设计）
 */
import { useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Spinner, Check, Clock, FileText, CaretRight,
  CalendarCheck, Warning, CheckCircle, Hourglass,
} from '@phosphor-icons/react';
import api from '@/lib/api';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { PageWrapper } from '@/components/PageWrapper';
import { Skeleton } from '@/components/ui/skeleton';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

interface AssignmentItem {
  id: number;
  title: string;
  due_date: string | null;
  question_count: number;
  submitted: boolean;
  score: number | null;
  created_at: string;
}

interface QuestionData {
  id: number;
  text: string;
  q_type: string;
  options?: string[] | null;
  difficulty_level: string;
  kp_name: string;
  points: number;
  order: number;
}

type View = 'list' | 'detail';

const isOverdue = (due: string | null) => {
  if (!due) return false;
  return new Date(due) < new Date();
};

const isUrgent = (due: string | null, submitted: boolean) => {
  if (!due || submitted) return false;
  const diff = new Date(due).getTime() - Date.now();
  return diff > 0 && diff < 24 * 60 * 60 * 1000;
};

const daysLeft = (due: string | null) => {
  if (!due) return null;
  const diff = new Date(due).getTime() - Date.now();
  return Math.ceil(diff / (1000 * 60 * 60 * 24));
};

const StatChip = ({
  icon: Icon, label, count, variant = 'default',
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string; count: number;
  variant?: 'default' | 'warning' | 'danger' | 'success';
}) => {
  const colorMap = {
    default: 'bg-muted/60 text-muted-foreground',
    warning: 'bg-amber-50 text-amber-600 dark:bg-amber-950/50 dark:text-amber-400',
    danger: 'bg-red-50 text-red-600 dark:bg-red-950/50 dark:text-red-400',
    success: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-950/50 dark:text-emerald-400',
  };
  return (
    <div className={cn('flex items-center gap-2 px-3 py-2 rounded-xl', colorMap[variant])}>
      <Icon className="h-4 w-4 shrink-0" />
      <span className="text-[11px] font-bold uppercase tracking-wide">{label}</span>
      <span className="text-lg font-black leading-none -mt-0.5">{count}</span>
    </div>
  );
};

const ListSkeleton = () => (
  <div className="space-y-2">
    {Array.from({ length: 4 }).map((_, i) => (
      <div key={i} className="rounded-xl border border-border bg-card p-4 flex items-center gap-3">
        <Skeleton className="h-9 w-9 rounded-lg shrink-0" />
        <div className="flex-1 space-y-1.5">
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-3 w-32" />
        </div>
        <Skeleton className="h-5 w-14 rounded-full" />
      </div>
    ))}
  </div>
);

export default function MyAssignments() {
  const navigate = useNavigate();
  const [view, setView] = useState<View>('list');
  const [assignments, setAssignments] = useState<AssignmentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState<{
    id: number; title: string; due_date: string | null;
    questions: QuestionData[]; submitted: boolean;
    previous_answers: Record<string, string>; score: number | null;
  } | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);

  const fetchList = async () => {
    setLoading(true);
    try {
      const res = await api.get('/assignments/my/');
      setAssignments(res.data || []);
    } catch { toast.error('加载作业列表失败'); }
    setLoading(false);
  };

  useEffect(() => { fetchList(); }, []);

  const openDetail = async (id: number) => {
    setDetailLoading(true); setView('detail');
    try {
      const res = await api.get(`/assignments/${id}/questions/`);
      setDetail(res.data); setAnswers(res.data.previous_answers || {});
    } catch { toast.error('加载作业详情失败'); }
    setDetailLoading(false);
  };

  const handleSubmit = async () => {
    if (!detail) return;
    setSubmitting(true);
    try {
      const res = await api.post('/assignments/submit/', { assignment_id: detail.id, answers });
      toast.success(res.data.message);
      setDetail({ ...detail, submitted: true, score: res.data.score, previous_answers: answers });
      fetchList();
    } catch (e: any) { toast.error(e?.response?.data?.error || '提交失败'); }
    setSubmitting(false);
  };

  const stats = useMemo(() => {
    const pending = assignments.filter(a => !a.submitted && !isOverdue(a.due_date));
    const submitted = assignments.filter(a => a.submitted);
    const overdue = assignments.filter(a => !a.submitted && isOverdue(a.due_date));
    return { pending: pending.length, submitted: submitted.length, overdue: overdue.length };
  }, [assignments]);

  const sortedAssignments = useMemo(() => {
    return [...assignments].sort((a, b) => {
      const scoreA = (a.submitted ? 3 : 0) + (isOverdue(a.due_date) && !a.submitted ? 0 : 0) + (isUrgent(a.due_date, a.submitted) ? 1 : 0);
      const scoreB = (b.submitted ? 3 : 0) + (isOverdue(b.due_date) && !b.submitted ? 0 : 0) + (isUrgent(b.due_date, b.submitted) ? 1 : 0);
      if (scoreA !== scoreB) return scoreA - scoreB;
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });
  }, [assignments]);

  if (view === 'list') {
    return (
      <PageWrapper title="我的作业" subtitle="">
        <div className="max-w-2xl mx-auto space-y-5 animate-in fade-in slide-in-from-bottom-2 duration-300">
          {!loading && assignments.length > 0 && (
            <div className="flex flex-wrap gap-2">
              <StatChip icon={Hourglass} label="待提交" count={stats.pending} variant="default" />
              <StatChip icon={CheckCircle} label="已提交" count={stats.submitted} variant="success" />
              {stats.overdue > 0 && <StatChip icon={Warning} label="已逾期" count={stats.overdue} variant="danger" />}
            </div>
          )}
          {loading ? <ListSkeleton /> : assignments.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
              <div className="h-16 w-16 rounded-2xl bg-muted/40 flex items-center justify-center mb-4">
                <CalendarCheck className="h-8 w-8 text-muted-foreground/30" />
              </div>
              <p className="text-sm font-bold">暂无作业</p>
              <p className="text-xs mt-1 text-muted-foreground/60">老师布置作业后会显示在这里</p>
            </div>
          ) : (
            <div className="space-y-1.5">
              {sortedAssignments.map(a => {
                const urgent = isUrgent(a.due_date, a.submitted);
                const overdue = !a.submitted && isOverdue(a.due_date);
                const left = daysLeft(a.due_date);
                return (
                  <button key={a.id} onClick={() => openDetail(a.id)}
                    className={cn(
                      'w-full flex items-center gap-3 px-4 py-3.5 rounded-xl border transition-all duration-200 text-left',
                      'hover:border-primary/30 hover:shadow-sm hover:-translate-y-px active:scale-[0.99]',
                      a.submitted ? 'border-border bg-card' :
                      overdue ? 'border-red-200 bg-red-50/30 dark:border-red-900/30 dark:bg-red-950/10' :
                      urgent ? 'border-amber-200 bg-amber-50/30 dark:border-amber-900/30 dark:bg-amber-950/10' :
                      'border-border bg-card',
                    )}>
                    <div className={cn(
                      'h-9 w-9 rounded-lg flex items-center justify-center shrink-0',
                      a.submitted ? 'bg-emerald-100 text-emerald-600 dark:bg-emerald-950/50 dark:text-emerald-400' :
                      overdue ? 'bg-red-100 text-red-600 dark:bg-red-950/50 dark:text-red-400' :
                      urgent ? 'bg-amber-100 text-amber-600 dark:bg-amber-950/50 dark:text-amber-400' :
                      'bg-blue-100 text-blue-600 dark:bg-blue-950/50 dark:text-blue-400',
                    )}>
                      {a.submitted ? <Check className="h-4 w-4" /> : overdue ? <Warning className="h-4 w-4" /> : <Clock className="h-4 w-4" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-bold truncate">{a.title}</div>
                      <div className="text-xs text-muted-foreground mt-0.5 flex items-center gap-1.5">
                        <span>{a.question_count} 题</span>
                        {a.due_date && <>
                          <span className="text-muted-foreground/30">·</span>
                          <span className={cn(overdue ? 'text-red-500 font-bold' : urgent ? 'text-amber-500 font-bold' : '')}>
                            截止 {new Date(a.due_date).toLocaleDateString('zh-CN')}
                            {left !== null && !overdue && <span className="ml-1 font-normal">{left <= 0 ? '(今天)' : `(${left}天后)`}</span>}
                          </span>
                        </>}
                        {a.submitted && a.score !== null && <>
                          <span className="text-muted-foreground/30">·</span>
                          <span className="font-bold text-emerald-600 dark:text-emerald-400">得分 {a.score}</span>
                        </>}
                      </div>
                    </div>
                    {a.submitted ? (
                      <span className="text-[10px] font-bold text-emerald-600 bg-emerald-100 dark:bg-emerald-950/50 dark:text-emerald-400 px-2.5 py-0.5 rounded-full shrink-0">已提交</span>
                    ) : overdue ? (
                      <span className="text-[10px] font-bold text-red-600 bg-red-100 dark:bg-red-950/50 dark:text-red-400 px-2.5 py-0.5 rounded-full shrink-0">已逾期</span>
                    ) : (
                      <CaretRight className="h-4 w-4 text-muted-foreground/40 shrink-0" />
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </PageWrapper>
    );
  }

  if (detailLoading || !detail) {
    return (
      <PageWrapper title="作业详情" subtitle="">
        <div className="max-w-2xl mx-auto space-y-4 animate-in fade-in duration-200">
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-32" />
          {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-40 w-full rounded-xl" />)}
        </div>
      </PageWrapper>
    );
  }

  const answeredCount = Object.values(answers).filter(v => v.trim()).length;
  const progressPct = detail.questions.length > 0 ? Math.round((answeredCount / detail.questions.length) * 100) : 0;

  return (
    <PageWrapper title={detail.title} subtitle="">
      <div className="max-w-2xl mx-auto space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
        <div className="flex items-center gap-3">
          <button onClick={() => { setView('list'); fetchList(); }}
            className="p-1.5 -ml-1.5 rounded-lg hover:bg-muted transition-colors text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">{detail.questions.length} 题</span>
              {detail.due_date && <><span className="text-muted-foreground/30 text-xs">·</span>
                <span className={cn('text-xs', isOverdue(detail.due_date) && !detail.submitted ? 'text-red-500 font-bold' : 'text-muted-foreground')}>
                  截止 {new Date(detail.due_date).toLocaleDateString('zh-CN')}
                </span></>}
              {detail.submitted && detail.score !== null && <><span className="text-muted-foreground/30 text-xs">·</span>
                <span className="text-xs font-bold text-emerald-600 dark:text-emerald-400">得分 {detail.score}</span></>}
            </div>
            {!detail.submitted && (
              <div className="mt-2 flex items-center gap-2">
                <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                  <div className="h-full bg-primary rounded-full transition-all duration-500 ease-out" style={{ width: `${progressPct}%` }} />
                </div>
                <span className="text-[11px] font-bold text-muted-foreground shrink-0">{answeredCount}/{detail.questions.length}</span>
              </div>
            )}
          </div>
          {detail.submitted && (
            <span className="text-[10px] font-bold text-emerald-600 bg-emerald-100 dark:bg-emerald-950/50 dark:text-emerald-400 px-2.5 py-0.5 rounded-full shrink-0">已提交</span>
          )}
        </div>

        {detail.submitted ? (
          <div className="space-y-3">
            {detail.questions.map((q, i) => (
              <div key={q.id} className="rounded-xl border border-border bg-card p-4 animate-in fade-in slide-in-from-bottom-1 duration-300" style={{ animationDelay: `${i * 40}ms` }}>
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[11px] font-bold text-muted-foreground">第 {i + 1} 题</span>
                  <span className="text-[10px] text-muted-foreground/50">{q.points} 分</span>
                  {q.kp_name && <span className="text-[10px] text-muted-foreground/40 ml-auto">{q.kp_name}</span>}
                </div>
                <div className="text-sm leading-relaxed prose prose-sm max-w-none dark:prose-invert">
                  <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>{q.text}</ReactMarkdown>
                </div>
                <div className="mt-3 p-3 rounded-lg bg-muted/30 border border-border/50">
                  <span className="text-[11px] font-bold text-muted-foreground">你的答案</span>
                  <p className="text-sm mt-1 leading-relaxed">{detail.previous_answers[String(q.id)] || <span className="text-muted-foreground/40 italic">未作答</span>}</p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="space-y-3">
            {detail.questions.map((q, i) => (
              <div key={q.id} className="rounded-xl border border-border bg-card p-4 animate-in fade-in slide-in-from-bottom-1 duration-300" style={{ animationDelay: `${i * 40}ms` }}>
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[11px] font-bold text-muted-foreground">第 {i + 1} 题</span>
                  <span className="text-[10px] text-muted-foreground/50">{q.points} 分</span>
                  {q.kp_name && <span className="text-[10px] text-muted-foreground/40 ml-auto">{q.kp_name}</span>}
                </div>
                <div className="text-sm leading-relaxed prose prose-sm max-w-none dark:prose-invert mb-3">
                  <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>{q.text}</ReactMarkdown>
                </div>
                {q.q_type === 'objective' && q.options?.length ? (
                  <div className="space-y-1.5">
                    {q.options.map((opt, j) => (
                      <button key={j} onClick={() => setAnswers(prev => ({ ...prev, [String(q.id)]: opt }))}
                        className={cn(
                          'w-full text-left px-3 py-2.5 rounded-lg text-sm border transition-all duration-150',
                          'hover:border-primary/30 active:scale-[0.99]',
                          answers[String(q.id)] === opt ? 'border-primary bg-primary/5 text-primary font-bold shadow-sm' : 'border-border text-foreground/70',
                        )}>
                        <span className="font-bold text-muted-foreground mr-2">{String.fromCharCode(65 + j)}.</span>{opt}
                      </button>
                    ))}
                  </div>
                ) : (
                  <textarea value={answers[String(q.id)] || ''} onChange={e => setAnswers(prev => ({ ...prev, [String(q.id)]: e.target.value }))}
                    placeholder="输入你的答案..." rows={4}
                    className="w-full border border-border rounded-lg px-3 py-2.5 text-sm placeholder:text-muted-foreground/40 focus:outline-none focus:border-primary/40 focus:ring-1 focus:ring-primary/20 resize-none bg-transparent transition-colors" />
                )}
              </div>
            ))}
            <div className="sticky bottom-0 -mx-4 px-4 py-3 bg-background/90 backdrop-blur-xl border-t border-border md:relative md:mx-0 md:px-0 md:py-0 md:bg-transparent md:backdrop-blur-none md:border-0">
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">
                  {answeredCount}/{detail.questions.length} 题已作答
                  {progressPct === 100 && <span className="ml-2 text-emerald-500 font-bold">全部完成</span>}
                </span>
                <Button onClick={handleSubmit} disabled={submitting || answeredCount === 0} size="sm" className="gap-1.5">
                  {submitting ? <><Spinner className="h-3.5 w-3.5 animate-spin" />提交中...</> : <><Check className="h-3.5 w-3.5" />提交作业</>}
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </PageWrapper>
  );
}
