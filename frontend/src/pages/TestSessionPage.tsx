import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { ArrowLeft, Bell, CheckCircle, CaretLeft, CaretRight, Spinner, Star } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { toast } from 'sonner';
import { cn, processMathContent, normalizeOptions } from '@/lib/utils';
import api from '@/lib/api';
import { MarkdownContent } from '@/components/MarkdownContent';
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
  const [empty, setEmpty] = useState(false);
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

  const kpId = useMemo(() => {
    const kp = searchParams.get('kp_name') || searchParams.get('kp');
    return kp || undefined;
  }, [searchParams]);

  const returnPath = searchParams.get('source') === 'xiaoyu' ? '/xiaoyu' : '/tests';
  const practiceDone = searchParams.get('source') === 'xiaoyu' && searchParams.get('practiceDone') === '1';

  useEffect(() => {
    const fetchQuestions = async () => {
      setLoading(true);
      try {
        const res = await api.get(`/quizzes/questions/?limit=${questionLimit}&preference=${preference}${kpId ? `&kp_name=${kpId}` : ''}`);
        if (!res.data?.length) {
          // 任意 preference 无题目时 fallback 到 balanced
          if (preference !== 'balanced') {
            const fallback = await api.get(`/quizzes/questions/?limit=${questionLimit}&preference=balanced${kpId ? `&kp_name=${kpId}` : ''}`);
            if (fallback.data?.length) {
              setQuestions(fallback.data.map((q: any) => ({ ...q, options: normalizeOptions(q.options) })));
              setLoading(false);
              return;
            }
          }
          setEmpty(true);
          setLoading(false);
          return;
        }
        setQuestions(res.data.map((q: any) => ({ ...q, options: normalizeOptions(q.options) })));
      } catch (e) {
        toast.error(t('loadFailed'));
        navigate(returnPath, { replace: true });
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
      navigate(returnPath, { replace: true });
      return;
    }

    setIsSubmitting(true);
    try {
      const payload = unmasteredQuestions.map((q) => ({ question_id: q.id, answer: answers[q.id] }));
      await api.post('/quizzes/submit-exam/', { answers: payload });
      toast.success(t('submitted'), { description: t('submittedDesc') });
      navigate(practiceDone ? '/xiaoyu?practiceDone=1' : returnPath, { replace: true });
    } catch (e: any) {
      toast.error(e.response?.data?.error || t('submitFailed'));
    } finally {
      setIsSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="h-full min-h-0 flex items-center justify-center bg-background">
        <Spinner className="h-7 w-7 animate-spin text-muted-foreground/50" />
      </div>
    );
  }

  if (empty) {
    return (
      <div className="h-full min-h-0 flex flex-col items-center justify-center bg-background gap-4">
        <p className="text-sm text-muted-foreground">题库中没有匹配的题目</p>
        <button onClick={() => navigate(returnPath, { replace: true })}
          className="text-sm text-primary hover:underline">
          {returnPath === '/xiaoyu' ? '回到小宇' : '返回'}
        </button>
      </div>
    );
  }

  if (!currentQ) {
    return null;
  }

  return (
    <div className="h-full min-h-0 bg-background text-foreground flex flex-col overflow-hidden">
      {/* ── Header ── */}
      <header className="h-11 shrink-0 border-b border-border px-3 flex items-center justify-between bg-card">
        <Link to="/tests">
          <Button variant="ghost" size="sm" className="h-8 px-2 rounded-lg text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted">
            <ArrowLeft className="h-4 w-4 mr-1" />
            {t('back')}
          </Button>
        </Link>
        <div className="flex items-center gap-2">
          {isMobile && (
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg text-muted-foreground/60 hover:text-muted-foreground">
                  <Bell className="h-4 w-4" />
                </Button>
              </PopoverTrigger>
              <PopoverContent side="bottom" align="end" className="w-64 rounded-2xl p-4 bg-card border-border">
                <div className="space-y-3 text-left">
                  <p className="text-[11px] font-semibold text-muted-foreground/60">{t('reminderSettings')}</p>
                  <div className="flex items-center justify-between">
                    <Label className="text-xs font-medium">{t('questionTypeReminder')}</Label>
                    <Switch
                      checked={reminderSettings.questionType}
                      onCheckedChange={(enabled) => {
                        setReminderSettings(updateLearningReminderSetting('questionType', enabled));
                      }}
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <Label className="text-xs font-medium">{t('testResultReminder')}</Label>
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
          <div className="px-2.5 py-1 rounded-md bg-muted text-muted-foreground font-medium text-xs tabular-nums">
            {currentIdx + 1} / {questions.length}
          </div>
        </div>
      </header>

      {/* ── Body ── */}
      <div className="flex-1 min-h-0 flex flex-col">
        <div className="flex-1 min-h-0 overflow-y-auto px-3 py-3">
          <div className="bg-card border border-border rounded-xl p-4 space-y-4">
            {/* Metadata row */}
            <div className="flex flex-wrap items-center gap-2">
              <Badge className="rounded-md px-2 py-0 h-5 text-[10px] font-semibold bg-muted text-muted-foreground border-none hover:bg-muted">
                {currentQ.q_type === 'objective'
                  ? t('typeObjective')
                  : currentQ.subjective_type === 'calculate'
                    ? t('typeCalculate')
                    : currentQ.subjective_type === 'noun'
                      ? t('typeNoun')
                      : t('typeEssay')}
              </Badge>
              <span className="text-[10px] font-medium text-muted-foreground">
                {currentQ.difficulty_level_display || t('difficultyFallback')} · ELO {currentQ.difficulty || 1200}
              </span>
            </div>

            {/* Question text */}
            <div className="text-sm font-medium text-foreground leading-relaxed">
              <MarkdownContent content={processMathContent(currentQ.text)} />
            </div>

            {/* Action buttons */}
            <div className="flex items-center gap-1.5">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => toggleMastered(currentQ.id)}
                className={cn(
                  'h-7.5 px-2.5 rounded-lg text-[11px] font-medium gap-1.5 transition-colors',
                  currentQ.is_mastered
                    ? 'text-emerald-600 bg-emerald-50'
                    : 'text-muted-foreground/60 hover:text-emerald-600 hover:bg-emerald-50/50'
                )}
              >
                <CheckCircle className="h-3.5 w-3.5" />
                {currentQ.is_mastered ? t('alreadyMastered') : t('markMastered')}
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => toggleFavorite(currentQ.id)}
                className={cn(
                  'h-7.5 w-7.5 rounded-lg transition-colors',
                  currentQ.is_favorite ? 'text-amber-500 bg-amber-50' : 'text-muted-foreground/60 hover:text-amber-500 hover:bg-amber-50/50'
                )}
              >
                <Star className={cn('h-3.5 w-3.5', currentQ.is_favorite && 'fill-current')} />
              </Button>
            </div>

            {/* Mastered banner */}
            {currentQ.is_mastered && (
              <div className="flex items-center gap-2 px-3 py-2 bg-emerald-50/70 dark:bg-emerald-950/30 border border-emerald-100 dark:border-emerald-800/40 rounded-lg text-xs font-medium text-emerald-700 dark:text-emerald-400">
                <CheckCircle className="w-3.5 h-3.5" /> {t('alreadyMastered')}
              </div>
            )}

            {/* Answer area */}
            <div className={cn(currentQ.is_mastered && 'pointer-events-none')}>
              {currentQ.q_type === 'objective' ? (
                <div className="space-y-2">
                  {currentQ.options?.map((opt: string, i: number) => {
                    const selected = answers[currentQ.id] === opt;
                    return (
                      <button
                        key={i}
                        disabled={currentQ.is_mastered}
                        onClick={() => setAnswers((prev) => ({ ...prev, [currentQ.id]: opt }))}
                        className={cn(
                          'w-full flex items-center gap-3 p-3 rounded-xl border text-left transition-all duration-200 active:scale-[0.995]',
                          selected
                            ? 'bg-primary border-primary text-primary-foreground shadow-sm'
                            : 'bg-card border-border hover:border-primary/40 active:bg-muted/50',
                          currentQ.is_mastered && 'opacity-50'
                        )}
                      >
                        <span className={cn(
                          'font-display text-base font-bold italic w-7 h-7 rounded-lg flex items-center justify-center shrink-0 transition-colors',
                          selected ? 'bg-primary-foreground/10 text-primary-foreground' : 'bg-muted text-muted-foreground'
                        )}>
                          {String.fromCharCode(65 + i)}
                        </span>
                        <span className={cn('text-[13px] leading-snug', selected ? 'text-white' : 'text-foreground/80')}>
                          <MarkdownContent content={processMathContent(opt)} />
                        </span>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <textarea
                  value={answers[currentQ.id] || ''}
                  disabled={currentQ.is_mastered}
                  onChange={(e) => setAnswers((prev) => ({ ...prev, [currentQ.id]: e.target.value }))}
                  className={cn(
                    'w-full bg-muted/50 border border-border rounded-xl p-4 min-h-[180px] text-sm font-medium leading-relaxed',
                    'focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-border',
                    'placeholder:text-muted-foreground/60 resize-none transition-all text-foreground',
                    currentQ.is_mastered && 'opacity-50'
                  )}
                  placeholder={currentQ.is_mastered ? t('masteredPlaceholder') : t('inputPlaceholder')}
                />
              )}
            </div>
          </div>
        </div>

        {/* ── Footer ── */}
        <footer className="shrink-0 border-t border-border bg-card px-3 pt-2.5 pb-[calc(0.5rem+env(safe-area-inset-bottom))] space-y-2.5">
          <div className="flex justify-between items-center">
            <span className="text-[10px] font-medium text-muted-foreground/60">{t('answeredProgress')}</span>
            <span className="text-[11px] font-semibold text-foreground/80 tabular-nums">{answeredCount} / {totalNeedAnswer}</span>
          </div>
          <div className="h-1 w-full bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-all duration-300"
              style={{ width: `${totalNeedAnswer ? (answeredCount / totalNeedAnswer) * 100 : 100}%` }}
            />
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              onClick={() => setCurrentIdx((prev) => Math.max(0, prev - 1))}
              disabled={currentIdx === 0}
              className="h-9 rounded-xl px-3 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted"
            >
              <CaretLeft className="h-4 w-4 mr-1" />
              {t('previousQ')}
            </Button>
            {currentIdx === questions.length - 1 ? (
              <Button
                onClick={handleSubmit}
                disabled={isSubmitting}
                className="h-9 flex-1 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold"
              >
                {isSubmitting ? t('submitting') : t('submitScore')}
              </Button>
            ) : (
              <Button
                onClick={() => setCurrentIdx((prev) => Math.min(questions.length - 1, prev + 1))}
                className="h-9 flex-1 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold"
              >
                {t('nextQ')}
                <CaretRight className="h-4 w-4 ml-1" />
              </Button>
            )}
          </div>
        </footer>
      </div>
    </div>
  );
};
