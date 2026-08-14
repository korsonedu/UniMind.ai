import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Loading } from '@/components/Loading';
import { useAuthStore } from '@/store/useAuthStore';
import api from '@/lib/api';
import { toast } from 'sonner';
import { Brain, Clock, Hash, ArrowRight, ArrowLeft, CheckCircle, House } from '@phosphor-icons/react';

type Phase = 'welcome' | 'testing' | 'results';

interface Question {
  question_text: string;
  q_type: string;
  options?: string[];
  answer?: string;
  knowledge_point_id?: number;
  _kp_name?: string;
}

interface DiagnosticResult {
  total_score: number;
  total_questions: number;
  results: Array<{
    question_text: string;
    user_answer: string;
    correct_answer: string;
    is_correct: boolean;
    score: number;
    feedback: string;
    knowledge_point_name: string;
  }>;
}

export function DiagnosticTest() {
  const navigate = useNavigate();
  const updateUser = useAuthStore(s => s.updateUser);
  const [phase, setPhase] = useState<Phase>('welcome');
  const [loading, setLoading] = useState(false);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [timeLeft, setTimeLeft] = useState(300);
  const [result, setResult] = useState<DiagnosticResult | null>(null);
  const [isReassessment, setIsReassessment] = useState(false);
  const submittedRef = useRef(false);

  useEffect(() => {
    if (phase !== 'testing') return;
    const timer = setInterval(() => setTimeLeft(t => {
      if (t <= 1) { clearInterval(timer); return 0; }
      return t - 1;
    }), 1000);
    return () => clearInterval(timer);
  }, [phase]);

  const handleSubmit = useCallback(async () => {
    if (submittedRef.current) return;
    submittedRef.current = true;
    setLoading(true);
    try {
      const formattedAnswers = questions.map((q, i) => ({
        question: q,
        answer: answers[i] || '',
        knowledge_point_id: q.knowledge_point_id,
        _kp_name: q._kp_name,
      }));
      const res = await api.post('/users/me/diagnostic/submit/', {
        answers: formattedAnswers,
        is_reassessment: isReassessment,
      });
      setResult(res.data);
      updateUser({ has_completed_initial_assessment: true });
      setPhase('results');
    } catch (err: any) {
      submittedRef.current = false;
      toast.error(err.response?.data?.error || '提交失败');
    } finally {
      setLoading(false);
    }
  }, [questions, answers, isReassessment]);

  useEffect(() => {
    if (timeLeft <= 0 && phase === 'testing') {
      handleSubmit();
    }
  }, [timeLeft, phase, handleSubmit]);

  const startDiagnostic = async () => {
    submittedRef.current = false;
    setLoading(true);
    try {
      const res = await api.post('/users/me/diagnostic/generate/');
      setQuestions(res.data.questions);
      setTimeLeft(res.data.time_limit_seconds || 300);
      setPhase('testing');
    } catch (err: any) {
      if (err.response?.data?.status === 'already_completed') {
        toast.info('诊断已完成，你可以直接开始练习');
        navigate('/tests');
      } else {
        toast.error(err.response?.data?.error || '生成诊断题失败');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleReassess = async () => {
    setLoading(true);
    try {
      const { data } = await api.post('/users/me/diagnostic/reassess/');
      setQuestions(data.questions);
      setTimeLeft(data.time_limit_seconds || 300);
      setCurrentIndex(0);
      setAnswers({});
      setResult(null);
      setIsReassessment(true);
      setPhase('testing');
      submittedRef.current = false;
    } catch (err: any) {
      if (err.response?.data?.status === 'already_completed') {
        toast.info('您已完成诊断评估');
        navigate('/tests');
        return;
      }
      toast.error(err.response?.data?.error || '生成重评估失败');
    } finally {
      setLoading(false);
    }
  };

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  if (loading && phase === 'welcome') return <Loading fullScreen />;

  // Welcome
  if (phase === 'welcome') {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="max-w-md w-full text-center">
          <div className="w-20 h-20 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-6">
            <Brain className="w-10 h-10 text-primary" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight mb-3">诊断测试</h1>
          <p className="text-muted-foreground mb-10 leading-relaxed">
            通过 10 道题快速了解你的知识掌握情况，小宇会据此为你推荐练习方向。
          </p>

          <div className="flex justify-center gap-8 mb-10">
            <div className="text-center">
              <div className="flex items-center justify-center gap-1.5 text-muted-foreground mb-1">
                <Hash className="w-4 h-4" />
              </div>
              <div className="text-2xl font-bold">10</div>
              <div className="text-xs text-muted-foreground">道题</div>
            </div>
            <div className="w-px bg-border" />
            <div className="text-center">
              <div className="flex items-center justify-center gap-1.5 text-muted-foreground mb-1">
                <Clock className="w-4 h-4" />
              </div>
              <div className="text-2xl font-bold">5</div>
              <div className="text-xs text-muted-foreground">分钟</div>
            </div>
            <div className="w-px bg-border" />
            <div className="text-center">
              <div className="flex items-center justify-center gap-1.5 text-muted-foreground mb-1">
                <Brain className="w-4 h-4" />
              </div>
              <div className="text-2xl font-bold">AI</div>
              <div className="text-xs text-muted-foreground">智能分析</div>
            </div>
          </div>

          <Button className="w-full rounded-full py-6 text-base" size="lg" onClick={startDiagnostic}>
            开始测试
            <ArrowRight className="w-5 h-5 ml-2" />
          </Button>
        </div>
      </div>
    );
  }

  // Testing
  if (phase === 'testing' && questions.length > 0) {
    const q = questions[currentIndex];
    const progress = ((currentIndex + 1) / questions.length) * 100;

    return (
      <div className="min-h-screen p-4 max-w-2xl mx-auto">
        {/* Reassessment banner */}
        {isReassessment && (
          <div className="bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 text-blue-700 dark:text-blue-300 text-sm rounded-xl px-4 py-3 mb-4 text-center">
            重新评估中 — 本次评估聚焦你之前的薄弱知识点
          </div>
        )}

        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="rounded-full">{currentIndex + 1} / {questions.length}</Badge>
            {q._kp_name && <Badge variant="secondary" className="rounded-full">{q._kp_name}</Badge>}
          </div>
          <div className={`font-mono text-lg font-semibold ${timeLeft < 60 ? 'text-red-500' : 'text-muted-foreground'}`}>
            {formatTime(timeLeft)}
          </div>
        </div>

        {/* Progress */}
        <div className="w-full bg-muted rounded-full h-1.5 mb-8">
          <div className="bg-primary h-1.5 rounded-full transition-all duration-300" style={{ width: `${progress}%` }} />
        </div>

        {/* Question */}
        <Card className="border-border/50 shadow-sm mb-8">
          <CardContent className="p-6 md:p-8">
            <div className="text-base md:text-lg whitespace-pre-wrap leading-relaxed mb-6">{q.question_text}</div>

            {q.q_type === 'objective' && q.options ? (
              <div className="space-y-2.5">
                {q.options.map((opt, i) => (
                  <button
                    key={i}
                    className={`w-full text-left p-4 rounded-xl border transition-all duration-200 ${
                      answers[currentIndex] === opt
                        ? 'border-primary bg-primary/5 shadow-sm'
                        : 'border-border/50 hover:bg-muted/50 hover:border-border'
                    }`}
                    onClick={() => setAnswers(prev => ({ ...prev, [currentIndex]: opt }))}
                  >
                    <span className="font-semibold mr-2 text-muted-foreground">{String.fromCharCode(65 + i)}.</span>
                    {opt}
                  </button>
                ))}
              </div>
            ) : (
              <textarea
                className="w-full p-4 border border-border/50 rounded-xl min-h-[140px] resize-y focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
                placeholder="输入你的答案..."
                value={answers[currentIndex] || ''}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setAnswers(prev => ({ ...prev, [currentIndex]: e.target.value }))}
              />
            )}
          </CardContent>
        </Card>

        {/* Navigation */}
        <div className="flex justify-between">
          <Button
            variant="outline"
            className="rounded-full"
            disabled={currentIndex === 0}
            onClick={() => setCurrentIndex(i => i - 1)}
          >
            <ArrowLeft className="w-4 h-4 mr-1" />
            上一题
          </Button>
          {currentIndex < questions.length - 1 ? (
            <Button className="rounded-full" onClick={() => setCurrentIndex(i => i + 1)}>
              下一题
              <ArrowRight className="w-4 h-4 ml-1" />
            </Button>
          ) : (
            <Button className="rounded-full" onClick={handleSubmit} disabled={loading}>
              {loading ? '提交中...' : '提交答卷'}
            </Button>
          )}
        </div>
      </div>
    );
  }

  // Results
  if (phase === 'results' && result) {
    const accuracy = Math.round((result.total_score / result.total_questions) * 100);

    return (
      <div className="min-h-screen p-4 max-w-2xl mx-auto">
        <div className="text-center py-8">
          <div className="w-20 h-20 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-6">
            <CheckCircle className="w-10 h-10 text-primary" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight mb-2">诊断完成</h1>
          <div className="text-5xl font-bold mt-4 mb-2">{accuracy}%</div>
          <p className="text-muted-foreground mb-4">
            {`答对 ${result.total_score} / ${result.total_questions} 题`}
          </p>
          <Button onClick={handleReassess} variant="outline" className="rounded-full">
            重新评估（聚焦弱项）
          </Button>
        </div>

        <div className="flex gap-3">
          <Button className="flex-1 rounded-full py-6 text-base" size="lg" onClick={() => navigate('/')}>
            <House className="w-5 h-5 mr-2" />
            回到首页
          </Button>
          <Button className="flex-1 rounded-full py-6 text-base" size="lg" variant="outline" onClick={() => navigate('/tests')}>
            开始练习
            <ArrowRight className="w-5 h-5 ml-2" />
          </Button>
        </div>
      </div>
    );
  }

  return <Loading fullScreen />;
}
