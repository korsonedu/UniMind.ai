import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { ArrowLeft, Bell, CheckCircle2, ChevronLeft, ChevronRight, Loader2, Star } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { toast } from 'sonner';
import { cn, processMathContent, normalizeOptions } from '@/lib/utils';
import api from '@/lib/api';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import {
  getLearningReminderSettings,
  sendLearningReminder,
  updateLearningReminderSetting,
  type LearningReminderSettings,
} from '@/lib/learningReminders';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { useTranslation } from 'react-i18next';

const hasAnswer = (val: any) => {
  if (typeof val === 'string') return val.trim().length > 0;
  return val !== null && val !== undefined && val !== '';
};

export const TestSessionPage: React.FC = () => {
  const { t } = useTranslation('testSession');
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [questions, setQuestions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [answers, setAnswers] = useState<Record<number, any>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [reminderSettings, setReminderSettings] = useState<LearningReminderSettings>(getLearningReminderSettings());
  const lastTypeReminderQidRef = useRef<number | null>(null);

  const questionLimit = useMemo(() => {
    const raw = Number.parseInt(searchParams.get('count') || '5', 10);
    if (!Number.isFinite(raw)) return 5;
    return Math.max(1, Math.min(raw, 50));
  }, [searchParams]);

  const preference = useMemo(() => {
    const p = searchParams.get('preference') || 'balanced';
    return ['balanced', 'new_first', 'review_first'].includes(p) ? p : 'balanced';
  }, [searchParams]);

  useEffect(() => {
    const fetchQuestions = async () => {
      setLoading(true);
      try {
        const res = await api.get(`/quizzes/questions/?limit=${questionLimit}&preference=${preference}`);
        if (!res.data?.length) {
          toast.error(t('noQuestions'));
          navigate('/tests', { replace: true });
          return;
        }
        setQuestions(res.data.map((q: any) => ({ ...q, options: normalizeOptions(q.options) })));
      } catch (e) {
        toast.error(t('loadFailed'));
        navigate('/tests', { replace: true });
      } finally {
        setLoading(false);
      }
    };

    fetchQuestions();
  }, [navigate, questionLimit]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const media = window.matchMedia('(max-width: 767px)');
    const sync = () => setIsMobile(media.matches);
    sync();
    media.addEventListener('change', sync);
    return () => media.removeEventListener('change', sync);
  }, []);

  const currentQ = questions[currentIdx];
  const totalNeedAnswer = questions.filter((q) => !q.is_mastered).length;
  const answeredCount = questions.filter((q) => !q.is_mastered && hasAnswer(answers[q.id])).length;

  useEffect(() => {
    if (!isMobile || !currentQ?.id || !reminderSettings.questionType) return;
    if (lastTypeReminderQidRef.current === currentQ.id) return;
    lastTypeReminderQidRef.current = currentQ.id;

    const typeLabel = currentQ.q_type === 'objective'
      ? t('typeObjective')
      : currentQ.subjective_type === 'calculate'
        ? t('typeCalculate')
        : currentQ.subjective_type === 'noun'
          ? t('typeNoun')
          : t('typeEssay');

    sendLearningReminder(t('questionTypeReminder'), t('typeReminderLabel', { type: typeLabel }));
  }, [currentQ, isMobile, reminderSettings.questionType]);

  const toggleFavorite = async (qId: number) => {
    try {
      const res = await api.post('/quizzes/favorite/toggle/', { question_id: qId });
      setQuestions((prev) => prev.map((q) => (q.id === qId ? { ...q, is_favorite: res.data.is_favorite } : q)));
      toast.success(res.data.is_favorite ? t('favorited') : t('unfavorited'));
    } catch (e) {
      toast.error(t('operationFailed'));
    }
  };

  const toggleMastered = async (qId: number) => {
    try {
      const res = await api.post('/quizzes/mastered/toggle/', { question_id: qId });
      const isNowMastered = res.data.is_mastered;
      setQuestions((prev) => prev.map((q) => (q.id === qId ? { ...q, is_mastered: isNowMastered } : q)));
      if (isNowMastered) {
        setAnswers((prev) => {
          const next = { ...prev };
          delete next[qId];
          return next;
        });
        toast.success(t('mastered'));
      }
    } catch (e) {
      toast.error(t('operationFailed'));
    }
  };

  const handleSubmit = async () => {
    const unmasteredQuestions = questions.filter((q) => !q.is_mastered);
    const validAnswers = unmasteredQuestions.filter((q) => hasAnswer(answers[q.id]));

    if (unmasteredQuestions.length > 0 && validAnswers.length < unmasteredQuestions.length) {
      toast.error(t('completeAll', { done: validAnswers.length, total: unmasteredQuestions.length }));
      return;
    }

    if (unmasteredQuestions.length === 0) {
      toast.info(t('practiceEnded'));
      navigate('/tests', { replace: true });
      return;
    }

    setIsSubmitting(true);
    try {
      const payload = unmasteredQuestions.map((q) => ({ question_id: q.id, answer: answers[q.id] }));
      await api.post('/quizzes/submit-exam/', { answers: payload });
      toast.success(t('submitted'), { description: t('submittedDesc') });
      navigate('/tests', { replace: true });
    } catch (e: any) {
      toast.error(e.response?.data?.error || t('submitFailed'));
    } finally {
      setIsSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="h-full min-h-0 flex items-center justify-center bg-background">
        <Loader2 className="h-7 w-7 animate-spin text-muted-foreground/50" />
      </div>
    );
  }

  if (!currentQ) {
    return null;
  }

  return (
    <div className="h-full min-h-0 bg-background text-foreground flex flex-col overflow-hidden">
      <header className="h-12 shrink-0 border-b border-border px-3 flex items-center justify-between bg-background/90 backdrop-blur-md">
        <Link to="/tests"><Button variant="ghost" size="sm" className="h-8 px-2 rounded-lg text-xs font-bold">
          <ArrowLeft className="h-4 w-4 mr-1" />
          {t('back')}
        </Button>
        <div className="flex items-center gap-2">
          {isMobile && (
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline" size="icon" className="h-8 w-8 rounded-lg border-border">
                  <Bell className="h-4 w-4" />
                </Button>
              </PopoverTrigger>
              <PopoverContent side="bottom" align="end" className="w-64 rounded-2xl p-4 bg-card border-border">
                <div className="space-y-3 text-left">
                  <p className="text-xs font-black uppercase tracking-widest text-muted-foreground">{t('reminderSettings')}</p>
                  <div className="flex items-center justify-between">
                    <Label className="text-xs font-bold">{t('questionTypeReminder')}</Label>
                    <Switch
                      checked={reminderSettings.questionType}
                      onCheckedChange={(enabled) => {
                        setReminderSettings(updateLearningReminderSetting('questionType', enabled));
                      }}
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <Label className="text-xs font-bold">{t('testResultReminder')}</Label>
                    <Switch
                      checked={reminderSettings.testResult}
                      onCheckedChange={(enabled) => {
                        setReminderSettings(updateLearningReminderSetting('testResult', enabled));
                      }}
                    />
                  </div>
                </div>
              </PopoverContent>
            </Popover>
          )}
          <div className="px-3 py-1 rounded-lg bg-primary text-primary-foreground font-mono font-bold text-xs tabular-nums">
            {currentIdx + 1} / {questions.length}
          </div>
        </div>
      </header>

      <div className="flex-1 min-h-0 flex flex-col">
        <div className="flex-1 min-h-0 overflow-y-auto px-3 py-3">
          <div className="bg-card border border-border/60 rounded-2xl p-4 space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="secondary" className="rounded-lg px-2 py-0.5 text-[10px] font-black uppercase tracking-widest bg-muted text-muted-foreground border-none">
                {currentQ.q_type === 'objective'
                  ? t('typeObjective')
                  : currentQ.subjective_type === 'calculate'
                    ? t('typeCalculate')
                    : currentQ.subjective_type === 'noun'
                      ? t('typeNoun')
                      : t('typeEssay')}
              </Badge>
              <Badge variant="outline" className="rounded-lg px-2 py-0.5 text-[10px] font-bold text-indigo-500 border-indigo-100 bg-indigo-50/30">
                {currentQ.difficulty_level_display || t('difficultyFallback')} (ELO {currentQ.difficulty || 1200})
              </Badge>
            </div>

            <div className="text-base font-bold text-foreground leading-relaxed">
              <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                {processMathContent(currentQ.text)}
              </ReactMarkdown>
            </div>

            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => toggleMastered(currentQ.id)}
                className={cn(
                  'rounded-xl h-8 px-3 gap-2 border transition-all',
                  currentQ.is_mastered
                    ? 'text-emerald-600 bg-emerald-50 border-emerald-100'
                    : 'text-muted-foreground border-border hover:text-emerald-500 hover:bg-emerald-50/50'
                )}
              >
                <CheckCircle2 className="h-4 w-4" />
                <span className="text-[10px] font-black uppercase tracking-widest">{currentQ.is_mastered ? t('alreadyMastered') : t('markMastered')}</span>
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => toggleFavorite(currentQ.id)}
                className={cn(
                  'rounded-xl h-8 w-8 shrink-0 border border-border transition-all',
                  currentQ.is_favorite ? 'text-amber-500 fill-amber-500 bg-amber-50' : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                )}
              >
                <Star className="h-4 w-4" />
              </Button>
            </div>

            <div className={cn('transition-opacity', currentQ.is_mastered && 'opacity-40')}>
              {currentQ.q_type === 'objective' ? (
                <div className="grid grid-cols-1 gap-2.5">
                  {currentQ.options?.map((opt: string, i: number) => (
                    <button
                      key={i}
                      disabled={currentQ.is_mastered}
                      onClick={() => setAnswers((prev) => ({ ...prev, [currentQ.id]: opt }))}
                      className={cn(
                        'w-full p-3 rounded-xl border text-left font-bold transition-all flex items-center gap-3',
                        answers[currentQ.id] === opt ? 'bg-slate-900 text-white border-slate-900 shadow-sm' : 'bg-card border-border hover:border-indigo-400 hover:bg-muted',
                        currentQ.is_mastered && 'cursor-not-allowed'
                      )}
                    >
                      <div className={cn('h-6 w-6 rounded-lg border-2 flex items-center justify-center transition-all', answers[currentQ.id] === opt ? 'border-white/20 bg-indigo-600' : 'border-border bg-muted')}>
                        <span className={cn('text-[10px] font-black', answers[currentQ.id] === opt ? 'text-white' : 'text-muted-foreground')}>
                          {String.fromCharCode(65 + i)}
                        </span>
                      </div>
                      <span className="text-xs">{opt}</span>
                    </button>
                  ))}
                </div>
              ) : (
                <textarea
                  value={answers[currentQ.id] || ''}
                  disabled={currentQ.is_mastered}
                  onChange={(e) => setAnswers((prev) => ({ ...prev, [currentQ.id]: e.target.value }))}
                  className={cn(
                    'w-full bg-muted border border-border rounded-xl p-3 min-h-[170px] font-medium text-sm focus:ring-2 focus:ring-indigo-500/20 transition-all resize-none text-foreground',
                    currentQ.is_mastered && 'cursor-not-allowed'
                  )}
                  placeholder={currentQ.is_mastered ? t('masteredPlaceholder') : t('inputPlaceholder')}
                />
              )}
            </div>
          </div>
        </div>

        <footer className="shrink-0 border-t border-border bg-background/95 backdrop-blur-md px-3 pt-2 pb-[calc(0.5rem+env(safe-area-inset-bottom))] space-y-2">
          <div className="flex justify-between items-center text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
            <span>{t('answeredProgress')}</span>
            <span className="text-foreground">{answeredCount} / {totalNeedAnswer}</span>
          </div>
          <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
            <div className="h-full bg-indigo-600 transition-all duration-300" style={{ width: `${totalNeedAnswer ? (answeredCount / totalNeedAnswer) * 100 : 100}%` }} />
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => setCurrentIdx((prev) => Math.max(0, prev - 1))} disabled={currentIdx === 0} className="h-10 rounded-xl px-3 text-xs font-bold">
              <ChevronLeft className="h-4 w-4 mr-1" />
              {t('previousQ')}
            </Button>
            {currentIdx === questions.length - 1 ? (
              <Button onClick={handleSubmit} disabled={isSubmitting} className="h-10 flex-1 rounded-xl bg-primary text-primary-foreground font-bold text-xs">
                {isSubmitting ? t('submitting') : t('submitScore')}
              </Button>
            ) : (
              <Button onClick={() => setCurrentIdx((prev) => Math.min(questions.length - 1, prev + 1))} className="h-10 flex-1 rounded-xl bg-primary text-primary-foreground font-bold text-xs">
                {t('nextQ')}
                <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            )}
          </div>
        </footer>
      </div>
    </div>
  );
};
