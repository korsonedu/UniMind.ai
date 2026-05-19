import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { CheckCircle2, Loader2, Sparkles, RotateCcw, ChevronRight } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
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
        className="sm:max-w-[1100px] rounded-[3rem] border-none bg-card p-0 shadow-2xl overflow-hidden flex flex-col h-[min(800px,92vh)] max-h-[92vh] z-[100]"
      >
        <DialogHeader className="p-10 pb-6 border-b border-border shrink-0 bg-card">
          <div className="flex justify-between items-center">
            <div className="space-y-1.5 text-left">
              <DialogTitle className="text-2xl font-black tracking-tight text-foreground uppercase">{t('training.title')}</DialogTitle>
              <p className="text-[11px] font-bold uppercase tracking-[0.3em] text-indigo-600 animate-pulse">Smart Evaluation Active</p>
            </div>
            <div className="px-6 py-2 bg-slate-900 rounded-2xl text-white font-mono font-bold text-sm tabular-nums shadow-xl">
              ELO {question.difficulty || 1200}
            </div>
          </div>
        </DialogHeader>

        <div ref={contentRef} className="flex-1 overflow-y-auto p-8 bg-card scrollbar-thin">
          <div className="max-w-4xl mx-auto space-y-8 text-left">
            {!showResult ? (
              <>
                <div className="space-y-4 border-b border-border pb-5">
                  <div className="flex flex-wrap items-center gap-3">
                    <Badge variant="secondary" className="rounded-lg px-2 py-0.5 text-[11px] font-black uppercase tracking-widest bg-muted text-muted-foreground border-none">
                      {question.q_type === 'objective'
                        ? t('training.questionType.objective')
                        : question.subjective_type === 'calculate'
                          ? t('training.questionType.calculate')
                          : question.subjective_type === 'noun'
                            ? t('training.questionType.noun')
                            : t('training.questionType.subjective')}
                    </Badge>
                    <Badge variant="outline" className="rounded-lg px-2 py-0.5 text-[11px] font-bold text-indigo-500 border-indigo-100 bg-indigo-50/30">
                      {question.difficulty_level_display || t('training.difficultyFallback')} (ELO {question.difficulty || 1200})
                    </Badge>
                    {question.knowledge_point_detail?.name && (
                      <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-widest">
                        {question.knowledge_point_detail.name}
                      </span>
                    )}
                  </div>
                  <div className="text-xl font-bold text-foreground leading-relaxed">
                    <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                      {processMathContent(question.text)}
                    </ReactMarkdown>
                  </div>
                </div>

                {question.q_type === 'objective' ? (
                  <div className="grid grid-cols-1 gap-3 max-w-3xl">
                    {objectiveOptions.map((opt) => (
                      <button
                        key={opt.key}
                        onClick={() => setAnswer(opt.key)}
                        className={cn(
                          "w-full p-4 rounded-2xl border text-left font-bold transition-all flex items-center gap-5 group/opt",
                          answer === opt.key
                            ? "bg-slate-900 text-white border-slate-900 shadow-xl scale-[1.01]"
                            : "bg-card border-border hover:border-indigo-400 hover:bg-muted"
                        )}
                      >
                        <div
                          className={cn(
                            "h-7 w-7 rounded-xl border-2 flex items-center justify-center transition-all shrink-0",
                            answer === opt.key
                              ? "border-white/20 bg-indigo-600"
                              : "border-border bg-muted group-hover/opt:border-indigo-200"
                          )}
                        >
                          <span className={cn("text-[11px] font-black", answer === opt.key ? "text-white" : "text-muted-foreground")}>
                            {opt.key}
                          </span>
                        </div>
                        <span className="text-sm tracking-tight whitespace-pre-wrap break-words">{opt.text}</span>
                      </button>
                    ))}
                  </div>
                ) : (
                  <textarea
                    value={answer}
                    onChange={(e) => setAnswer(e.target.value)}
                    placeholder={t('training.answerPlaceholder')}
                    className="w-full bg-muted border border-border rounded-[2rem] p-8 min-h-[260px] font-bold text-base focus:ring-4 focus:ring-indigo-500/20 transition-all placeholder:text-muted-foreground resize-none shadow-inner text-foreground"
                  />
                )}
              </>
            ) : (
              <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
                <div
                  className={cn(
                    "p-6 rounded-[2rem] border flex items-center gap-6",
                    resultData?.is_correct
                      ? "bg-emerald-50 border-emerald-100 text-emerald-700"
                      : "bg-red-50 border-red-100 text-red-700"
                  )}
                >
                  <div
                    className={cn(
                      "h-12 w-12 rounded-2xl flex items-center justify-center shrink-0 shadow-sm",
                      resultData?.is_correct ? "bg-emerald-500 text-white" : "bg-red-500 text-white"
                    )}
                  >
                    {resultData?.is_correct ? <CheckCircle2 className="w-6 h-6" /> : <RotateCcw className="w-6 h-6" />}
                  </div>
                  <div>
                    <p className="text-[11px] font-bold uppercase tracking-widest opacity-60">{t('training.resultLabel')}</p>
                    <h4 className="text-xl font-black">{resultData?.is_correct ? t('training.passed') : t('training.failed')}</h4>
                  </div>
                  <div className="ml-auto text-right">
                    <p className="text-[11px] font-bold uppercase tracking-widest opacity-60">{t('training.scoreLabel')}</p>
                    <p className="text-2xl font-black">{resultData?.score} / {resultData?.max_score}</p>
                  </div>
                </div>

                <div className="space-y-4">
                  <h5 className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground">{t('training.standardAnswer')}</h5>
                  <div className="p-8 bg-muted rounded-[2.5rem] border border-border text-sm font-medium leading-relaxed text-foreground">
                    <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                      {processMathContent(standardAnswerText)}
                    </ReactMarkdown>
                  </div>
                </div>

                <div className="space-y-4">
                  <h5 className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2">
                    <Sparkles className="w-3.5 h-3.5" /> {t('training.rationale')}
                  </h5>
                  <div className="p-8 bg-slate-900 text-slate-200 rounded-[2.5rem] text-sm leading-relaxed shadow-xl">
                    <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                      {processMathContent(rationaleText)}
                    </ReactMarkdown>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="p-8 border-t border-border flex justify-between items-center bg-card shrink-0">
          {!showResult ? (
            <>
              <Button
                variant="ghost"
                onClick={onClose}
                disabled={isSubmitting}
                className="rounded-xl h-12 px-6 font-bold text-muted-foreground hover:text-foreground"
              >
                {t('training.exit')}
              </Button>
              <Button
                onClick={handleSubmit}
                disabled={isSubmitting || !answer.trim()}
                className="rounded-2xl px-12 bg-indigo-600 text-white hover:bg-indigo-700 font-black h-14 shadow-xl shadow-indigo-100 transition-all active:scale-95"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin mr-2" />
                    {t('training.submitting')}
                  </>
                ) : (
                  <>
                    {t('training.submit')}
                    <ChevronRight className="ml-2 h-5 w-5" />
                  </>
                )}
              </Button>
            </>
          ) : (
            <div className="ml-auto flex gap-3">
              <Button variant="outline" onClick={handleReset} className="h-12 px-8 rounded-2xl font-bold border-border">
                {t('training.retry')}
              </Button>
              <Button onClick={onClose} className="h-12 px-10 rounded-2xl bg-primary text-primary-foreground font-bold">
                {t('training.complete')}
              </Button>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};
