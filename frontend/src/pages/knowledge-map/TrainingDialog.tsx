import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { CheckCircle, Spinner, Sparkle, ArrowCounterClockwise, CaretRight } from '@phosphor-icons/react';
import { MarkdownContent } from '@/components/MarkdownContent';
import { cn, processMathContent } from '@/lib/utils';
import api from '@/lib/api';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';

interface KnowledgeTrainingDialogProps {
  question: any;
  onClose: () => void;
  onSuccess?: () => void;
}

const normalizeObjectiveOptions = (rawOptions: any): Array<{ key: string; text: string }> => {
  if (Array.isArray(rawOptions)) {
    return rawOptions
      .slice(0, 4)
      .map((value, idx) => ({
        key: String.fromCharCode(65 + idx),
        text: String(value ?? '').trim(),
      }))
      .filter((item) => item.text);
  }

  if (rawOptions && typeof rawOptions === 'object') {
    const options = Object.entries(rawOptions)
      .map(([key, value]) => ({
        key: String(key || '').trim().toUpperCase().slice(0, 1),
        text: String(value ?? '').trim(),
      }))
      .filter((item) => ['A', 'B', 'C', 'D'].includes(item.key) && item.text);
    options.sort((a, b) => a.key.localeCompare(b.key));
    return options;
  }

  return [];
};

