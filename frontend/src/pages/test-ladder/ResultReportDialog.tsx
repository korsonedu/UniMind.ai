import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn, processMathContent } from '@/lib/utils';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
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
  const [isMobile, setIsMobile] = useState(false);
  const resultReminderKeyRef = useRef<string>('');

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const media = window.matchMedia('(max-width: 767px)');
    const sync = () => setIsMobile(media.matches);
    sync();
    media.addEventListener('change', sync);
    return () => media.removeEventListener('change', sync);
  }, []);

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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        onInteractOutside={(e) => e.preventDefault()}
        className="w-[96vw] sm:max-w-[1200px] rounded-2xl md:rounded-[3rem] border-none bg-card p-0 shadow-2xl overflow-hidden flex flex-col h-[92vh] md:h-[90vh] md:max-h-[920px] z-[100]"
      >
        <DialogHeader className="px-4 md:px-8 py-4 border-b border-border shrink-0 bg-card">
          <div className="flex flex-col md:flex-row justify-between md:items-center gap-3">
            <div className="space-y-0.5 text-left">
              <DialogTitle className="text-xl font-black tracking-tight text-foreground uppercase">{t('result.title')}</DialogTitle>
              <p className="text-[11px] font-bold uppercase tracking-[0.3em] text-indigo-600">Academic Audit</p>
            </div>
            {examSummary && (
              <div className="flex items-center gap-6">
                <div className="text-right">
                  <p className="text-[11px] font-bold text-muted-foreground uppercase tracking-widest">{t('result.totalScore')}</p>
                  <p className="text-lg font-black text-foreground tabular-nums">{examSummary.total_score} / {examSummary.max_score}</p>
                </div>
                <div className="h-6 w-px bg-border" />
                <div className="text-right">
                  <p className="text-[11px] font-bold text-muted-foreground uppercase tracking-widest">{t('result.eloChange')}</p>
                  <p className={cn("text-lg font-black tabular-nums", examSummary.elo_change >= 0 ? "text-emerald-500" : "text-rose-500")}>
                    {examSummary.elo_change >= 0 ? `+${examSummary.elo_change}` : examSummary.elo_change}
                  </p>
                </div>
              </div>
            )}
          </div>
        </DialogHeader>

        <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
          <div className="flex-1 overflow-y-auto p-3 md:p-4 pt-2 bg-muted/30 scrollbar-thin md:border-r border-border">
            {results.length > 0 && (
              <div className="animate-in fade-in slide-in-from-bottom-2 duration-500">
                <Card className="border border-border bg-card rounded-[2rem] overflow-hidden shadow-sm">
                  <div className="p-6 space-y-4">
                    <div className="flex justify-between items-start gap-4">
                      <div className="flex gap-3 items-start flex-1 text-left">
                        <span className="text-2xl font-black text-muted-foreground/30 tabular-nums leading-none">{(currentReportIdx + 1).toString().padStart(2, '0')}</span>
                        <div className="font-bold text-base text-foreground leading-snug">
                          <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                            {processMathContent(results[currentReportIdx].question?.text || "")}
                          </ReactMarkdown>
                        </div>
                      </div>
                      <Badge className={cn("rounded-lg px-2.5 py-0.5 font-bold shadow-sm shrink-0 text-[11px]", results[currentReportIdx].is_correct ? "bg-emerald-500 text-white" : "bg-rose-500 text-white")}>
                        {results[currentReportIdx].score} / {results[currentReportIdx].max_score} PTS
                      </Badge>
                    </div>

                    <div className="grid gap-4 pt-4 border-t border-border">
                      <div className="space-y-1 text-left">
                        <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-muted-foreground ml-1">My Response</p>
                        <div className="p-3.5 bg-muted rounded-xl border border-border text-[13px] font-medium text-foreground leading-relaxed whitespace-pre-wrap">
                          {results[currentReportIdx].user_answer || t('result.noAnswer')}
                        </div>
                      </div>
                      
                      <div className="space-y-1 text-left">
                        <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-emerald-500 ml-1">AI Feedback</p>
                        <div className="p-4 bg-emerald-500/10 rounded-xl border border-emerald-400/20 text-[14px] font-bold text-foreground leading-relaxed shadow-sm text-left">
                          <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                            {processMathContent(results[currentReportIdx].feedback)}
                          </ReactMarkdown>
                        </div>
                      </div>

                      <div className="space-y-1 text-left">
                        <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-indigo-500 ml-1">Academic Analysis</p>
                        <div className="p-6 bg-slate-900 rounded-[1.5rem] text-[14px] font-medium text-slate-200 leading-relaxed shadow-xl text-left">
                          <div className="prose prose-invert prose-sm max-w-none prose-p:leading-relaxed">
                            <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                              {processMathContent(results[currentReportIdx].analysis || results[currentReportIdx].ai_answer || "")}
                            </ReactMarkdown>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </Card>
              </div>
            )}
          </div>

          <div className={cn("w-full md:w-64 bg-muted/50 p-4 md:p-6 md:flex flex-col shrink-0 border-t md:border-t-0 border-border", isMobile ? "hidden" : "flex")}>
            <h5 className="text-[11px] font-bold text-muted-foreground uppercase tracking-widest mb-4 text-left">{t('result.assessmentMatrix')}</h5>
            <ScrollArea className="flex-1 pr-2">
              <div className="grid grid-cols-4 gap-2">
                {results.map((res, i) => (
                  <button
                    key={i}
                    onClick={() => setCurrentReportIdx(i)}
                    className={cn(
                      "h-10 w-10 rounded-xl font-bold text-xs transition-all border flex items-center justify-center relative",
                      i === currentReportIdx
                        ? "bg-slate-900 text-white border-slate-900 shadow-lg scale-110 z-10"
                        : res.is_correct
                          ? "bg-emerald-50 text-emerald-600 border-emerald-100 hover:bg-emerald-100"
                          : "bg-rose-50 text-rose-600 border-rose-100 hover:bg-rose-100"
                    )}
                  >
                    {i + 1}
                    {i === currentReportIdx && <div className="absolute -bottom-1 w-1 h-1 bg-white rounded-full" />}
                  </button>
                ))}
              </div>
            </ScrollArea>

            <div className="mt-6 space-y-3 pt-4 border-t border-border text-left">
              <div className="flex justify-between items-center text-[11px] font-bold uppercase tracking-widest text-muted-foreground">
                <span>{t('result.scoreRate')}</span>
                <span className="text-foreground">
                  {examSummary ? Math.round((examSummary.total_score / examSummary.max_score) * 100) : 0}%
                </span>
              </div>
              <div className="h-1 w-full bg-muted rounded-full overflow-hidden">
                <div
                  className="h-full bg-indigo-600 transition-all duration-500"
                  style={{ width: `${examSummary ? (examSummary.total_score / examSummary.max_score) * 100 : 0}%` }}
                />
              </div>
              <p className="text-[11px] font-medium text-muted-foreground leading-tight pt-1">
                {t('result.matrixHint')}
              </p>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};
