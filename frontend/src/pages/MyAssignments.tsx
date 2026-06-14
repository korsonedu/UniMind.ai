/**
 * 学生端 — 我的作业。
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Spinner, Check, Clock, FileText, CaretRight } from '@phosphor-icons/react';
import api from '@/lib/api';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
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

export default function MyAssignments() {
  const navigate = useNavigate();
  const [view, setView] = useState<View>('list');
  const [assignments, setAssignments] = useState<AssignmentItem[]>([]);
  const [loading, setLoading] = useState(true);

  // Detail state
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
      const res = await api.get('/quizzes/assignments/my/');
      setAssignments(res.data || []);
    } catch { toast.error('加载作业列表失败'); }
    setLoading(false);
  };

  useEffect(() => { fetchList(); }, []);

  const openDetail = async (id: number) => {
    setDetailLoading(true);
    setView('detail');
    try {
      const res = await api.get(`/quizzes/assignments/${id}/questions/`);
      setDetail(res.data);
      setAnswers(res.data.previous_answers || {});
    } catch { toast.error('加载作业详情失败'); }
    setDetailLoading(false);
  };

  const handleSubmit = async () => {
    if (!detail) return;
    setSubmitting(true);
    try {
      const res = await api.post('/quizzes/assignments/submit/', {
        assignment_id: detail.id,
        answers,
      });
      toast.success(res.data.message);
      setDetail({ ...detail, submitted: true, score: res.data.score });
      fetchList();
    } catch (e: any) {
      toast.error(e?.response?.data?.error || '提交失败');
    }
    setSubmitting(false);
  };

  const isOverdue = (due: string | null) => {
    if (!due) return false;
    return new Date(due) < new Date();
  };

  // ── List view ──
  if (view === 'list') {
    return (
      <div className="max-w-2xl mx-auto p-4 md:p-6 space-y-4">
        <h1 className="text-lg font-bold">我的作业</h1>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Spinner className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : assignments.length === 0 ? (
          <div className="text-center py-12 space-y-2">
            <FileText className="h-10 w-10 mx-auto text-muted-foreground/40" />
            <p className="text-sm text-muted-foreground">暂无作业</p>
            <p className="text-xs text-muted-foreground/60">老师布置作业后会显示在这里</p>
          </div>
        ) : (
          <div className="space-y-1">
            {assignments.map(a => (
              <button
                key={a.id}
                onClick={() => openDetail(a.id)}
                className="w-full flex items-center gap-3 px-4 py-3 rounded-xl border border-border bg-card hover:border-primary/20 transition-colors text-left"
              >
                <div className={cn(
                  'h-8 w-8 rounded-lg flex items-center justify-center shrink-0',
                  a.submitted ? 'bg-emerald-50 text-emerald-500' :
                  isOverdue(a.due_date) ? 'bg-red-50 text-red-500' :
                  'bg-amber-50 text-amber-500'
                )}>
                  {a.submitted ? <Check className="h-4 w-4" /> : <Clock className="h-4 w-4" />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-bold">{a.title}</div>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {a.question_count} 题
                    {a.due_date && ` · 截止 ${new Date(a.due_date).toLocaleDateString('zh-CN')}`}
                    {a.submitted && a.score !== null && ` · 得分 ${a.score}`}
                  </div>
                </div>
                {a.submitted ? (
                  <span className="text-[10px] font-bold text-emerald-500 bg-emerald-50 px-2 py-0.5 rounded-full">已提交</span>
                ) : isOverdue(a.due_date) ? (
                  <span className="text-[10px] font-bold text-red-500 bg-red-50 px-2 py-0.5 rounded-full">已截止</span>
                ) : (
                  <CaretRight className="h-4 w-4 text-muted-foreground" />
                )}
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  // ── Detail view ──
  if (detailLoading || !detail) {
    return (
      <div className="flex items-center justify-center h-full">
        <Spinner className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const answeredCount = Object.values(answers).filter(v => v.trim()).length;

  return (
    <div className="max-w-2xl mx-auto p-4 md:p-6 space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button onClick={() => setView('list')} className="p-1 -ml-1 rounded hover:bg-muted transition-colors text-muted-foreground">
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div>
          <h1 className="text-lg font-bold">{detail.title}</h1>
          <p className="text-xs text-muted-foreground">
            {detail.questions.length} 题
            {detail.due_date && ` · 截止 ${new Date(detail.due_date).toLocaleDateString('zh-CN')}`}
            {detail.submitted && detail.score !== null && ` · 得分 ${detail.score}`}
          </p>
        </div>
        {detail.submitted && (
          <span className="ml-auto text-[10px] font-bold text-emerald-500 bg-emerald-50 px-2 py-0.5 rounded-full">已提交</span>
        )}
      </div>

      {/* Questions */}
      {detail.submitted ? (
        <div className="space-y-4">
          {detail.questions.map((q, i) => (
            <div key={q.id} className="rounded-xl border border-border bg-card p-4">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs font-bold text-muted-foreground">第 {i + 1} 题</span>
                <span className="text-[10px] text-muted-foreground/60">{q.points} 分</span>
              </div>
              <div className="text-sm leading-relaxed prose prose-sm max-w-none dark:prose-invert">
                <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                  {q.text}
                </ReactMarkdown>
              </div>
              <div className="mt-3 p-3 rounded-lg bg-muted/30">
                <span className="text-xs font-bold text-muted-foreground">你的答案：</span>
                <span className="text-sm ml-1">{detail.previous_answers[String(q.id)] || '（未作答）'}</span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="space-y-4">
          {detail.questions.map((q, i) => (
            <div key={q.id} className="rounded-xl border border-border bg-card p-4">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs font-bold text-muted-foreground">第 {i + 1} 题</span>
                <span className="text-[10px] text-muted-foreground/60">{q.points} 分</span>
              </div>
              <div className="text-sm leading-relaxed prose prose-sm max-w-none dark:prose-invert mb-3">
                <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                  {q.text}
                </ReactMarkdown>
              </div>
              {q.q_type === 'objective' && q.options?.length ? (
                <div className="space-y-1.5">
                  {q.options.map((opt, j) => (
                    <button
                      key={j}
                      onClick={() => setAnswers(prev => ({ ...prev, [String(q.id)]: opt }))}
                      className={cn(
                        'w-full text-left px-3 py-2 rounded-lg text-sm border transition-colors',
                        answers[String(q.id)] === opt
                          ? 'border-primary bg-primary/5 text-primary font-bold'
                          : 'border-border text-foreground/70 hover:border-primary/30'
                      )}
                    >
                      {String.fromCharCode(65 + j)}. {opt}
                    </button>
                  ))}
                </div>
              ) : (
                <textarea
                  value={answers[String(q.id)] || ''}
                  onChange={e => setAnswers(prev => ({ ...prev, [String(q.id)]: e.target.value }))}
                  placeholder="输入你的答案..."
                  rows={4}
                  className="w-full border border-border rounded-lg px-3 py-2 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:border-primary/40 resize-none"
                />
              )}
            </div>
          ))}

          {/* Submit */}
          <div className="flex items-center justify-between pt-2">
            <span className="text-xs text-muted-foreground">
              {answeredCount}/{detail.questions.length} 题已作答
            </span>
            <Button onClick={handleSubmit} disabled={submitting || answeredCount === 0}>
              {submitting ? '提交中...' : '提交作业'}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