export const KnowledgeTrainingDialog: React.FC<KnowledgeTrainingDialogProps> = ({
  question,
  onClose,
  onSuccess
}) => {
  const { t } = useTranslation('knowledgeMap');
  const [answer, setAnswer] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showResult, setShowResult] = useState(false);
  const [resultData, setResultData] = useState<any>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  const objectiveOptions = useMemo(
    () => normalizeObjectiveOptions(question?.options),
    [question?.options]
  );

  useEffect(() => {
    setAnswer('');
    setIsSubmitting(false);
    setShowResult(false);
    setResultData(null);
  }, [question?.id]);

  useEffect(() => {
    if (contentRef.current) contentRef.current.scrollTop = 0;
  }, [question?.id, showResult]);

  const standardAnswerText = useMemo(() => {
    if (!showResult) return '';
    const modelAnswer = String(resultData?.analysis || '').trim();
    if (modelAnswer) return modelAnswer;
    return String(question?.ai_answer || question?.correct_answer || t('training.fallbackStandardAnswer')).trim();
  }, [question?.ai_answer, question?.correct_answer, resultData?.analysis, showResult, t]);

  const rationaleText = useMemo(() => {
    if (!showResult) return '';
    const rationale = String(resultData?.feedback || '').trim();
    if (rationale) return rationale;
    return t('training.fallbackRationale');
  }, [resultData?.feedback, showResult, t]);

  const handleSubmit = async () => {
    if (!answer.trim()) return toast.error(t('training.emptyAnswer'));

    setIsSubmitting(true);
    try {
      const payload = [{ question_id: question.id, answer: answer }];
      await api.post('/quizzes/submit-exam/', { answers: payload });
      toast.success(t('training.submitSuccess'));
      if (onSuccess) onSuccess();
      onClose();
    } catch (e: any) {
      toast.error(e.response?.data?.error || t('training.submitFailed'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReset = () => {
    setAnswer('');
    setShowResult(false);
    setResultData(null);
  };

  if (!question) return null;

  return (
    <Dialog open={!!question} onOpenChange={(open) => { if (!open && !isSubmitting) onClose(); }}>
      <DialogContent
        onInteractOutside={(e) => e.preventDefault()}
        className="max-w-3xl rounded-2xl border-stone-200 bg-white p-0 shadow-2xl overflow-hidden flex flex-col h-[min(800px,92vh)] max-h-[92vh] z-[var(--z-dropdown)]"
      >
        <DialogTitle className="sr-only">{t('training.title')}</DialogTitle>

        {/* ── Header ── */}
        <div className="px-6 py-3 border-b border-stone-100 flex items-center justify-between shrink-0 bg-white">
          <div className="flex items-center gap-2.5 min-w-0">
            <Badge className="rounded-md px-2 py-0 h-5 text-[10px] font-semibold bg-stone-100 text-stone-600 border-none hover:bg-stone-100">
              {question.q_type === 'objective'
                ? t('training.questionType.objective')
                : question.subjective_type === 'calculate'
                  ? t('training.questionType.calculate')
                  : question.subjective_type === 'noun'
                    ? t('training.questionType.noun')
                    : t('training.questionType.subjective')}
            </Badge>
            <span aria-hidden className="text-stone-300 select-none">·</span>
            <span className="text-[11px] font-medium text-stone-500 whitespace-nowrap">
              {question.difficulty_level_display || t('training.difficultyFallback')} · ELO {question.difficulty || 1200}
            </span>
            {question.knowledge_point_detail?.name && (
              <>
                <span aria-hidden className="text-stone-300 select-none">·</span>
                <span className="text-[11px] font-medium text-stone-400 truncate">
                  {question.knowledge_point_detail.name}
                </span>
              </>
            )}
          </div>
          <div className="px-3 py-1 bg-stone-100 rounded-lg">
            <span className="font-display text-sm font-bold text-stone-600 italic tabular-nums">
              ELO {question.difficulty || 1200}
            </span>
          </div>
        </div>

        {/* ── Body ── */}
        <div ref={contentRef} className="flex-1 overflow-y-auto">
          <div className="px-8 py-6 max-w-2xl mx-auto">
            {!showResult ? (
              <>
                {/* Question text */}
                <div className="text-[15px] font-medium text-stone-800 leading-relaxed mb-8">
                  <MarkdownContent content={processMathContent(question.text)} />
                </div>

                {/* Answer area */}
                {question.q_type === 'objective' ? (
                  <div className="space-y-2.5">
                    {objectiveOptions.map((opt) => (
                      <button
                        key={opt.key}
                        onClick={() => setAnswer(opt.key)}
                        className={cn(
                          "w-full flex items-center gap-4 p-3.5 rounded-xl border text-left transition-all duration-200 group",
                          "active:scale-[0.995]",
                          answer === opt.key
                            ? "bg-zinc-900 border-zinc-900 text-white shadow-lg shadow-zinc-900/5"
                            : "bg-white border-stone-200 hover:border-stone-400 hover:bg-stone-50/80"
                        )}
                      >
                        <span className={cn(
                          "font-display text-lg font-bold italic w-8 h-8 rounded-lg flex items-center justify-center shrink-0 transition-colors",
                          answer === opt.key
                            ? "bg-white/10 text-white"
                            : "bg-stone-100 text-stone-500 group-hover:bg-stone-200 group-hover:text-stone-700"
                        )}>
                          {opt.key}
                        </span>
                        <span className={cn(
                          "text-sm leading-relaxed whitespace-pre-wrap break-words",
                          answer === opt.key ? "text-white" : "text-stone-700"
                        )}>
                          {opt.text}
                        </span>
                      </button>
                    ))}
                  </div>
                ) : (
                  <textarea
                    value={answer}
                    onChange={(e) => setAnswer(e.target.value)}
                    placeholder={t('training.answerPlaceholder')}
                    className="w-full bg-stone-50 border border-stone-200 rounded-xl p-5 min-h-[260px] text-sm font-medium leading-relaxed focus:outline-none focus:ring-2 focus:ring-zinc-900/10 focus:border-stone-400 placeholder:text-stone-400 resize-none transition-all text-stone-800"
                  />
                )}
              </>
            ) : (
              <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
                {/* Result status */}
                <div className={cn(
                  "p-5 rounded-xl border flex items-center gap-5",
                  resultData?.is_correct
                    ? "bg-emerald-50/70 border-emerald-100 text-emerald-700"
                    : "bg-red-50/70 border-red-100 text-red-700"
                )}>
                  <div className={cn(
                    "h-10 w-10 rounded-xl flex items-center justify-center shrink-0",
                    resultData?.is_correct ? "bg-emerald-500 text-white" : "bg-red-500 text-white"
                  )}>
                    {resultData?.is_correct ? <CheckCircle className="w-5 h-5" /> : <ArrowCounterClockwise className="w-5 h-5" />}
                  </div>
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-wider opacity-60">{t('training.resultLabel')}</p>
                    <h4 className="text-lg font-bold">{resultData?.is_correct ? t('training.passed') : t('training.failed')}</h4>
                  </div>
                  <div className="ml-auto text-right">
                    <p className="text-[10px] font-semibold uppercase tracking-wider opacity-60">{t('training.scoreLabel')}</p>
                    <p className="text-xl font-bold tabular-nums">{resultData?.score} / {resultData?.max_score}</p>
                  </div>
                </div>

                {/* Standard answer */}
                <div className="space-y-2">
                  <h5 className="text-[10px] font-semibold uppercase tracking-wider text-stone-400">{t('training.standardAnswer')}</h5>
                  <div className="p-5 bg-stone-50 rounded-xl border border-stone-100 text-sm font-medium leading-relaxed text-stone-700">
                    <MarkdownContent content={processMathContent(standardAnswerText)} />
                  </div>
                </div>

                {/* Rationale */}
                <div className="space-y-2">
                  <h5 className="text-[10px] font-semibold uppercase tracking-wider text-stone-400 flex items-center gap-1.5">
                    <Sparkle className="w-3 h-3" /> {t('training.rationale')}
                  </h5>
                  <div className="p-5 bg-zinc-900 text-stone-200 rounded-xl text-sm leading-relaxed">
                    <MarkdownContent content={processMathContent(rationaleText)} />
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ── Footer ── */}
        <div className="px-6 py-3.5 border-t border-stone-100 flex items-center justify-between shrink-0 bg-white">
          {!showResult ? (
            <>
              <Button
                variant="ghost"
                onClick={onClose}
                disabled={isSubmitting}
                className="h-9 px-4 rounded-xl text-sm font-medium text-stone-500 hover:text-stone-900 hover:bg-stone-100"
              >
                {t('training.exit')}
              </Button>
              <Button
                onClick={handleSubmit}
                disabled={isSubmitting || !answer.trim()}
                className="h-9 px-6 rounded-xl bg-zinc-900 hover:bg-zinc-800 text-white text-sm font-semibold shadow-sm transition-all active:scale-[0.97] gap-1.5"
              >
                {isSubmitting ? (
                  <>
                    <Spinner className="w-4 h-4 animate-spin" />
                    {t('training.submitting')}
                  </>
                ) : (
                  <>
                    {t('training.submit')}
                    <CaretRight className="h-4 w-4" />
                  </>
                )}
              </Button>
            </>
          ) : (
            <div className="ml-auto flex gap-2.5">
              <Button
                variant="outline"
                onClick={handleReset}
                className="h-9 px-5 rounded-xl text-sm font-medium border-stone-200 text-stone-600 hover:bg-stone-50 hover:text-stone-900"
              >
                {t('training.retry')}
              </Button>
              <Button
                onClick={onClose}
                className="h-9 px-5 rounded-xl bg-zinc-900 hover:bg-zinc-800 text-white text-sm font-semibold"
              >
                {t('training.complete')}
              </Button>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};
