/**
 * 学生端 - 我的作业
 */
import { useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Spinner, Check, Clock, FileText, CaretRight, CaretDown,
  CalendarCheck, Warning, CheckCircle, Hourglass,
} from '@phosphor-icons/react';
import api from '@/lib/api';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { PageWrapper } from '@/components/PageWrapper';
import { Skeleton } from '@/components/ui/skeleton';
import { MarkdownContent } from '@/components/MarkdownContent';

interface AssignmentItem {
  id: number;
  title: string;
  due_date: string | null;
  question_count: number;
  submitted: boolean;
  score: number | null;
  pending_count: number | null;
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
  score?: number;
  max_score?: number;
  is_correct?: boolean;
  feedback?: string;
  analysis?: string;
  correct_answer?: string;
  graded?: boolean;
  user_answer?: string;
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

const StatItem = ({
  value, label, variant = 'default',
}: {
  value: number;
  label: string;
  variant?: 'default' | 'warning' | 'danger' | 'success';
}) => {
  const colorMap = {
    default: 'text-foreground',
    warning: 'text-amber-600 dark:text-amber-400',
    danger: 'text-red-600 dark:text-red-400',
    success: 'text-emerald-600 dark:text-emerald-400',
  };
  return (
    <div className="flex flex-col items-center px-5 py-3">
      <span className={cn('text-2xl font-bold tabular-nums leading-none', colorMap[variant])}>
        {value}
      </span>
      <span className="text-xs text-muted-foreground mt-1.5">{label}</span>
    </div>
  );
};

const ListSkeleton = () => (
  <div className="space-y-2">
    {Array.from({ length: 4 }).map((_, i) => (
      <div key={i} className="rounded-xl border border-border/60 bg-card p-4 flex items-center gap-3">
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
    pending_count: number | null;
  } | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [expandedCards, setExpandedCards] = useState<Set<number>>(new Set());

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
      const qrMap = new Map((res.data.question_results || []).map((r: any) => [r.question_id, r]));
      const updatedQuestions = detail.questions.map(q => {
        const qr: any = qrMap.get(q.id);
        if (qr) {
          return {
            ...q,
            score: qr.score,
            max_score: qr.max_score,
            is_correct: qr.is_correct,
            feedback: qr.feedback,
            analysis: qr.analysis,
            correct_answer: qr.correct_answer,
            graded: qr.graded,
            user_answer: qr.user_answer,
          };
        }
        return q;
      });
      setDetail({
        ...detail,
        submitted: true,
        score: res.data.score,
        pending_count: res.data.pending_count,
        previous_answers: answers,
        questions: updatedQuestions,
      });
      fetchList();
    } catch (e: any) { toast.error(e?.response?.data?.error || '提交失败'); }
    setSubmitting(false);
  };

  const toggleCard = (id: number) => {
    setExpandedCards(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
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

  // ── List View ──
  if (view === 'list') {
    return (
      <PageWrapper title="我的作业" subtitle="">
        <div className="max-w-2xl mx-auto space-y-6">
          {/* Stats summary */}
          {!loading && assignments.length > 0 && (
            <div className="flex items-center justify-center divide-x divide-border/60 rounded-2xl border border-border/60 bg-card py-1">
              <StatItem value={stats.pending} label="待提交" variant={stats.pending > 0 ? 'default' : 'default'} />
              <StatItem value={stats.submitted} label="已提交" variant="success" />
              <StatItem value={stats.overdue} label="已逾期" variant={stats.overdue > 0 ? 'danger' : 'default'} />
            </div>
          )}

          {loading ? (
            <ListSkeleton />
          ) : assignments.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24 text-muted-foreground">
              <div className="h-16 w-16 rounded-2xl bg-muted/30 flex items-center justify-center mb-5">
                <CalendarCheck className="h-8 w-8 text-muted-foreground/25" weight="duotone" />
              </div>
              <p className="text-sm font-semibold">暂无作业</p>
              <p className="text-xs mt-1.5 text-muted-foreground/50">老师布置作业后会显示在这里</p>
            </div>
          ) : (
            <div className="space-y-2">
              {sortedAssignments.map(a => {
                const urgent = isUrgent(a.due_date, a.submitted);
                const overdue = !a.submitted && isOverdue(a.due_date);
                const left = daysLeft(a.due_date);

                const statusConfig = a.submitted
                  ? { accent: 'border-emerald-400/60', iconBg: 'bg-emerald-50 dark:bg-emerald-950/30', iconColor: 'text-emerald-600 dark:text-emerald-400', Icon: Check, badge: '已提交', badgeClass: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-950/40 dark:text-emerald-400' }
                  : overdue
                  ? { accent: 'border-red-400/60', iconBg: 'bg-red-50 dark:bg-red-950/30', iconColor: 'text-red-600 dark:text-red-400', Icon: Warning, badge: '已逾期', badgeClass: 'bg-red-50 text-red-600 dark:bg-red-950/40 dark:text-red-400' }
                  : urgent
                  ? { accent: 'border-amber-400/60', iconBg: 'bg-amber-50 dark:bg-amber-950/30', iconColor: 'text-amber-600 dark:text-amber-400', Icon: Clock, badge: null, badgeClass: '' }
                  : { accent: 'border-blue-400/60', iconBg: 'bg-blue-50 dark:bg-blue-950/30', iconColor: 'text-blue-600 dark:text-blue-400', Icon: Clock, badge: null, badgeClass: '' };

                return (
                  <button
                    key={a.id}
                    onClick={() => openDetail(a.id)}
                    className={cn(
                      'w-full flex items-center gap-3.5 px-4 py-3.5 rounded-xl border transition-all duration-200 text-left',
                      'hover:shadow-sm hover:-translate-y-px active:translate-y-0 active:scale-[0.995]',
                      'border-border/60 bg-card',
                      statusConfig.accent.replace('border-', 'border-l-2 '),
                    )}
                  >
                    <div className={cn('h-9 w-9 rounded-lg flex items-center justify-center shrink-0', statusConfig.iconBg)}>
                      <statusConfig.Icon className={cn('h-4 w-4', statusConfig.iconColor)} weight="fill" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-semibold truncate">{a.title}</div>
                      <div className="text-xs text-muted-foreground mt-0.5 flex items-center gap-1.5">
                        <span>{a.question_count} 题</span>
                        {a.due_date && (
                          <>
                            <span className="text-border">|</span>
                            <span className={cn(overdue ? 'text-red-500 font-semibold' : urgent ? 'text-amber-500 font-semibold' : '')}>
                              截止 {new Date(a.due_date).toLocaleDateString('zh-CN')}
                              {left !== null && !overdue && (
                                <span className="ml-1 font-normal text-muted-foreground">
                                  {left <= 0 ? '(今天)' : `(${left}天后)`}
                                </span>
                              )}
                            </span>
                          </>
                        )}
                        {a.submitted && a.score !== null && a.pending_count ? (
                          <>
                            <span className="text-border">|</span>
                            <span className="font-semibold text-amber-600 dark:text-amber-400">部分批改</span>
                          </>
                        ) : a.submitted && a.score !== null && (
                          <>
                            <span className="text-border">|</span>
                            <span className="font-semibold text-emerald-600 dark:text-emerald-400">得分 {a.score}</span>
                          </>
                        )}
                      </div>
                    </div>
                    {a.submitted ? (
                      <span className={cn('text-[11px] font-semibold px-2.5 py-0.5 rounded-full shrink-0', statusConfig.badgeClass)}>
                        {statusConfig.badge}
                      </span>
                    ) : overdue ? (
                      <span className={cn('text-[11px] font-semibold px-2.5 py-0.5 rounded-full shrink-0', statusConfig.badgeClass)}>
                        {statusConfig.badge}
                      </span>
                    ) : (
                      <CaretRight className="h-4 w-4 text-muted-foreground/30 shrink-0" />
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

  // ── Detail Loading ──
  if (detailLoading || !detail) {
    return (
      <PageWrapper title="作业详情" subtitle="">
        <div className="max-w-2xl mx-auto space-y-4">
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-32" />
          {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-40 w-full rounded-xl" />)}
        </div>
      </PageWrapper>
    );
  }

  const answeredCount = Object.values(answers).filter(v => v.trim()).length;
  const progressPct = detail.questions.length > 0 ? Math.round((answeredCount / detail.questions.length) * 100) : 0;

  // ── Detail View ──
  return (
    <PageWrapper title={detail.title} subtitle="">
      <div className="max-w-2xl mx-auto space-y-5">
        {/* Header */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => { setView('list'); fetchList(); }}
            className="p-1.5 -ml-1.5 rounded-lg hover:bg-muted/60 transition-colors text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>{detail.questions.length} 题</span>
              {detail.due_date && (
                <>
                  <span className="text-border">|</span>
                  <span className={cn(isOverdue(detail.due_date) && !detail.submitted ? 'text-red-500 font-semibold' : '')}>
                    截止 {new Date(detail.due_date).toLocaleDateString('zh-CN')}
                  </span>
                </>
              )}
              {detail.submitted && detail.score !== null && (
                <>
                  <span className="text-border">|</span>
                  <span className="font-semibold text-emerald-600 dark:text-emerald-400">得分 {detail.score}</span>
                </>
              )}
            </div>
            {!detail.submitted && (
              <div className="mt-2.5 flex items-center gap-2.5">
                <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary rounded-full transition-all duration-500 ease-out"
                    style={{ width: `${progressPct}%` }}
                  />
                </div>
                <span className="text-xs font-semibold text-muted-foreground shrink-0 tabular-nums">
                  {answeredCount}/{detail.questions.length}
                </span>
              </div>
            )}
          </div>
          {detail.submitted && (
            <span className="text-[11px] font-semibold text-emerald-600 bg-emerald-50 dark:bg-emerald-950/40 dark:text-emerald-400 px-2.5 py-1 rounded-full shrink-0">
              已提交
            </span>
          )}
        </div>

        {/* Submitted: graded results */}
        {detail.submitted ? (
          <div className="space-y-3">
            {detail.pending_count != null && detail.pending_count > 0 && (
              <div className="rounded-xl border border-amber-200/60 bg-amber-50/40 dark:border-amber-800/30 dark:bg-amber-950/20 p-4 flex items-start gap-3">
                <Hourglass className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" weight="fill" />
                <div>
                  <p className="text-sm font-semibold text-amber-700 dark:text-amber-400">等待老师批改</p>
                  <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                    还有 {detail.pending_count} 道主观题待老师批改，批改完成后你将看到完整结果
                  </p>
                </div>
              </div>
            )}

            {detail.questions.map((q, i) => {
              const userAnswer = q.user_answer || detail.previous_answers[String(q.id)];
              const hasGrading = q.graded !== false && q.score !== undefined;
              const isPending = q.graded === false;
              const expanded = expandedCards.has(q.id);

              return (
                <div key={q.id} className="rounded-xl border border-border/60 bg-card overflow-hidden">
                  <button
                    onClick={() => toggleCard(q.id)}
                    className="w-full flex items-center gap-2.5 p-4 text-left hover:bg-muted/30 transition-colors"
                  >
                    <span className="text-xs font-semibold text-muted-foreground shrink-0">第 {i + 1} 题</span>
                    {hasGrading && (
                      <span className={cn(
                        'text-[11px] font-semibold px-2 py-0.5 rounded-md shrink-0',
                        q.is_correct
                          ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-950/40 dark:text-emerald-400'
                          : 'bg-red-50 text-red-600 dark:bg-red-950/40 dark:text-red-400',
                      )}>
                        {q.score}/{q.max_score} 分
                      </span>
                    )}
                    {isPending && (
                      <span className="text-[11px] font-semibold px-2 py-0.5 rounded-md shrink-0 bg-amber-50 text-amber-600 dark:bg-amber-950/40 dark:text-amber-400">
                        待批改
                      </span>
                    )}
                    <span className="text-xs text-muted-foreground/40">{q.points} 分</span>
                    {q.kp_name && (
                      <span className="text-xs text-muted-foreground/40 ml-auto mr-2">{q.kp_name}</span>
                    )}
                    <CaretDown className={cn(
                      'h-4 w-4 text-muted-foreground/25 shrink-0 transition-transform duration-200',
                      expanded && 'rotate-180',
                    )} />
                  </button>

                  {expanded && (
                    <div className="px-4 pb-4 space-y-3 border-t border-border/40 pt-3">
                      <div className="text-sm leading-relaxed prose prose-sm max-w-none dark:prose-invert">
                        <MarkdownContent content={q.text} />
                      </div>

                      {/* User answer */}
                      <div className="p-3.5 rounded-lg bg-muted/40">
                        <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">你的答案</span>
                        <p className="text-sm mt-1.5 leading-relaxed">
                          {userAnswer || <span className="text-muted-foreground/35 italic">未作答</span>}
                        </p>
                      </div>

                      {/* Pending grading */}
                      {isPending && (
                        <div className="rounded-lg bg-amber-50/60 dark:bg-amber-950/25 border border-amber-200/40 dark:border-amber-800/20 p-3.5 text-center">
                          <Hourglass className="h-5 w-5 mx-auto text-amber-400 mb-1.5" weight="fill" />
                          <p className="text-xs text-amber-600 dark:text-amber-400 font-medium">等待老师批改</p>
                        </div>
                      )}

                      {/* Correct answer */}
                      {q.correct_answer && (
                        <div className="p-3.5 rounded-lg bg-emerald-50/60 dark:bg-emerald-950/25 border border-emerald-200/40 dark:border-emerald-800/20">
                          <span className="text-[11px] font-semibold text-emerald-600 dark:text-emerald-400 uppercase tracking-wide">参考答案</span>
                          <div className="text-sm mt-1.5 leading-relaxed prose prose-sm max-w-none dark:prose-invert">
                            <MarkdownContent content={q.correct_answer} />
                          </div>
                        </div>
                      )}

                      {/* AI feedback */}
                      {q.feedback && (
                        <div className="p-3.5 rounded-lg bg-blue-50/60 dark:bg-blue-950/25 border border-blue-200/40 dark:border-blue-800/20">
                          <span className="text-[11px] font-semibold text-blue-600 dark:text-blue-400 uppercase tracking-wide">AI 批改反馈</span>
                          <div className="text-sm mt-1.5 leading-relaxed prose prose-sm max-w-none dark:prose-invert">
                            <MarkdownContent content={q.feedback} />
                          </div>
                        </div>
                      )}

                      {/* Analysis */}
                      {q.analysis && (
                        <div className="p-3.5 rounded-lg bg-amber-50/60 dark:bg-amber-950/25 border border-amber-200/40 dark:border-amber-800/20">
                          <span className="text-[11px] font-semibold text-amber-600 dark:text-amber-400 uppercase tracking-wide">详细分析</span>
                          <div className="text-sm mt-1.5 leading-relaxed prose prose-sm max-w-none dark:prose-invert">
                            <MarkdownContent content={q.analysis} />
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          /* Unsubmitted: answer input view */
          <div className="space-y-3">
            {detail.questions.map((q, i) => (
              <div key={q.id} className="rounded-xl border border-border/60 bg-card p-4">
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-xs font-semibold text-muted-foreground">第 {i + 1} 题</span>
                  <span className="text-xs text-muted-foreground/40">{q.points} 分</span>
                  {q.kp_name && (
                    <span className="text-xs text-muted-foreground/35 ml-auto">{q.kp_name}</span>
                  )}
                </div>
                <div className="text-sm leading-relaxed prose prose-sm max-w-none dark:prose-invert mb-3.5">
                  <MarkdownContent content={q.text} />
                </div>

                {q.q_type === 'objective' && q.options?.length ? (
                  <div className="space-y-1.5">
                    {q.options.map((opt, j) => (
                      <button
                        key={j}
                        onClick={() => setAnswers(prev => ({ ...prev, [String(q.id)]: opt }))}
                        className={cn(
                          'w-full text-left px-3.5 py-2.5 rounded-lg text-sm border transition-all duration-150',
                          'hover:border-primary/30 active:scale-[0.995]',
                          answers[String(q.id)] === opt
                            ? 'border-primary/50 bg-primary/5 text-primary font-semibold'
                            : 'border-border/60 text-foreground/70 hover:bg-muted/30',
                        )}
                      >
                        <span className="font-semibold text-muted-foreground mr-2">{String.fromCharCode(65 + j)}.</span>
                        {opt}
                      </button>
                    ))}
                  </div>
                ) : (
                  <textarea
                    value={answers[String(q.id)] || ''}
                    onChange={e => setAnswers(prev => ({ ...prev, [String(q.id)]: e.target.value }))}
                    placeholder="输入你的答案..."
                    rows={4}
                    className="w-full border border-border/60 rounded-lg px-3.5 py-2.5 text-sm placeholder:text-muted-foreground/35 focus:outline-none focus:border-primary/40 focus:ring-1 focus:ring-primary/15 resize-none bg-transparent transition-colors"
                  />
                )}
              </div>
            ))}

            {/* Submit bar */}
            <div className="sticky bottom-0 -mx-4 px-4 py-3 bg-background/90 backdrop-blur-xl border-t border-border/60 md:relative md:mx-0 md:px-0 md:py-0 md:bg-transparent md:backdrop-blur-none md:border-0">
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">
                  {answeredCount}/{detail.questions.length} 题已作答
                  {progressPct === 100 && (
                    <span className="ml-2 text-emerald-600 dark:text-emerald-400 font-semibold">全部完成</span>
                  )}
                </span>
                <Button
                  onClick={handleSubmit}
                  disabled={submitting || answeredCount === 0}
                  size="sm"
                  className="gap-1.5 rounded-lg"
                >
                  {submitting ? (
                    <><Spinner className="h-3.5 w-3.5 animate-spin" />提交中...</>
                  ) : (
                    <><Check className="h-3.5 w-3.5" weight="bold" />提交作业</>
                  )}
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </PageWrapper>
  );
}
