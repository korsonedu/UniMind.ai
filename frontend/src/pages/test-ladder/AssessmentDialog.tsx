import React from 'react';
import { useIsMobile } from '@/lib/useIsMobile';
import { useTranslation } from 'react-i18next';
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { CaretLeft, CaretRight, CheckCircle, Star, Spinner } from '@phosphor-icons/react';
import { cn, processMathContent } from '@/lib/utils';
import { MarkdownContent } from '@/components/MarkdownContent';

interface AssessmentProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  questions: any[];
  currentIdx: number;
  setCurrentIdx: React.Dispatch<React.SetStateAction<number>>;
  answers: any;
  handleSelect: (id: number, val: any) => void;
  toggleMastered: (id: number) => void;
  toggleFavorite: (id: number) => void;
  handleSubmit: () => void;
  isSubmitting: boolean;
  gradingMessage: string;
}

export const AssessmentDialog: React.FC<AssessmentProps> = ({
  open,
  onOpenChange,
  questions,
  currentIdx,
  setCurrentIdx,
  answers,
  handleSelect,
  toggleMastered,
  toggleFavorite,
  handleSubmit,
  isSubmitting,
  gradingMessage
}) => {
  const { t } = useTranslation('testLadder');
  const isMobile = useIsMobile();

  if (questions.length === 0) return null;

  const currentQ = questions[currentIdx];
  if (!currentQ) return null;

  const answeredCount = Object.keys(answers).length;
  const totalCount = questions.length;
  const progress = totalCount > 0 ? (answeredCount / totalCount) * 100 : 0;
  const isLast = currentIdx === totalCount - 1;
  const isFirst = currentIdx === 0;

  const typeLabel = currentQ.q_type === 'objective'
    ? t('assessment.questionTypes.objective')
    : currentQ.subjective_type === 'calculate'
      ? t('assessment.questionTypes.calculate')
      : currentQ.subjective_type === 'noun'
        ? t('assessment.questionTypes.noun')
        : t('assessment.questionTypes.subjective');

  const diffLabel = currentQ.difficulty_level_display || t('difficulty.normal');

  return (
    <Dialog open={open} onOpenChange={(open) => { if (!open && !isSubmitting) onOpenChange(false); }}>
      <DialogContent
        onInteractOutside={(e) => e.preventDefault()}
        className="w-[96vw] max-w-5xl rounded-2xl border-stone-200 bg-white p-0 shadow-2xl overflow-hidden flex flex-col h-[92vh] max-h-[860px] z-[var(--z-dropdown)]"
      >
        <DialogTitle className="sr-only">{t('assessment.title')}</DialogTitle>

        {/* ── Header ── */}
        <div className="px-6 py-3 border-b border-stone-100 flex items-center justify-between shrink-0 bg-white">
          <div className="flex items-center gap-2.5 min-w-0">
            <Badge className="rounded-md px-2 py-0 h-5 text-[10px] font-semibold bg-stone-100 text-stone-600 border-none hover:bg-stone-100">
              {typeLabel}
            </Badge>
            <span aria-hidden className="text-stone-300 select-none">·</span>
            <span className="text-[11px] font-medium text-stone-500 whitespace-nowrap">
              {diffLabel} · ELO {currentQ.difficulty || 1200}
            </span>
            {currentQ.knowledge_point_detail && (
              <>
                <span aria-hidden className="text-stone-300 select-none">·</span>
                <span className="text-[11px] font-medium text-stone-400 truncate">
                  {currentQ.knowledge_point_detail.name}
                </span>
              </>
            )}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => toggleMastered(currentQ.id)}
              className={cn(
                "h-7.5 px-2.5 rounded-lg text-[11px] font-medium gap-1.5 transition-colors",
                currentQ.is_mastered
                  ? "text-emerald-600 bg-emerald-50 hover:bg-emerald-100"
                  : "text-stone-400 hover:text-emerald-600 hover:bg-emerald-50/50"
              )}
            >
              <CheckCircle className="h-3.5 w-3.5" />
              {currentQ.is_mastered ? t('assessment.mastered') : t('assessment.notMastered')}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => toggleFavorite(currentQ.id)}
              className={cn(
                "h-7.5 w-7.5 rounded-lg transition-colors",
                currentQ.is_favorite
                  ? "text-amber-500 bg-amber-50 hover:bg-amber-100"
                  : "text-stone-400 hover:text-amber-500 hover:bg-amber-50/50"
              )}
            >
              <Star className={cn("h-3.5 w-3.5", currentQ.is_favorite && "fill-current")} />
            </Button>
          </div>
        </div>

        {/* ── Body ── */}
        <div className="flex-1 flex min-h-0">
          {/* ── Main Content ── */}
          <div className="flex-1 overflow-y-auto">
            <div className="px-6 md:px-10 py-6 md:py-8 max-w-2xl">
              {/* Question number */}
              <div className="flex items-baseline gap-2 mb-5">
                <span className="font-display text-[2.5rem] font-bold italic text-stone-200 leading-none select-none">
                  {(currentIdx + 1).toString().padStart(2, '0')}
                </span>
                <span className="text-xs font-medium text-stone-400">/ {totalCount}</span>
              </div>

              {/* Mastered banner */}
              {currentQ.is_mastered && (
                <div className="flex items-center gap-2 px-3 py-2 bg-emerald-50/70 border border-emerald-100 rounded-lg text-xs font-medium text-emerald-700 mb-5 -mt-3">
                  <CheckCircle className="w-3.5 h-3.5" />
                  {t('assessment.mastered')}
                </div>
              )}

              {/* Question text */}
              <div className="text-[15px] font-medium text-stone-800 leading-relaxed mb-8">
                <MarkdownContent content={processMathContent(currentQ.text)} />
              </div>

              {/* Answer area */}
              <div className={cn(currentQ.is_mastered && "pointer-events-none")}>
                {currentQ.q_type === 'objective' ? (
                  <div className="space-y-2.5">
                    {currentQ.options?.map((opt: string, i: number) => {
                      const selected = answers[currentQ.id] === opt;
                      return (
                        <button
                          key={i}
                          disabled={currentQ.is_mastered}
                          onClick={() => handleSelect(currentQ.id, opt)}
                          className={cn(
                            "w-full flex items-center gap-4 p-3.5 rounded-xl border text-left transition-all duration-200 group",
                            "active:scale-[0.995]",
                            selected
                              ? "bg-zinc-900 border-zinc-900 text-white shadow-lg shadow-zinc-900/5"
                              : "bg-white border-stone-200 hover:border-stone-400 hover:bg-stone-50/80",
                            currentQ.is_mastered && "opacity-50"
                          )}
                        >
                          <span className={cn(
                            "font-display text-lg font-bold italic w-8 h-8 rounded-lg flex items-center justify-center shrink-0 transition-colors",
                            selected
                              ? "bg-white/10 text-white"
                              : "bg-stone-100 text-stone-500 group-hover:bg-stone-200 group-hover:text-stone-700"
                          )}>
                            {String.fromCharCode(65 + i)}
                          </span>
                          <span className={cn(
                            "text-sm leading-relaxed",
                            selected ? "text-white" : "text-stone-700"
                          )}>
                            {opt}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <textarea
                    value={answers[currentQ.id] || ''}
                    disabled={currentQ.is_mastered}
                    onChange={(e) => handleSelect(currentQ.id, e.target.value)}
                    className={cn(
                      "w-full bg-stone-50 border border-stone-200 rounded-xl p-5 min-h-[220px] text-sm font-medium leading-relaxed",
                      "focus:outline-none focus:ring-2 focus:ring-zinc-900/10 focus:border-stone-400",
                      "placeholder:text-stone-400 resize-none transition-all",
                      currentQ.is_mastered && "opacity-50"
                    )}
                    placeholder={currentQ.is_mastered ? t('assessment.placeholderMastered') : t('assessment.placeholderDefault')}
                  />
                )}
              </div>
            </div>
          </div>

          {/* ── Sidebar ── */}
          <div className={cn(
            "w-52 border-l border-stone-100 bg-stone-50/60 flex flex-col shrink-0",
            isMobile ? "hidden" : "flex"
          )}>
            <div className="p-5 flex flex-col items-center flex-1">
              {/* Progress display */}
              <div className="text-center mb-3">
                <span className="font-display text-[2.75rem] font-bold text-stone-800 leading-none tabular-nums">
                  {answeredCount}
                </span>
                <span className="text-sm text-stone-400 font-medium"> / {totalCount}</span>
              </div>

              {/* Progress bar */}
              <div className="w-full h-1 bg-stone-200 rounded-full overflow-hidden mb-5">
                <div
                  className="h-full bg-zinc-800 rounded-full transition-all duration-500 ease-out"
                  style={{ width: `${progress}%` }}
                />
              </div>

              {/* Question grid */}
              <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-2.5 w-full">
                {t('assessment.questionMatrix')}
              </p>
              <div className="grid grid-cols-4 gap-1.5 w-full">
                {questions.map((q, i) => {
                  const isCurrent = i === currentIdx;
                  const isAnswered = !!answers[q.id];
                  return (
                    <button
                      key={i}
                      onClick={() => setCurrentIdx(i)}
                      className={cn(
                        "aspect-square rounded-lg text-xs font-semibold transition-all duration-200 flex items-center justify-center",
                        isCurrent && "bg-zinc-900 text-white shadow-sm scale-105",
                        !isCurrent && isAnswered && "bg-stone-200 text-stone-600 hover:bg-stone-300",
                        !isCurrent && !isAnswered && "bg-white border border-stone-200 text-stone-400 hover:border-stone-400 hover:text-stone-600"
                      )}
                    >
                      {i + 1}
                    </button>
                  );
                })}
              </div>

              {/* Sidebar stats */}
              <div className="mt-auto w-full pt-4 border-t border-stone-200 space-y-1.5">
                <div className="flex justify-between text-[10px] font-medium">
                  <span className="text-stone-400">{t('assessment.answered')}</span>
                  <span className="text-stone-700 tabular-nums">{answeredCount}</span>
                </div>
                <div className="flex justify-between text-[10px] font-medium">
                  <span className="text-stone-400">{t('assessment.notAnswered')}</span>
                  <span className="text-stone-700 tabular-nums">{totalCount - answeredCount}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ── Footer ── */}
        <div className="px-6 py-3.5 border-t border-stone-100 flex items-center justify-between shrink-0 bg-white">
          <Button
            variant="ghost"
            disabled={isFirst}
            onClick={() => setCurrentIdx(prev => prev - 1)}
            className="h-9 px-4 rounded-xl text-sm font-medium text-stone-500 hover:text-stone-900 hover:bg-stone-100 gap-1.5 transition-colors"
          >
            <CaretLeft className="h-4 w-4" />
            {t('assessment.prevQuestion')}
          </Button>

          {gradingMessage && (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-stone-50 rounded-full border border-stone-200">
              <Spinner className="h-3.5 w-3.5 animate-spin text-stone-400" />
              <span className="text-[11px] font-medium text-stone-500">{gradingMessage}</span>
            </div>
          )}

          {isLast ? (
            <Button
              onClick={handleSubmit}
              disabled={isSubmitting}
              className="h-9 px-6 rounded-xl bg-zinc-900 hover:bg-zinc-800 text-white text-sm font-semibold shadow-sm transition-all active:scale-[0.97]"
            >
              {isSubmitting ? t('assessment.submitting') : t('assessment.submit')}
            </Button>
          ) : (
            <Button
              onClick={() => setCurrentIdx(prev => prev + 1)}
              className="h-9 px-5 rounded-xl bg-zinc-900 hover:bg-zinc-800 text-white text-sm font-semibold shadow-sm transition-all active:scale-[0.97] gap-1.5"
            >
              {t('assessment.nextQuestion')}
              <CaretRight className="h-4 w-4" />
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};
