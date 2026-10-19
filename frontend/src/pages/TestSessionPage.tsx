import { formatApiErrorToast } from '@/lib/apiError';
import type { QuizQuestion } from '@/types/api';
import '@/styles/practice.css';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { ArrowLeft, Bell, CheckCircle, CaretLeft, CaretRight, Spinner, Star } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
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
import { AssessmentDialog } from './test-ladder/AssessmentDialog';
import { useLearningSession } from '@/hooks/useLearningSession';

const hasAnswer = (val: unknown) => {
  if (typeof val === 'string') return val.trim().length > 0;
  return val !== null && val !== undefined && val !== '';
};

export const TestSessionPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [questions, setQuestions] = useState<QuizQuestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [empty, setEmpty] = useState(false);
  const [reminderSettings, setReminderSettings] = useState<LearningReminderSettings>(getLearningReminderSettings());
  const lastTypeReminderQidRef = useRef<number | null>(null);

  useLearningSession({ enabled: isMobile && !loading && !isSubmitting && questions.length > 0,
    kind: 'practice', questionIds: questions.map(question => question.id) });

  const questionLimit = useMemo(() => {
    const raw = Number.parseInt(searchParams.get('count') || '5', 10);
    if (!Number.isFinite(raw)) return 5;
    return Math.max(1, Math.min(raw, 50));
  }, [searchParams]);

  const preference = useMemo(() => {
    const p = searchParams.get('preference') || 'balanced';
    return ['balanced', 'new_first', 'review_first'].includes(p) ? p : 'balanced';
  }, [searchParams]);

  const requestParams = useMemo(() => {
    const params = new URLSearchParams({ limit: String(questionLimit), preference });
    for (const key of ['kp', 'kp_name', 'sub_ids', 'difficulty_level', 'ids']) {
      const value = searchParams.get(key);
      if (value) params.set(key, value);
    }
    return params.toString();
  }, [searchParams, questionLimit, preference]);
  const returnPath = searchParams.get('source') === 'xiaoyu' ? '/xiaoyu' : searchParams.has('ids') ? '/tests/review' : '/tests';
  const practiceDone = searchParams.get('source') === 'xiaoyu' && searchParams.get('practiceDone') === '1';

  useEffect(() => {
    const controller = new AbortController();
    const fetchQuestions = async () => {
      setLoading(true);
      setEmpty(false);
      try {
        let response = await api.get(`/quizzes/questions/?${requestParams}`, { signal: controller.signal });
        if (!response.data?.length && preference !== 'balanced' && !searchParams.has('ids')) {
          const fallback = new URLSearchParams(requestParams);
          fallback.set('preference', 'balanced');
          response = await api.get(`/quizzes/questions/?${fallback}`, { signal: controller.signal });
        }
        setEmpty(!response.data?.length);
        setQuestions((response.data || []).map((q: QuizQuestion) => ({ ...q, options: normalizeOptions(q.options) })));
        setAnswers({});
        setCurrentIdx(0);
      } catch {
        if (!controller.signal.aborted) { toast.error('题目加载失败'); navigate(returnPath, { replace: true }); }
      } finally { if (!controller.signal.aborted) setLoading(false); }
    };
    fetchQuestions();
    return () => controller.abort();
  }, [navigate, requestParams, preference, returnPath, searchParams]);

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
      ? '客观选择'
      : currentQ.subjective_type === 'calculate'
        ? '主观计算'
        : currentQ.subjective_type === 'noun'
          ? '名词解释'
          : '主观论述';

    sendLearningReminder('题型提醒', `当前题型：${typeLabel}`);
  }, [currentQ, isMobile, reminderSettings.questionType]);

  const toggleFavorite = async (qId: number) => {
    try {
      const res = await api.post('/quizzes/favorite/toggle/', { question_id: qId });
      setQuestions((prev) => prev.map((q) => (q.id === qId ? { ...q, is_favorite: res.data.is_favorite } : q)));
      toast.success(res.data.is_favorite ? '已加入收藏' : '已取消收藏');
    } catch {
      toast.error('操作失败');
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
        toast.success('已标记掌握');
      }
    } catch {
      toast.error('操作失败');
    }
  };

  const handleSubmit = async () => {
    const unmasteredQuestions = questions.filter((q) => !q.is_mastered);
    const validAnswers = unmasteredQuestions.filter((q) => hasAnswer(answers[q.id]));

    if (unmasteredQuestions.length > 0 && validAnswers.length < unmasteredQuestions.length) {
      toast.error(`请完成所有题目 (${validAnswers.length}/${unmasteredQuestions.length})`);
      return;
    }

    if (unmasteredQuestions.length === 0) {
      toast.info('练习已结束');
      navigate(returnPath, { replace: true });
      return;
    }

    setIsSubmitting(true);
    try {
      const payload = unmasteredQuestions.map((q) => ({ question_id: q.id, answer: answers[q.id] }));
      await api.post('/quizzes/submit-exam/', { answers: payload });
      toast.success('试卷已提交 AI 批改', { description: '完成后请在通知中心查看报告。' });
      navigate(practiceDone ? '/xiaoyu?practiceDone=1' : returnPath, { replace: true });
    } catch (e: unknown) {
      toast.error(formatApiErrorToast(e, '提交失败'));
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

  if (!isMobile) {
    return (
      <AssessmentDialog
        open
        onOpenChange={() => navigate(returnPath, { replace: true })}
        questions={questions}
        currentIdx={currentIdx}
        setCurrentIdx={setCurrentIdx}
        answers={answers}
        handleSelect={(id, value) => setAnswers(prev => ({ ...prev, [id]: value }))}
        toggleMastered={toggleMastered}
        toggleFavorite={toggleFavorite}
        handleSubmit={handleSubmit}
        isSubmitting={isSubmitting}
        gradingMessage={isSubmitting ? '正在提交…' : ''}
      />
    );
  }

  return (
    <div className="um-practice-session h-full min-h-0 bg-background text-foreground flex flex-col overflow-hidden">
      {/* ── Header ── */}
      <header className="h-11 shrink-0 border-b border-border px-3 flex items-center justify-between bg-card">
        <Link to={returnPath}>
          <Button variant="ghost" size="sm" className="h-8 px-2 rounded-lg text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted">
            <ArrowLeft className="h-4 w-4 mr-1" />
            返回
          </Button>
        </Link>
        <div className="flex items-center gap-2">
          {isMobile && (
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="ghost" size="icon" aria-label="提醒设置" className="h-8 w-8 rounded-lg text-muted-foreground/60 hover:text-muted-foreground">
                  <Bell className="h-4 w-4" />
                </Button>
              </PopoverTrigger>
              <PopoverContent side="bottom" align="end" className="w-64 rounded-2xl p-4 bg-card border-border">
                <div className="space-y-3 text-left">
                  <p className="text-[11px] font-semibold text-muted-foreground/60">提醒设置</p>
                  <div className="flex items-center justify-between">
                    <Label className="text-xs font-medium">题型提醒</Label>
                    <Switch
                      checked={reminderSettings.questionType}
                      onCheckedChange={(enabled) => {
                        setReminderSettings(updateLearningReminderSetting('questionType', enabled));
                      }}
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <Label className="text-xs font-medium">做题结果提醒</Label>
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
              <span className="text-xs text-muted-foreground">
                {currentQ.q_type === 'objective'
                  ? '客观选择'
                  : currentQ.subjective_type === 'calculate'
                    ? '主观计算'
                    : currentQ.subjective_type === 'noun'
                      ? '名词解释'
                      : '主观论述'}
              </span>
              <span className="text-[10px] font-medium text-muted-foreground">
                {currentQ.difficulty_level_display || '适当'} · ELO {currentQ.difficulty || 1200}
              </span>
            </div>

            {/* Question text */}
            <div className="text-[15px] font-normal text-foreground leading-relaxed">
              <MarkdownContent content={processMathContent(currentQ.text)} />
            </div>

            {/* Action buttons */}
            <div className="flex items-center gap-1.5">
              <Button
                variant="ghost"
                size="sm"
                aria-pressed={!!currentQ.is_mastered}
                onClick={() => toggleMastered(currentQ.id)}
                className={cn(
                  'h-7.5 px-2.5 rounded-lg text-[11px] font-medium gap-1.5 transition-colors',
                  currentQ.is_mastered ? 'text-primary bg-primary/10' : 'text-muted-foreground hover:bg-muted'
                )}
              >
                <CheckCircle className="h-3.5 w-3.5" />
                {currentQ.is_mastered ? '已掌握' : '标记掌握'}
              </Button>
              <Button
                variant="ghost"
                size="icon"
                aria-label={currentQ.is_favorite ? '取消收藏' : '收藏题目'}
                aria-pressed={!!currentQ.is_favorite}
                onClick={() => toggleFavorite(currentQ.id)}
                className={cn(
                  'h-7.5 w-7.5 rounded-lg transition-colors',
                  currentQ.is_favorite ? 'text-primary bg-primary/10' : 'text-muted-foreground hover:bg-muted'
                )}
              >
                <Star className={cn('h-3.5 w-3.5', currentQ.is_favorite && 'fill-current')} />
              </Button>
            </div>

            {/* Mastered banner */}
            {currentQ.is_mastered && (
              <div className="flex items-center gap-2 py-2 text-xs text-primary">
                <CheckCircle className="w-3.5 h-3.5" /> 已掌握
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
                        disabled={currentQ.is_mastered || isSubmitting}
                        aria-pressed={selected}
                        onClick={() => setAnswers((prev) => ({ ...prev, [currentQ.id]: opt }))}
                        className={cn(
                          'w-full flex items-start gap-3 p-3 rounded-lg border text-left transition-colors duration-150',
                          selected
                            ? 'bg-primary border-primary text-primary-foreground shadow-sm'
                            : 'bg-card border-border hover:border-primary/40 active:bg-muted/50',
                          currentQ.is_mastered && 'opacity-50'
                        )}
                      >
                        <span className="um-practice-option-letter">
                          {String.fromCharCode(65 + i)}
                        </span>
                        <div className="min-w-0 flex-1 text-[13px] leading-relaxed">
                          <MarkdownContent content={processMathContent(opt)} />
                        </div>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <textarea
                  aria-label="作答内容"
                  value={answers[currentQ.id] || ''}
                  disabled={currentQ.is_mastered || isSubmitting}
                  onChange={(e) => setAnswers((prev) => ({ ...prev, [currentQ.id]: e.target.value }))}
                  className={cn(
                    'w-full bg-muted/50 border border-border rounded-xl p-4 min-h-[180px] text-sm font-medium leading-relaxed',
                    'focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-border',
                    'placeholder:text-muted-foreground/60 resize-none transition-all text-foreground',
                    currentQ.is_mastered && 'opacity-50'
                  )}
                  placeholder={currentQ.is_mastered ? '该题已标记掌握，无需填写答案...' : '在此输入你的分析或计算过程...'}
                />
              )}
            </div>
          </div>
        </div>

        {/* ── Footer ── */}
        <footer className="shrink-0 border-t border-border bg-card px-3 pt-2.5 pb-[calc(0.5rem+env(safe-area-inset-bottom))] space-y-2.5">
          <div className="flex justify-between items-center">
            <span className="text-[10px] font-medium text-muted-foreground/60">已答进度</span>
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
              上一题
            </Button>
            {currentIdx === questions.length - 1 ? (
              <Button
                onClick={handleSubmit}
                disabled={isSubmitting}
                className="h-9 flex-1 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold"
              >
                {isSubmitting ? '提交中...' : '提交评分'}
              </Button>
            ) : (
              <Button
                onClick={() => setCurrentIdx((prev) => Math.min(questions.length - 1, prev + 1))}
                className="h-9 flex-1 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold"
              >
                下一题
                <CaretRight className="h-4 w-4 ml-1" />
              </Button>
            )}
          </div>
        </footer>
      </div>
    </div>
  );
};
