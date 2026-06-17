/**
 * 工作台 — 作业批改面板。
 * 列表待批改提交 → 展开评分。
 */
import { useEffect, useState } from 'react';
import { Spinner, CheckCircle, CaretDown, CaretUp, User, ClipboardText } from '@phosphor-icons/react';
import api from '@/lib/api';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';

interface SubmissionItem {
  id: number;
  student_name: string;
  assignment_title: string;
  submitted_at: string;
  answers: Record<string, string>; // question_id → answer
  questions: SubmissionQuestion[];
  current_score: number | null;
  current_feedback: string;
}

interface SubmissionQuestion {
  id: number;
  text: string;
  q_type: string;
  max_score: number;
  reference_answer?: string;
  student_answer: string;
}

export function GradingPanel() {
  const [submissions, setSubmissions] = useState<SubmissionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [scores, setScores] = useState<Record<string, string>>({}); // question_id → score
  const [feedback, setFeedback] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const fetchSubmissions = async () => {
    setLoading(true);
    try {
      const res = await api.get('/quizzes/assignments/submissions/');
      setSubmissions(res.data || []);
    } catch {
      toast.error('加载待批改列表失败');
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchSubmissions();
  }, []);

  const toggleExpand = (submission: SubmissionItem) => {
    if (expandedId === submission.id) {
      setExpandedId(null);
      setScores({});
      setFeedback('');
    } else {
      setExpandedId(submission.id);
      // Initialize scores from question list
      const initial: Record<string, string> = {};
      submission.questions.forEach((q) => {
        initial[String(q.id)] = '';
      });
      setScores(initial);
      setFeedback(submission.current_feedback || '');
    }
  };

  const handleScoreChange = (questionId: string, value: string) => {
    setScores((prev) => ({ ...prev, [questionId]: value }));
  };

  const handleSubmitGrade = async (submissionId: number) => {
    setSubmitting(true);
    try {
      const res = await api.post(`/quizzes/assignments/submissions/${submissionId}/grade/`, {
        scores,
        feedback,
      });
      toast.success(res.data?.message || '批改成功');
      // Remove from list
      setSubmissions((prev) => prev.filter((s) => s.id !== submissionId));
      setExpandedId(null);
      setScores({});
      setFeedback('');
    } catch (e: unknown) {
      const err = e as { response?: { data?: { error?: string } } };
      toast.error(err?.response?.data?.error || '批改失败');
    }
    setSubmitting(false);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto p-4 md:p-6 space-y-4">
      <h1 className="text-lg font-bold">作业批改</h1>

      {submissions.length === 0 ? (
        <div className="text-center py-20 space-y-2">
          <CheckCircle className="h-10 w-10 mx-auto text-emerald-500/40" />
          <p className="text-sm text-muted-foreground">暂无待批改作业</p>
          <p className="text-xs text-muted-foreground/60">所有提交都已批改完成</p>
        </div>
      ) : (
        <div className="space-y-2">
          {submissions.map((sub) => {
            const isExpanded = expandedId === sub.id;
            const gradedCount = Object.values(scores).filter((v) => v.trim()).length;
            const totalQuestions = sub.questions.length;

            return (
              <div
                key={sub.id}
                className="rounded-xl border border-border bg-card overflow-hidden transition-colors"
              >
                {/* Header row */}
                <button
                  onClick={() => toggleExpand(sub)}
                  className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-muted/30 transition-colors"
                >
                  <div className="h-8 w-8 rounded-lg bg-amber-50 text-amber-500 flex items-center justify-center shrink-0">
                    <ClipboardText className="h-4 w-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-bold truncate">
                      {sub.student_name} · {sub.assignment_title}
                    </div>
                    <div className="text-xs text-muted-foreground mt-0.5 flex items-center gap-1">
                      <User className="h-3 w-3" />
                      <span>
                        提交于 {new Date(sub.submitted_at).toLocaleDateString('zh-CN')}
                      </span>
                      {sub.current_score != null && (
                        <Badge variant="outline" className="ml-2 text-[10px]">
                          已评分: {sub.current_score}
                        </Badge>
                      )}
                    </div>
                  </div>
                  {isExpanded ? (
                    <CaretUp className="h-4 w-4 text-muted-foreground shrink-0" />
                  ) : (
                    <CaretDown className="h-4 w-4 text-muted-foreground shrink-0" />
                  )}
                </button>

                {/* Expanded grading area */}
                {isExpanded && (
                  <div className="border-t border-border px-4 py-4 space-y-4 bg-muted/20">
                    {sub.questions.map((q, i) => (
                      <div
                        key={q.id}
                        className="rounded-lg border border-border bg-card p-4 space-y-3"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="text-xs font-bold text-muted-foreground mb-1">
                              第 {i + 1} 题 · {q.q_type} · {q.max_score} 分
                            </p>
                            <p className="text-sm leading-relaxed">{q.text}</p>
                          </div>
                        </div>

                        {q.reference_answer && (
                          <div className="rounded-md bg-emerald-50 px-3 py-2 text-xs leading-relaxed">
                            <span className="font-bold text-emerald-600">参考答案：</span>
                            <span className="text-emerald-700">{q.reference_answer}</span>
                          </div>
                        )}

                        <div className="rounded-md bg-muted/50 px-3 py-2 text-sm leading-relaxed">
                          <span className="font-bold text-muted-foreground text-xs">
                            学生答案：
                          </span>
                          <span>{q.student_answer || '（未作答）'}</span>
                        </div>

                        <div className="flex items-center gap-2">
                          <label className="text-xs font-bold text-muted-foreground shrink-0">
                            得分：
                          </label>
                          <Input
                            type="number"
                            min={0}
                            max={q.max_score}
                            value={scores[String(q.id)] || ''}
                            onChange={(e) =>
                              handleScoreChange(String(q.id), e.target.value)
                            }
                            placeholder={`0-${q.max_score}`}
                            className="w-24 h-8 text-sm"
                          />
                          <span className="text-xs text-muted-foreground">
                            / {q.max_score}
                          </span>
                        </div>
                      </div>
                    ))}

                    {/* Feedback */}
                    <div>
                      <label className="text-xs font-bold text-muted-foreground block mb-1.5">
                        反馈评语（可选）
                      </label>
                      <Textarea
                        value={feedback}
                        onChange={(e) => setFeedback(e.target.value)}
                        placeholder="给学生留言..."
                        rows={3}
                      />
                    </div>

                    {/* Action bar */}
                    <div className="flex items-center justify-between pt-2">
                      <span className="text-xs text-muted-foreground">
                        {gradedCount}/{totalQuestions} 题已评分
                      </span>
                      <Button
                        onClick={() => handleSubmitGrade(sub.id)}
                        disabled={submitting || gradedCount === 0}
                      >
                        {submitting ? '提交中...' : '提交批改'}
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
