import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
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
  study_plan: {
    weak_kps: Array<{ kp_id: number; kp_name: string; accuracy: number }>;
    strong_kps: Array<{ kp_id: number; kp_name: string; accuracy: number }>;
    recommendation: string;
  };
}

export function DiagnosticTest() {
  const { t } = useTranslation('diagnostic');
  const navigate = useNavigate();
  const updateUser = useAuthStore(s => s.updateUser);
  const [phase, setPhase] = useState<Phase>('welcome');
  const [loading, setLoading] = useState(false);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [timeLeft, setTimeLeft] = useState(300);
  const [result, setResult] = useState<DiagnosticResult | null>(null);
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
      const res = await api.post('/users/me/diagnostic/submit/', { answers: formattedAnswers });
      setResult(res.data);
      updateUser({ has_completed_initial_assessment: true });
      setPhase('results');
    } catch (err: any) {
      submittedRef.current = false;
      toast.error(err.response?.data?.error || t('errors.submitFailed'));
    } finally {
      setLoading(false);
    }
  }, [questions, answers]);

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
        toast.info(t('errors.alreadyCompleted'));
        navigate('/tests');
      } else {
        toast.error(err.response?.data?.error || t('errors.generateFailed'));
      }
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
          <h1 className="text-3xl font-bold tracking-tight mb-3">{t('welcome.title')}</h1>
          <p className="text-muted-foreground mb-10 leading-relaxed">
            {t('welcome.subtitle')}
          </p>

          <div className="flex justify-center gap-8 mb-10">
            <div className="text-center">
              <div className="flex items-center justify-center gap-1.5 text-muted-foreground mb-1">
                <Hash className="w-4 h-4" />
              </div>
              <div className="text-2xl font-bold">10</div>
              <div className="text-xs text-muted-foreground">{t('welcome.questions')}</div>
            </div>
            <div className="w-px bg-border" />
            <div className="text-center">
              <div className="flex items-center justify-center gap-1.5 text-muted-foreground mb-1">
                <Clock className="w-4 h-4" />
              </div>
              <div className="text-2xl font-bold">5</div>
              <div className="text-xs text-muted-foreground">{t('welcome.minutes')}</div>
            </div>
            <div className="w-px bg-border" />
            <div className="text-center">
              <div className="flex items-center justify-center gap-1.5 text-muted-foreground mb-1">
                <Brain className="w-4 h-4" />
              </div>
              <div className="text-2xl font-bold">AI</div>
              <div className="text-xs text-muted-foreground">{t('welcome.aiAnalysis')}</div>
            </div>
          </div>

          <Button className="w-full rounded-full py-6 text-base" size="lg" onClick={startDiagnostic}>
            {t('welcome.startButton')}
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
                placeholder={t('testing.placeholder')}
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
            {t('testing.previous')}
          </Button>
          {currentIndex < questions.length - 1 ? (
            <Button className="rounded-full" onClick={() => setCurrentIndex(i => i + 1)}>
              {t('testing.next')}
              <ArrowRight className="w-4 h-4 ml-1" />
            </Button>
          ) : (
            <Button className="rounded-full" onClick={handleSubmit} disabled={loading}>
              {loading ? t('testing.submitting') : t('testing.submit')}
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
          <h1 className="text-3xl font-bold tracking-tight mb-2">{t('results.title')}</h1>
          <div className="text-5xl font-bold mt-4 mb-2">{accuracy}%</div>
          <p className="text-muted-foreground">
            {t('results.correctOf', { score: result.total_score, total: result.total_questions })}
          </p>
        </div>

        <div className="space-y-6 mb-10">
          {/* Strong KPs */}
          {result.study_plan.strong_kps.length > 0 && (
            <Card className="border-border/50 shadow-sm">
              <CardContent className="p-5">
                <h3 className="text-sm font-semibold text-green-600 mb-3">{t('results.strongKPs')}</h3>
                <div className="flex flex-wrap gap-2">
                  {result.study_plan.strong_kps.map(kp => (
                    <Badge key={kp.kp_id} variant="outline" className="border-green-200 dark:border-green-800/40 text-green-700 dark:text-green-400 rounded-full">
                      {kp.kp_name} ({kp.accuracy}%)
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Weak KPs */}
          {result.study_plan.weak_kps.length > 0 && (
            <Card className="border-border/50 shadow-sm">
              <CardContent className="p-5">
                <h3 className="text-sm font-semibold text-red-600 mb-3">{t('results.weakKPs')}</h3>
                <div className="flex flex-wrap gap-2">
                  {result.study_plan.weak_kps.map(kp => (
                    <Badge key={kp.kp_id} variant="outline" className="border-red-200 dark:border-red-800/40 text-red-700 dark:text-red-400 rounded-full">
                      {kp.kp_name} ({kp.accuracy}%)
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Recommendation */}
          {result.study_plan.recommendation && (
            <Card className="border-border/50 shadow-sm">
              <CardContent className="p-5">
                <h3 className="text-sm font-semibold mb-2">{t('results.aiAdvice')}</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">{result.study_plan.recommendation}</p>
              </CardContent>
            </Card>
          )}
        </div>

        <div className="flex gap-3">
          <Button className="flex-1 rounded-full py-6 text-base" size="lg" onClick={() => navigate('/')}>
            <House className="w-5 h-5 mr-2" />
            {t('results.goHome')}
          </Button>
          <Button className="flex-1 rounded-full py-6 text-base" size="lg" variant="outline" onClick={() => navigate('/tests')}>
            {t('results.startPractice')}
            <ArrowRight className="w-5 h-5 ml-2" />
          </Button>
        </div>
      </div>
    );
  }

  return <Loading fullScreen />;
}
