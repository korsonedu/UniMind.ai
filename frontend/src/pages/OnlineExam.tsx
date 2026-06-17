import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { Clock, AlertTriangle, ChevronLeft, ChevronRight, Send } from 'lucide-react';
import { cn } from '@/lib/utils';
import api from '@/lib/api';

interface QuestionData {
  id: number;
  question_text: string;
  question_type: string;
  options: Array<{ label: string; text: string; _original_label?: string }>;
  points: number;
}

interface ExamSession {
  attempt_id: number;
  exam_title: string;
  duration_minutes: number | null;
  remaining_seconds: number | null;
  started_at: string;
  questions: QuestionData[];
  saved_answers: Record<string, string>;
}

interface QuestionResult {
  question_id: number;
  score: number;
  max_score: number;
  is_correct: boolean;
  feedback: string;
  analysis?: string;
}

interface ExamResult {
  attempt_id: number;
  score: number;
  max_score: number;
  passed: boolean | null;
  question_results: QuestionResult[];
}

export function OnlineExam() {
  const { examId } = useParams<{ examId: string }>();
  const navigate = useNavigate();
  const [session, setSession] = useState<ExamSession | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [currentIdx, setCurrentIdx] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [timeLeft, setTimeLeft] = useState<number | null>(null);
  const [result, setResult] = useState<ExamResult | null>(null);
  const [error, setError] = useState('');
  const timeLeftRef = useRef<number | null>(null);
  const submittedRef = useRef(false);

  // Keep ref in sync for timer callback
  useEffect(() => {
    timeLeftRef.current = timeLeft;
  }, [timeLeft]);

  // Start exam
  const startExam = useCallback(async () => {
    try {
      const r = await api.post(`/quizzes/online-exams/${examId}/start/`);
      setSession(r.data);
      setAnswers(r.data.saved_answers || {});
      if (r.data.remaining_seconds != null) {
        setTimeLeft(r.data.remaining_seconds);
      }
    } catch (e: any) {
      setError(e.response?.data?.error || '开始考试失败');
    }
  }, [examId]);

  useEffect(() => {
    if (examId) startExam();
  }, [examId, startExam]);

  // Submit handler (extracted so timer can call it)
  const handleSubmit = useCallback(async () => {
    if (submittedRef.current || submitting) return;
    submittedRef.current = true;
    setSubmitting(true);
    try {
      const r = await api.post(`/quizzes/online-exams/${examId}/submit/`, { answers });
      setResult(r.data);
      setTimeLeft(0);
      toast.success('提交成功');
    } catch (e: any) {
      submittedRef.current = false;
      toast.error(e.response?.data?.error || '提交失败');
    } finally {
      setSubmitting(false);
    }
  }, [examId, answers, submitting]);

  // Submit with confirmation
  const confirmSubmit = useCallback(() => {
    const unanswered = session?.questions.filter(q => !answers[String(q.id)]?.trim()).length || 0;
    if (unanswered > 0) {
      if (!confirm(`还有 ${unanswered} 题未作答，确定提交吗？`)) return;
    }
    handleSubmit();
  }, [session, answers, handleSubmit]);

  // Countdown timer
  useEffect(() => {
    if (timeLeft == null || timeLeft <= 0 || result) return;
    const timer = setInterval(() => {
      setTimeLeft(prev => {
        if (prev == null || prev <= 1) {
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [timeLeft != null, !!result]);

  // Auto-submit when timer reaches 0
  useEffect(() => {
    if (timeLeft === 0 && session && !result && !submittedRef.current) {
      toast.info('考试时间已到，自动提交');
      handleSubmit();
    }
  }, [timeLeft, session, result, handleSubmit]);

  // Save answer
  const saveAnswer = (qid: number, answer: string) => {
    setAnswers(prev => ({ ...prev, [String(qid)]: answer }));
  };

  // Format countdown
  const formatTime = (seconds: number) => {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    return `${m}:${String(s).padStart(2, '0')}`;
  };

  // ── Results Page ──
  if (result) {
    const passed = result.passed;
    const scorePercent = result.max_score > 0 ? (result.score / result.max_score) * 100 : 0;
    return (
      <div className="max-w-3xl mx-auto p-6 space-y-6">
        <Card>
          <CardHeader className="text-center">
            <CardTitle className="text-2xl">{session?.exam_title || '考试'} — 成绩报告</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6 text-center">
            <div className="text-5xl font-black">
              <span className={passed ? 'text-green-500' : 'text-red-500'}>
                {result.score}
              </span>
              <span className="text-2xl text-muted-foreground"> / {result.max_score}</span>
            </div>
            <Progress value={scorePercent} className="h-3" />
            {passed !== null && passed !== undefined && (
              <Badge variant={passed ? 'default' : 'destructive'} className="text-lg px-4 py-2">
                {passed ? '通过 ✓' : '未通过 ✗'}
              </Badge>
            )}
            <div className="space-y-4 text-left pt-4">
              {result.question_results?.map((qr, i) => {
                const q = session?.questions.find(q => q.id === qr.question_id);
                return (
                  <Card key={qr.question_id} className="p-4 border-border/50">
                    <div className="flex justify-between items-start mb-2">
                      <p className="font-medium text-sm">第 {i + 1} 题</p>
                      <Badge variant={qr.is_correct ? 'secondary' : 'destructive'}>
                        {qr.score} / {qr.max_score}
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground line-clamp-2">
                      {q?.question_text || ''}
                    </p>
                    {qr.feedback && (
                      <div className="text-xs text-muted-foreground mt-2 pt-2 border-t border-border/50">
                        {qr.feedback}
                      </div>
                    )}
                    {qr.analysis && (
                      <div className="text-xs text-muted-foreground mt-1 p-2 bg-muted/30 rounded">
                        {qr.analysis}
                      </div>
                    )}
                  </Card>
                );
              })}
            </div>
            <Button onClick={() => navigate('/home')} className="w-full">
              返回首页
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ── Error State ──
  if (error) {
    return (
      <div className="max-w-md mx-auto p-6">
        <Card className="border-destructive/50 bg-destructive/5">
          <CardContent className="pt-6 space-y-4">
            <div className="flex items-center gap-3 text-destructive">
              <AlertTriangle className="h-5 w-5 flex-shrink-0" />
              <p className="font-medium">{error}</p>
            </div>
            <div className="flex gap-2">
              <Button onClick={() => navigate(-1)} variant="outline" className="flex-1">
                返回
              </Button>
              <Button onClick={() => { setError(''); startExam(); }} className="flex-1">
                重试
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ── Loading State ──
  if (!session) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <p className="text-muted-foreground animate-pulse">加载考试...</p>
      </div>
    );
  }

  // ── Exam In Progress ──
  const currentQ = session.questions[currentIdx];
  const answeredCount = Object.keys(answers).filter(k => answers[k]?.trim()).length;
  const totalCount = session.questions.length;
  const progress = totalCount > 0 ? (answeredCount / totalCount) * 100 : 0;

  return (
    <div className="max-w-3xl mx-auto p-4 space-y-4 pb-24">
      {/* Top bar */}
      <Card className="p-4">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h2 className="font-bold text-lg">{session.exam_title}</h2>
            <p className="text-xs text-muted-foreground">
              第 {currentIdx + 1} / {totalCount} 题
            </p>
          </div>
          <div className="flex items-center gap-3">
            {timeLeft != null && (
              <Badge
                variant={timeLeft < 60 ? 'destructive' : 'secondary'}
                className={cn('text-sm gap-1', timeLeft < 60 && 'animate-pulse')}
              >
                <Clock className="h-3.5 w-3.5" />
                {formatTime(timeLeft)}
              </Badge>
            )}
            <div className="hidden sm:flex items-center gap-2">
              <Progress value={progress} className="w-20 h-2" />
              <span className="text-xs text-muted-foreground whitespace-nowrap">
                {answeredCount}/{totalCount}
              </span>
            </div>
          </div>
        </div>
        {/* Mobile progress */}
        <div className="sm:hidden mt-3 flex items-center gap-2">
          <Progress value={progress} className="flex-1 h-2" />
          <span className="text-xs text-muted-foreground">{answeredCount}/{totalCount}</span>
        </div>
      </Card>

      {/* Question area */}
      {currentQ && (
        <Card className="p-5 md:p-6">
          <div className="space-y-4">
            <div className="flex items-center gap-2 flex-wrap">
              <Badge variant="outline" className="text-xs">
                {currentQ.question_type === 'objective' ? '客观题' : '主观题'}
              </Badge>
              <Badge variant="secondary" className="text-xs">{currentQ.points} 分</Badge>
            </div>
            <p className="text-base leading-relaxed whitespace-pre-wrap">
              {currentQ.question_text}
            </p>

            {/* Objective options */}
            {currentQ.question_type === 'objective' && currentQ.options && currentQ.options.length > 0 && (
              <div className="space-y-2">
                {currentQ.options.map((opt, i) => {
                  const isSelected = answers[String(currentQ.id)] === (opt._original_label || opt.label);
                  return (
                    <button
                      key={i}
                      onClick={() => saveAnswer(currentQ.id, opt._original_label || opt.label || String.fromCharCode(65 + i))}
                      className={cn(
                        'w-full text-left px-4 py-3 rounded-xl border transition-all duration-200',
                        isSelected
                          ? 'border-primary bg-primary/5 shadow-sm'
                          : 'border-border/50 hover:bg-muted/50 hover:border-border'
                      )}
                    >
                      <span className="font-semibold mr-2 text-muted-foreground">
                        {opt.label || String.fromCharCode(65 + i)}.
                      </span>
                      {opt.text}
                    </button>
                  );
                })}
              </div>
            )}

            {/* Subjective textarea */}
            {currentQ.question_type !== 'objective' && (
              <Textarea
                placeholder="请输入你的答案..."
                value={answers[String(currentQ.id)] || ''}
                onChange={e => saveAnswer(currentQ.id, e.target.value)}
                rows={6}
                className="mt-2 resize-y"
              />
            )}
          </div>
        </Card>
      )}

      {/* Bottom navigation */}
      <div className="fixed bottom-0 left-0 right-0 bg-background border-t border-border p-3 z-10">
        <div className="max-w-3xl mx-auto flex justify-between items-center">
          <Button
            variant="outline"
            disabled={currentIdx === 0}
            onClick={() => setCurrentIdx(i => i - 1)}
            size="sm"
            className="gap-1"
          >
            <ChevronLeft className="h-4 w-4" />
            <span className="hidden sm:inline">上一题</span>
          </Button>

          {/* Question number quick jump */}
          <div className="flex gap-1 flex-wrap justify-center max-w-[60%]">
            {session.questions.map((q, i) => {
              const isAnswered = !!answers[String(q.id)]?.trim();
              return (
                <Button
                  key={q.id}
                  variant={i === currentIdx ? 'default' : isAnswered ? 'secondary' : 'ghost'}
                  size="sm"
                  className={cn(
                    'w-8 h-8 p-0 text-xs rounded-lg',
                    i === currentIdx && 'ring-2 ring-primary ring-offset-1'
                  )}
                  onClick={() => setCurrentIdx(i)}
                >
                  {i + 1}
                </Button>
              );
            })}
          </div>

          <div className="flex gap-2">
            {currentIdx < totalCount - 1 ? (
              <Button onClick={() => setCurrentIdx(i => Math.min(i + 1, totalCount - 1))} size="sm" className="gap-1">
                <span className="hidden sm:inline">下一题</span>
                <ChevronRight className="h-4 w-4" />
              </Button>
            ) : (
              <Button onClick={confirmSubmit} disabled={submitting} size="sm" className="gap-1">
                <Send className="h-4 w-4" />
                <span className="hidden sm:inline">{submitting ? '提交中...' : '提交试卷'}</span>
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default OnlineExam;
