import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { ChevronLeft, ChevronRight, CheckCircle2, Star, Loader2 } from 'lucide-react';
import { cn, processMathContent } from '@/lib/utils';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

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
  const currentQ = questions[currentIdx];
  const { t } = useTranslation('testLadder');
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const media = window.matchMedia('(max-width: 767px)');
    const sync = () => setIsMobile(media.matches);
    sync();
    media.addEventListener('change', sync);
    return () => media.removeEventListener('change', sync);
  }, []);

  return (
    <Dialog open={open} onOpenChange={(open) => { if (!open && !isSubmitting) onOpenChange(false); }}>
      <DialogContent
        onInteractOutside={(e) => e.preventDefault()}
        className="w-[96vw] sm:max-w-[1200px] rounded-2xl md:rounded-[3rem] border-none bg-card p-0 shadow-2xl overflow-hidden flex flex-col h-[92vh] md:h-[800px] z-[100]"
      >
        {questions.length > 0 && currentQ && (
          <>
            <DialogHeader className="p-4 md:p-10 md:pb-6 border-b border-border shrink-0 bg-card">
              <div className="flex flex-col md:flex-row justify-between md:items-center gap-3">
                <div className="space-y-1.5 text-left">
                  <DialogTitle className="text-xl md:text-2xl font-black tracking-tight text-foreground uppercase">{t('assessment.title')}</DialogTitle>
                  <p className="text-[11px] font-bold uppercase tracking-[0.3em] text-indigo-600 animate-pulse">Smart Evaluation Active</p>
                </div>
                <div className="self-start md:self-auto px-4 md:px-6 py-2 bg-slate-900 rounded-xl md:rounded-2xl text-white font-mono font-bold text-sm tabular-nums shadow-sm">
                  {currentIdx + 1} / {questions.length}
                </div>
              </div>
            </DialogHeader>

            <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
              <div className="flex-1 overflow-y-auto p-4 md:p-8 md:pt-1 bg-card scrollbar-thin md:border-r border-border">
                <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-500">
                  <div className="space-y-4">
                    <div className="flex flex-col md:flex-row md:items-center justify-between border-b border-border pb-4 gap-3">
                      <div className="flex flex-wrap items-center gap-2 md:gap-3">
                        <Badge variant="secondary" className="rounded-lg px-2 py-0.5 text-[11px] font-black uppercase tracking-widest bg-muted text-muted-foreground border-none">
                          {currentQ.q_type === 'objective' ? t('assessment.questionTypes.objective') :
                            currentQ.subjective_type === 'calculate' ? t('assessment.questionTypes.calculate') :
                              currentQ.subjective_type === 'noun' ? t('assessment.questionTypes.noun') : t('assessment.questionTypes.subjective')}
                        </Badge>
                        <Badge variant="outline" className="rounded-lg px-2 py-0.5 text-[11px] font-bold text-indigo-500 border-indigo-100 bg-indigo-50/30">
                          {currentQ.difficulty_level_display || t('difficulty.normal')} (ELO {currentQ.difficulty || 1200})
                        </Badge>
                        {currentQ.knowledge_point_detail && (
                          <div className="flex items-center gap-2 ml-2">
                            <div className="h-1 w-1 rounded-full bg-muted-foreground/50" />
                            <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-widest">{currentQ.knowledge_point_detail.name}</span>
                          </div>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <Button 
                          variant="ghost" 
                          size="sm" 
                          onClick={() => toggleMastered(currentQ.id)} 
                          className={cn(
                            "rounded-xl h-9 px-3 gap-2 border transition-all", 
                            currentQ.is_mastered 
                              ? "text-emerald-600 bg-emerald-50 border-emerald-100" 
                              : "text-muted-foreground border-border hover:text-emerald-500 hover:bg-emerald-50/50"
                          )}
                        >
                          <CheckCircle2 className="h-4 w-4" />
                          <span className="text-[11px] font-black uppercase tracking-widest">{currentQ.is_mastered ? t('assessment.mastered') : t('assessment.notMastered')}</span>
                        </Button>
                        <Button variant="ghost" size="icon" onClick={() => toggleFavorite(currentQ.id)} className={cn("rounded-xl h-9 w-9 shrink-0 border border-border transition-all", currentQ.is_favorite ? "text-amber-500 fill-amber-500 bg-amber-50" : "text-muted-foreground hover:text-foreground hover:bg-muted")}>
                          <Star className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>

                    <div className="flex items-start gap-4 md:gap-8 relative mt-2 text-left">
                      <span className="text-6xl font-black text-muted-foreground/20 tabular-nums select-none absolute -left-4 -top-4 -z-10 opacity-50">{(currentIdx + 1).toString().padStart(2, '0')}</span>
                      <div className="flex-1 pt-0 min-w-0">
                        <div className="text-base md:text-xl font-bold text-foreground leading-relaxed text-left">
                          <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                            {processMathContent(currentQ.text)}
                          </ReactMarkdown>
                        </div>
                      </div>
                    </div>

                    <div className={cn("mt-4 transition-opacity", currentQ.is_mastered && "opacity-40")}>
                      {currentQ.q_type === 'objective' ? (
                        <div className="grid grid-cols-1 gap-3 max-w-3xl">
                          {currentQ.options?.map((opt: string, i: number) => (
                            <button
                              key={i}
                              disabled={currentQ.is_mastered}
                              onClick={() => handleSelect(currentQ.id, opt)}
                              className={cn(
                                "w-full p-3 md:p-4 rounded-xl md:rounded-2xl border text-left font-bold transition-all flex items-center gap-3 md:gap-5 group/opt",
                                answers[currentQ.id] === opt ? "bg-slate-900 text-white border-slate-900 shadow scale-[1.01]" : "bg-card border-border hover:border-indigo-400 hover:bg-muted",
                                currentQ.is_mastered && "cursor-not-allowed"
                              )}
                            >
                              <div className={cn("h-7 w-7 rounded-xl border-2 flex items-center justify-center transition-all", answers[currentQ.id] === opt ? "border-white/20 bg-indigo-600" : "border-border bg-muted group-hover/opt:border-indigo-200")}>
                                <span className={cn("text-[11px] font-black", answers[currentQ.id] === opt ? "text-white" : "text-muted-foreground")}>{String.fromCharCode(65 + i)}</span>
                              </div>
                              <span className="text-xs md:text-sm tracking-tight">{opt}</span>
                            </button>
                          ))}
                        </div>
                      ) : (
                        <div className="max-w-4xl space-y-6 text-left">
                          <textarea
                            value={answers[currentQ.id] || ''}
                            disabled={currentQ.is_mastered}
                            onChange={(e) => handleSelect(currentQ.id, e.target.value)}
                            className={cn(
                              "w-full bg-muted border border-border rounded-2xl md:rounded-[2rem] p-4 md:p-8 min-h-[180px] md:min-h-[250px] font-bold text-sm md:text-base focus:ring-4 focus:ring-indigo-500/20 transition-all placeholder:text-muted-foreground resize-none shadow-inner text-foreground",
                              currentQ.is_mastered && "cursor-not-allowed"
                            )}
                            placeholder={currentQ.is_mastered ? t('assessment.placeholderMastered') : t('assessment.placeholderDefault')}
                          />
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              <div className={cn("w-full md:w-64 bg-muted/30 p-4 md:p-8 md:flex flex-col shrink-0 border-t md:border-t-0 border-border", isMobile ? "hidden" : "flex")}>
                <h5 className="text-[12px] md:text-[13px] font-bold text-muted-foreground uppercase tracking-widest mb-3 md:mb-6 text-left">{t('assessment.questionMatrix')}</h5>
                <ScrollArea className="flex-1 pr-1 md:pr-2">
                  <div className="grid grid-cols-6 md:grid-cols-4 gap-2">
                    {questions.map((q, i) => (
                      <button
                        key={i}
                        onClick={() => setCurrentIdx(i)}
                        className={cn(
                          "h-10 w-10 rounded-xl font-bold text-xs transition-all border flex items-center justify-center",
                          i === currentIdx
                            ? "bg-slate-900 text-white border-slate-900 shadow-lg scale-110 z-10"
                            : answers[q.id]
                              ? "bg-indigo-50 text-indigo-600 border-indigo-100"
                              : "bg-card border-border text-muted-foreground hover:border-muted-foreground/50"
                        )}
                      >
                        {i + 1}
                      </button>
                    ))}
                  </div>
                </ScrollArea>

                <div className="mt-8 space-y-4 pt-6 border-t border-border text-left">
                  <div className="flex justify-between items-center text-[13px] font-bold uppercase tracking-widest text-muted-foreground">
                    <span>{t('assessment.answered')}</span>
                    <span className="text-foreground">{Object.keys(answers).length} / {questions.length}</span>
                  </div>
                  <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-indigo-600 transition-all duration-500"
                      style={{ width: `${(Object.keys(answers).length / questions.length) * 100}%` }}
                    />
                  </div>
                </div>
              </div>
            </div>

              <div className="p-4 md:p-10 border-t border-border flex flex-col md:flex-row justify-between md:items-center gap-3 md:gap-0 bg-card shrink-0">
              <div className="flex items-center gap-3 md:gap-6">
                <Button variant="ghost" disabled={currentIdx === 0} onClick={() => setCurrentIdx(prev => prev - 1)} className="rounded-xl font-bold gap-2 text-muted-foreground h-10 md:h-12 px-4 md:px-6 hover:text-foreground transition-colors">
                  <ChevronLeft className="h-5 w-5" /> {t('assessment.prevQuestion')}
                </Button>
                {gradingMessage && <div className="flex items-center gap-3 px-4 py-2 bg-indigo-50 rounded-full"><Loader2 className="h-4 w-4 animate-spin text-indigo-500" /><span className="text-[11px] font-bold text-indigo-600 uppercase tracking-widest">{gradingMessage}</span></div>}
              </div>
              {currentIdx === questions.length - 1 ? (
                <Button onClick={handleSubmit} disabled={isSubmitting} className="rounded-xl md:rounded-2xl w-full md:w-auto px-8 md:px-12 bg-indigo-600 text-white hover:bg-indigo-700 font-black h-12 md:h-14 shadow transition-all active:scale-95">
                  {isSubmitting ? t('assessment.submitting') : t('assessment.submit')}
                </Button>
              ) : (
                <Button onClick={() => setCurrentIdx(prev => prev + 1)} className="rounded-xl md:rounded-2xl w-full md:w-auto px-8 md:px-12 bg-slate-900 text-white hover:bg-slate-800 font-black h-12 md:h-14 shadow-lg transition-all active:scale-95">
                  {t('assessment.nextQuestion')} <ChevronRight className="ml-2 h-5 w-5" />
                </Button>
              )}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
};
