import React, { useEffect, useRef } from 'react';
import { useIsMobile } from '@/lib/useIsMobile';
import { useTranslation } from 'react-i18next';
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn, processMathContent } from '@/lib/utils';
import { MarkdownContent } from '@/components/MarkdownContent';
import { isLearningReminderEnabled, sendLearningReminder } from '@/lib/learningReminders';

interface ResultReportProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  examSummary: any;
  results: any[];
  currentReportIdx: number;
  setCurrentReportIdx: (idx: number) => void;
}

export const ResultReportDialog: React.FC<ResultReportProps> = ({
  open,
  onOpenChange,
  examSummary,
  results,
  currentReportIdx,
  setCurrentReportIdx
}) => {
  const { t } = useTranslation('testLadder');
  const isMobile = useIsMobile();
  const resultReminderKeyRef = useRef<string>('');

  useEffect(() => {
    if (!open || !isMobile || !examSummary || !isLearningReminderEnabled('testResult')) return;
    const key = `${examSummary.total_score}-${examSummary.max_score}-${examSummary.elo_change}`;
    if (resultReminderKeyRef.current === key) return;
    resultReminderKeyRef.current = key;

    const elo = Number(examSummary.elo_change || 0);
    const eloText = elo >= 0 ? `+${elo}` : `${elo}`;
    sendLearningReminder(
      t('result.testResultReminder'),
      t('result.testResultReminderBody', { totalScore: examSummary.total_score, maxScore: examSummary.max_score, eloText })
    );
  }, [examSummary, isMobile, open]);

  if (results.length === 0) return null;

  const currentResult = results[currentReportIdx];
  if (!currentResult) return null;

  const scorePercent = examSummary
    ? Math.round((examSummary.total_score / examSummary.max_score) * 100)
    : 0;

  const correctCount = results.filter((r: any) => r.is_correct).length;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        onInteractOutside={(e) => e.preventDefault()}
        className="w-[96vw] max-w-5xl rounded-2xl border-stone-200 bg-white p-0 shadow-2xl overflow-hidden flex flex-col h-[92vh] max-h-[860px] z-[var(--z-dropdown)]"
      >
        <DialogTitle className="sr-only">{t('result.title')}</DialogTitle>

        {/* ── Header ── */}
        <div className="px-6 py-3.5 border-b border-stone-100 flex items-center justify-between shrink-0 bg-white">
          <div className="flex items-center gap-5">
            <span className="text-sm font-bold text-stone-800">{t('result.title')}</span>
            <div className="flex items-center gap-1.5 text-[10px] font-medium text-stone-400">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              {correctCount}/{results.length} {t('result.matrixHint') ? '正确' : 'correct'}
            </div>
          </div>
          {examSummary && (
            <div className="flex items-center gap-5">
              <div className="text-right">
                <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider">{t('result.totalScore')}</p>
                <p className="text-sm font-bold text-stone-800 tabular-nums">
                  {examSummary.total_score} <span className="text-stone-400 text-xs font-medium">/ {examSummary.max_score}</span>
                </p>
              </div>
              <div className="text-right">
                <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider">{t('result.eloChange')}</p>
                <p className={cn(
                  "text-sm font-bold tabular-nums font-display italic",
                  examSummary.elo_change >= 0 ? "text-emerald-600" : "text-red-500"
                )}>
                  {examSummary.elo_change >= 0 ? `+${examSummary.elo_change}` : examSummary.elo_change}
                </p>
              </div>
            </div>
          )}
        </div>

        {/* ── Body ── */}
        <div className="flex-1 flex min-h-0">
          {/* ── Main Content ── */}
          <div className="flex-1 overflow-y-auto bg-stone-50/50">
            <div className="px-6 md:px-10 py-6 md:py-8 max-w-2xl mx-auto">
              <div className="animate-in fade-in slide-in-from-bottom-2 duration-500">
                <Card className="border border-stone-200 bg-white rounded-xl overflow-hidden shadow-sm">
                  <div className="p-6 space-y-5">
                    {/* Question header */}
                    <div className="flex justify-between items-start gap-4">
                      <div className="flex gap-3 items-start flex-1 min-w-0">
                        <span className="font-display text-2xl font-bold italic text-stone-300 leading-none select-none shrink-0">
                          {(currentReportIdx + 1).toString().padStart(2, '0')}
                        </span>
                        <div className="text-sm font-medium text-stone-800 leading-relaxed">
                          <MarkdownContent content={processMathContent(currentResult.question?.text || "")} />
                        </div>
                      </div>
                      <Badge className={cn(
                        "rounded-md px-2.5 py-0.5 text-[10px] font-semibold shrink-0",
                        currentResult.is_correct
                          ? "bg-emerald-100 text-emerald-700 border-emerald-200"
                          : "bg-red-100 text-red-700 border-red-200"
                      )}>
                        {currentResult.score} / {currentResult.max_score} PTS
                      </Badge>
                    </div>

                    <div className="grid gap-4 pt-4 border-t border-stone-100">
                      {/* My Response */}
                      <div className="space-y-1.5">
                        <p className="text-[10px] font-semibold uppercase tracking-wider text-stone-400">{t('result.myResponse')}</p>
                        <div className="p-3.5 bg-stone-50 rounded-lg border border-stone-100 text-[13px] font-medium text-stone-700 leading-relaxed whitespace-pre-wrap">
                          {currentResult.user_answer || t('result.noAnswer')}
                        </div>
                      </div>

                      {/* AI Feedback */}
                      <div className="space-y-1.5">
                        <p className="text-[10px] font-semibold uppercase tracking-wider text-emerald-600">{t('result.aiFeedback')}</p>
                        <div className="p-4 bg-emerald-50/50 rounded-lg border border-emerald-100 text-[13px] font-medium text-stone-700 leading-relaxed">
                          <MarkdownContent content={processMathContent(currentResult.feedback)} />
                        </div>
                      </div>

                      {/* Academic Analysis */}
                      <div className="space-y-1.5">
                        <p className="text-[10px] font-semibold uppercase tracking-wider text-stone-400">{t('result.academicAnalysis')}</p>
                        <div className="p-5 bg-zinc-900 rounded-xl text-[13px] font-medium text-stone-200 leading-relaxed">
                          <div className="prose prose-invert prose-sm max-w-none prose-p:leading-relaxed">
                            <MarkdownContent content={processMathContent(currentResult.analysis || currentResult.ai_answer || "")} />
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </Card>
              </div>
            </div>
          </div>

          {/* ── Sidebar ── */}
          <div className={cn(
            "w-52 border-l border-stone-100 bg-white flex flex-col shrink-0",
            isMobile ? "hidden" : "flex"
          )}>
            <div className="p-5 flex flex-col items-center flex-1">
              {/* Score display */}
              <div className="text-center mb-3">
                <span className="font-display text-[2.75rem] font-bold text-stone-800 leading-none tabular-nums">
                  {scorePercent}
                </span>
                <span className="text-lg text-stone-400 font-medium">%</span>
              </div>

              {/* Progress bar */}
              <div className="w-full h-1 bg-stone-200 rounded-full overflow-hidden mb-5">
                <div
                  className={cn(
                    "h-full rounded-full transition-all duration-500 ease-out",
                    scorePercent >= 80 ? "bg-emerald-500" : scorePercent >= 60 ? "bg-amber-500" : "bg-red-500"
                  )}
                  style={{ width: `${Math.max(scorePercent, 2)}%` }}
                />
              </div>

              {/* Question grid */}
              <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-2.5 w-full">
                {t('result.assessmentMatrix')}
              </p>
              <div className="grid grid-cols-4 gap-1.5 w-full">
                {results.map((res, i) => (
                  <button
                    key={i}
                    onClick={() => setCurrentReportIdx(i)}
                    className={cn(
                      "aspect-square rounded-lg text-xs font-semibold transition-all duration-200 flex items-center justify-center relative",
                      i === currentReportIdx
                        ? "bg-zinc-900 text-white shadow-sm scale-105"
                        : res.is_correct
                          ? "bg-emerald-100 text-emerald-700 hover:bg-emerald-200"
                          : "bg-red-100 text-red-700 hover:bg-red-200"
                    )}
                  >
                    {i + 1}
                  </button>
                ))}
              </div>

              {/* Stats */}
              <div className="mt-auto w-full pt-4 border-t border-stone-100 space-y-1.5">
                <div className="flex justify-between text-[10px] font-medium">
                  <span className="text-stone-400">{t('result.scoreRate')}</span>
                  <span className="text-stone-700 tabular-nums">{scorePercent}%</span>
                </div>
                <div className="flex justify-between text-[10px] font-medium">
                  <span className="text-stone-400">正确</span>
                  <span className="text-stone-700 tabular-nums">{correctCount}/{results.length}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};
