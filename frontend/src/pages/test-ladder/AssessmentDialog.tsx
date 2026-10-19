import type { QuizQuestion } from '@/types/api';
import '@/styles/practice.css';
import React from 'react';
import { useIsMobile } from '@/lib/useIsMobile';
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from '@/components/ui/button';
import { CaretLeft, CaretRight, CheckCircle, Star, Spinner, X } from '@phosphor-icons/react';
import { processMathContent } from '@/lib/utils';
import { MarkdownContent } from '@/components/MarkdownContent';
import { useLearningSession } from '@/hooks/useLearningSession';

interface AssessmentProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  questions: QuizQuestion[];
  currentIdx: number;
  setCurrentIdx: React.Dispatch<React.SetStateAction<number>>;
  answers: Record<number, string>;
  handleSelect: (id: number, val: string) => void;
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
  const isMobile = useIsMobile();
  useLearningSession({ enabled: open && !isSubmitting && questions.length > 0,
    kind: 'practice', questionIds: questions.map(question => question.id) });

  if (questions.length === 0) return null;

  const currentQ = questions[currentIdx];
  if (!currentQ) return null;

  const totalCount = questions.length;
  const totalNeedAnswer = questions.filter(q => !q.is_mastered).length;
  const answeredCount = questions.filter(q => !q.is_mastered && typeof answers[q.id] === 'string' && answers[q.id].trim()).length;
  const progress = totalNeedAnswer ? answeredCount / totalNeedAnswer * 100 : 100;
  const isLast = currentIdx === totalCount - 1;
  const isFirst = currentIdx === 0;

  const typeLabel = currentQ.q_type === 'objective'
    ? '客观选择'
    : currentQ.subjective_type === 'calculate'
      ? '主观计算'
      : currentQ.subjective_type === 'noun'
        ? '名词解释'
        : '主观论述';

  const diffLabel = currentQ.difficulty_level_display || '适当';

  return (
    <Dialog open={open} onOpenChange={next => { if (!next && !isSubmitting) onOpenChange(false); }}>
      <DialogContent showClose={false} onInteractOutside={event => event.preventDefault()} className="um-practice-dialog">
        <DialogTitle className="sr-only">本轮练习</DialogTitle><DialogDescription className="sr-only">逐题作答，可收藏题目、标记掌握，并在完成后提交批改。</DialogDescription>
        <header className="um-practice-question-header"><div className="um-practice-question-meta"><span>{typeLabel}</span><span>{diffLabel} · ELO {currentQ.difficulty || 1200}</span>{currentQ.knowledge_point_detail && <span>{currentQ.knowledge_point_detail.name}</span>}</div><div className="um-practice-question-actions"><Button variant="ghost" aria-pressed={!!currentQ.is_mastered} onClick={() => toggleMastered(currentQ.id)} disabled={isSubmitting}><CheckCircle size={16} />{currentQ.is_mastered ? '已掌握' : '标记掌握'}</Button><Button variant="ghost" size="icon" aria-label={currentQ.is_favorite ? '取消收藏' : '收藏题目'} aria-pressed={!!currentQ.is_favorite} onClick={() => toggleFavorite(currentQ.id)} disabled={isSubmitting}><Star size={16} weight={currentQ.is_favorite ? 'fill' : 'regular'} /></Button><Button variant="ghost" size="icon" aria-label="结束本轮练习" disabled={isSubmitting} onClick={() => onOpenChange(false)}><X size={17} /></Button></div></header>
        <div className="um-practice-question-body"><div className="um-practice-question-scroll"><article className="um-practice-question"><h2>第 {currentIdx + 1} 题<span> / {totalCount}</span></h2>{currentQ.is_mastered && <p className="um-practice-mastered">已标记掌握，本轮无需作答。</p>}<div className="um-practice-question-text"><MarkdownContent content={processMathContent(currentQ.text)} /></div>
          {currentQ.q_type === 'objective' ? <div className="um-practice-options" role="group" aria-label="选择答案">{currentQ.options?.map((opt: string, index: number) => <button type="button" key={index} disabled={currentQ.is_mastered || isSubmitting} aria-pressed={answers[currentQ.id] === opt} onClick={() => handleSelect(currentQ.id, opt)}><span className="um-practice-option-letter">{String.fromCharCode(65 + index)}</span><div><MarkdownContent content={processMathContent(opt)} /></div></button>)}</div> : <textarea className="um-practice-answer" aria-label="作答内容" value={answers[currentQ.id] || ''} disabled={currentQ.is_mastered || isSubmitting} onChange={event => handleSelect(currentQ.id, event.target.value)} placeholder={currentQ.is_mastered ? '该题已标记掌握，无需填写答案。' : '输入你的分析或计算过程…'} />}
        </article></div>{!isMobile && <aside className="um-practice-question-nav" aria-label="题目导航"><p>已答 {answeredCount} / {totalNeedAnswer}</p><progress value={progress} max={100} aria-label="本轮答题进度" /><nav aria-label="跳转题目">{questions.map((q, index) => <button type="button" key={q.id} aria-label={`第 ${index + 1} 题${q.is_mastered ? '，已掌握' : answers[q.id]?.trim() ? '，已答' : '，未答'}`} aria-current={index === currentIdx ? 'step' : undefined} data-complete={!!q.is_mastered || !!answers[q.id]?.trim()} disabled={isSubmitting} onClick={() => setCurrentIdx(index)}>{index + 1}</button>)}</nav></aside>}</div>
        <footer className="um-practice-question-footer"><Button variant="ghost" disabled={isFirst || isSubmitting} onClick={() => setCurrentIdx(prev => prev - 1)}><CaretLeft size={16} />上一题</Button><span role="status">{gradingMessage ? <><Spinner size={14} className="animate-spin" />{gradingMessage}</> : `已答 ${answeredCount} / ${totalNeedAnswer}`}</span>{isLast ? <Button className="um-practice-primary" onClick={handleSubmit} disabled={isSubmitting}>{isSubmitting ? '提交中…' : '提交评分'}</Button> : <Button className="um-practice-primary" disabled={isSubmitting} onClick={() => setCurrentIdx(prev => prev + 1)}>下一题<CaretRight size={16} /></Button>}</footer>
      </DialogContent>
    </Dialog>
  );
};
