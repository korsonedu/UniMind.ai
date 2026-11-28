import { t, useLocale } from '@/i18n';
import { useSystemStore } from '@/store/useSystemStore';
import { formatApiErrorToast } from '@/lib/apiError';
import type { QuizQuestion } from '@/types/api';
import '@/styles/practice.css';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Bell, CaretDown, CheckCircle, CaretLeft, CaretRight, Spinner, Star } from '@phosphor-icons/react';
import { WorkspaceToolbar } from '@/components/WorkspaceToolbar';
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
import { useExamActivityStore } from '@/store/useExamActivityStore';
import { useNotesSidebarAvailability } from '@/components/WorkspaceContext';

const hasAnswer = (val: unknown) => {
  if (typeof val === 'string') return val.trim().length > 0;
  return val !== null && val !== undefined && val !== '';
};

export const TestSessionPage: React.FC = () => {
  useLocale();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { practiceCount, practicePreference } = useSystemStore();
  const [questions, setQuestions] = useState<QuizQuestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const [empty, setEmpty] = useState(false);
  const [reminderSettings, setReminderSettings] = useState<LearningReminderSettings>(getLearningReminderSettings());
  const lastTypeReminderQidRef = useRef<number | null>(null);

  useNotesSidebarAvailability(!loading && questions.length > 0);
  useLearningSession({ enabled: isMobile && !loading && !isSubmitting && questions.length > 0,
    kind: 'practice', questionIds: questions.map(question => question.id) });

  const questionLimit = useMemo(() => {
    const raw = Number.parseInt(searchParams.get('count') || (practiceCount === 'recommended' ? '5' : practiceCount), 10);
    if (!Number.isFinite(raw)) return 5;
    return Math.max(1, Math.min(raw, 50));
  }, [searchParams, practiceCount]);

  const preference = useMemo(() => {
    const p = searchParams.get('preference') || practicePreference;
    return ['balanced', 'new_first', 'review_first'].includes(p) ? p : 'balanced';
  }, [searchParams, practicePreference]);

  const requestParams = useMemo(() => {
    const params = new URLSearchParams({ limit: String(questionLimit), preference });
    for (const key of ['kp', 'kp_name', 'sub_ids', 'difficulty_level', 'ids']) {
      const value = searchParams.get(key);
      if (value) params.set(key, value);
    }
    return params.toString();
  }, [searchParams, questionLimit, preference]);
  const returnPath = searchParams.get('source') === 'xiaoyu' ? '/xiaoyu' : searchParams.has('ids') ? '/tests/review' : '/tests';

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
        if (!controller.signal.aborted) { toast.error(t('题目加载失败')); navigate(returnPath, { replace: true }); }
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
      ? t('客观选择')
      : currentQ.subjective_type === 'calculate'
        ? t('主观计算')
        : currentQ.subjective_type === 'noun'
          ? t('名词解释')
          : t('主观论述');

    sendLearningReminder(t('题型提醒'), t('当前题型：{0}', { 0: typeLabel }));
  }, [currentQ, isMobile, reminderSettings.questionType]);

  const toggleFavorite = async (qId: number) => {
    try {
      const res = await api.post('/quizzes/favorite/toggle/', { question_id: qId });
      setQuestions((prev) => prev.map((q) => (q.id === qId ? { ...q, is_favorite: res.data.is_favorite } : q)));
      toast.success(res.data.is_favorite ? t('已加入收藏') : t('已取消收藏'));
    } catch {
      toast.error(t('操作失败'));
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
        toast.success(t('已标记掌握'));
      }
    } catch {
      toast.error(t('操作失败'));
    }
  };

  const handleSubmit = async () => {
    const unmasteredQuestions = questions.filter((q) => !q.is_mastered);
    const validAnswers = unmasteredQuestions.filter((q) => hasAnswer(answers[q.id]));

    if (unmasteredQuestions.length > 0 && validAnswers.length < unmasteredQuestions.length) {
      toast.error(t('请完成所有题目 ({0}/{1})', { 0: validAnswers.length, 1: unmasteredQuestions.length }));
      return;
    }

    if (unmasteredQuestions.length === 0) {
      toast.info(t('练习已结束'));
      navigate(returnPath, { replace: true });
      return;
    }

    setIsSubmitting(true);
    try {
      const payload = unmasteredQuestions.map((q) => ({ question_id: q.id, answer: answers[q.id] }));
      const response = await api.post('/quizzes/submit-exam/', { answers: payload });
      const examId = Number(response.data?.exam_id);
      if (Number.isFinite(examId)) {
        useExamActivityStore.getState().start({
          examId,
          total: Number(response.data?.total_questions) || unmasteredQuestions.length,
        });
      }
      toast.success(t('已提交 AI 批改'));
      navigate('/tests', { replace: true });
    } catch (e: unknown) {
      toast.error(formatApiErrorToast(e, t('提交失败')));
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
        <p className="text-sm text-muted-foreground">{t('题库中没有匹配的题目')}</p>
        <button onClick={() => navigate(returnPath, { replace: true })}
          className="text-sm text-primary hover:underline">
          {returnPath === '/xiaoyu' ? t('回到小宇') : t('返回')}
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
        gradingMessage={isSubmitting ? t('正在提交…') : ''}
      />
    );
  }

  const questionTypeLabel = currentQ.q_type === 'objective'
    ? t('客观选择')
    : currentQ.subjective_type === 'calculate'
      ? t('主观计算')
      : currentQ.subjective_type === 'noun'
        ? t('名词解释')
        : t('主观论述');

  return (
    <div className="um-practice-session h-full min-h-0 flex flex-col overflow-hidden">
      {/* ── Unified Mobile Toolbar ── */}
      <WorkspaceToolbar className="um-practice-session-toolbar">
        <Popover open={navOpen} onOpenChange={setNavOpen}>
          <PopoverTrigger asChild>
            <button type="button" className="um-practice-session-progress-trigger" aria-label={t('题目导航')}>
              <span>{t('第 {0} / {1} 题', { 0: currentIdx + 1, 1: questions.length })}</span>
              <CaretDown size={13} weight="regular" className="um-m-header-caret" />
            </button>
          </PopoverTrigger>
          <PopoverContent side="bottom" align="start" sideOffset={8} className="um-practice-nav-popover">
            <div className="um-practice-nav-popover-head">
              <span>{t('题目导航')}</span>
              <span>{t('已答 {0} / {1}', { 0: answeredCount, 1: totalNeedAnswer })}</span>
            </div>
            <div className="um-practice-nav-grid" role="navigation" aria-label={t('题目列表')}>
              {questions.map((q, idx) => {
                const complete = q.is_mastered || hasAnswer(answers[q.id]);
                return (
                  <button
                    key={q.id}
                    type="button"
                    aria-current={idx === currentIdx ? 'step' : undefined}
                    data-complete={complete ? 'true' : undefined}
                    onClick={() => { setCurrentIdx(idx); setNavOpen(false); }}
                  >
                    {idx + 1}
                  </button>
                );
              })}
            </div>
          </PopoverContent>
        </Popover>
        <div className="um-practice-session-toolbar-actions">
          <Popover>
            <PopoverTrigger asChild>
              <button type="button" aria-label={t('提醒设置')} className="um-agent-icon-button um-practice-session-bell">
                <Bell size={18} />
              </button>
            </PopoverTrigger>
            <PopoverContent side="bottom" align="end" sideOffset={8} className="um-practice-popover">
              <h2>{t('提醒设置')}</h2>
              <Label>
                {t('题型提醒')}
                <Switch
                  checked={reminderSettings.questionType}
                  onCheckedChange={(enabled) => {
                    setReminderSettings(updateLearningReminderSetting('questionType', enabled));
                  }}
                />
              </Label>
              <Label>
                {t('做题结果提醒')}
                <Switch
                  checked={reminderSettings.testResult}
                  onCheckedChange={(enabled) => {
                    setReminderSettings(updateLearningReminderSetting('testResult', enabled));
                  }}
                />
              </Label>
            </PopoverContent>
          </Popover>
        </div>
      </WorkspaceToolbar>

      {/* ── Slim Progress Line ── */}
      <div className="um-practice-session-bar" aria-hidden="true">
        <div style={{ width: `${totalNeedAnswer ? (answeredCount / totalNeedAnswer) * 100 : 100}%` }} />
      </div>

      {/* ── Body ── */}
      <div className="flex-1 min-h-0 flex flex-col">
        <div className="um-practice-session-scroll flex-1 min-h-0 overflow-y-auto">
          <div className="um-practice-session-paper">
            {/* Metadata & Actions row */}
            <div className="um-practice-session-meta-row">
              <div className="um-practice-session-badges">
                <span className="um-practice-session-chip">{questionTypeLabel}</span>
                <span className="um-practice-session-chip is-muted">
                  {currentQ.difficulty_level_display || t('适当')}
                </span>
              </div>
              <div className="um-practice-session-actions">
                <button
                  type="button"
                  aria-pressed={!!currentQ.is_mastered}
                  onClick={() => toggleMastered(currentQ.id)}
                  className="um-practice-session-chip-btn"
                >
                  <CheckCircle size={14} weight={currentQ.is_mastered ? 'fill' : 'regular'} />
                  <span>{currentQ.is_mastered ? t('已掌握') : t('标记掌握')}</span>
                </button>
                <button
                  type="button"
                  aria-label={currentQ.is_favorite ? t('取消收藏') : t('收藏题目')}
                  aria-pressed={!!currentQ.is_favorite}
                  onClick={() => toggleFavorite(currentQ.id)}
                  className="um-practice-session-icon-btn"
                >
                  <Star size={15} weight={currentQ.is_favorite ? 'fill' : 'regular'} />
                </button>
              </div>
            </div>

            {/* Question text */}
            <div className="um-practice-session-stem">
              <MarkdownContent content={processMathContent(currentQ.text)} />
            </div>

            {/* Mastered banner */}
            {currentQ.is_mastered && (
              <div className="um-practice-session-mastered">
                <CheckCircle size={15} weight="fill" /> {t('该题已标记掌握，提交时将自动跳过')}
              </div>
            )}

            {/* Answer area */}
            <div className={cn('um-practice-session-answer', currentQ.is_mastered && 'pointer-events-none opacity-50')}>
              {currentQ.q_type === 'objective' ? (
                <div className="um-practice-session-options">
                  {currentQ.options?.map((opt: string, i: number) => {
                    const selected = answers[currentQ.id] === opt;
                    return (
                      <button
                        key={i}
                        type="button"
                        disabled={currentQ.is_mastered || isSubmitting}
                        aria-pressed={selected}
                        onClick={() => setAnswers((prev) => ({ ...prev, [currentQ.id]: opt }))}
                        className="um-practice-session-option"
                      >
                        <span className="um-practice-session-letter">
                          {String.fromCharCode(65 + i)}
                        </span>
                        <div className="um-practice-session-option-text">
                          <MarkdownContent content={processMathContent(opt)} />
                        </div>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <textarea
                  aria-label={t('作答内容')}
                  value={answers[currentQ.id] || ''}
                  disabled={currentQ.is_mastered || isSubmitting}
                  onChange={(e) => setAnswers((prev) => ({ ...prev, [currentQ.id]: e.target.value }))}
                  className="um-practice-session-textarea"
                  placeholder={currentQ.is_mastered ? t('该题已标记掌握，无需填写答案...') : t('在此输入你的分析或计算过程...')}
                />
              )}
            </div>
          </div>
        </div>

        {/* ── Footer ── */}
        <footer className="um-practice-session-footer">
          <button
            type="button"
            onClick={() => setCurrentIdx((prev) => Math.max(0, prev - 1))}
            disabled={currentIdx === 0}
            className="um-practice-session-prev"
          >
            <CaretLeft size={16} />
            <span>{t('上一题')}</span>
          </button>
          {currentIdx === questions.length - 1 ? (
            <button
              type="button"
              onClick={handleSubmit}
              disabled={isSubmitting}
              className="um-practice-session-next"
            >
              <span>{isSubmitting ? t('提交中...') : t('提交评分')}</span>
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setCurrentIdx((prev) => Math.min(questions.length - 1, prev + 1))}
              className="um-practice-session-next"
            >
              <span>{t('下一题')}</span>
              <CaretRight size={16} />
            </button>
          )}
        </footer>
      </div>
    </div>
  );
};
