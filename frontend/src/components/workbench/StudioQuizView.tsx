import { useId, useState } from 'react';
import { ArrowClockwise } from '@phosphor-icons/react';
import { t } from '@/i18n';
import type { SourceAnchor, StudioQuizAnswer, StudioQuizAttempt, StudioQuizQuestion, StudioQuizResult } from '@/types/workbench';
import { CitationPill } from './CitationPill';
import { studioQuizAnswers, type StudioQuizDrafts } from './studioPractice';

function answerLabel(question: StudioQuizQuestion, value: StudioQuizResult['answer']) {
  if (value === null) return t('未作答');
  return question.type === 'single_choice' && typeof value === 'number' ? question.options[value] : value;
}

export function StudioQuizView({ questions, attempt, submitting, generating, generateHint, conversationId, onSelect, onSubmit, onGenerate }: {
  questions: StudioQuizQuestion[];
  attempt?: StudioQuizAttempt;
  submitting: boolean;
  generating: boolean;
  generateHint?: string;
  conversationId: string;
  onSelect: (anchor: SourceAnchor) => void;
  onSubmit: (answers: StudioQuizAnswer[]) => Promise<boolean>;
  onGenerate: () => void;
}) {
  const formId = useId();
  const [drafts, setDrafts] = useState<StudioQuizDrafts>({});
  const [retaking, setRetaking] = useState(false);
  const results = retaking ? undefined : attempt;
  const answers = studioQuizAnswers(questions, drafts);

  return <form className="um-wb-quiz" onSubmit={async event => {
    event.preventDefault();
    if (submitting || !answers.length || results) return;
    if (await onSubmit(answers)) setRetaking(false);
  }}>
    {results && <div className="um-wb-quiz-score" role="status">
      <span>{t('本次得分')}</span>
      <strong>{results.score} / {results.max_score}</strong>
    </div>}
    {questions.map((question, index) => {
      const result = results?.results.find(row => row.question_id === question.id);
      return <fieldset className="um-wb-quiz-question" key={question.id} disabled={submitting}>
        <legend>{index + 1}. {question.prompt}</legend>
        {result ? <div className="um-wb-quiz-feedback">
          <strong className="um-wb-quiz-points" data-full={result.score === result.max_score}>{t('得分 {0} / {1}', { 0: result.score, 1: result.max_score })}</strong>
          <p><b>{t('你的答案')}</b> {answerLabel(question, result.answer)}</p>
          <p><b>{t('参考答案')}</b> {answerLabel(question, result.correct_answer)}</p>
          {result.explanation && <p><b>{t('解析')}</b> {result.explanation}</p>}
          {result.feedback && <p>{result.feedback}</p>}
          <CitationPill citation={result.citation} conversationId={conversationId} onSelect={onSelect} />
        </div> : question.type === 'single_choice' ? <div className="um-wb-quiz-options">
          {question.options.map((option, optionIndex) => <label key={option}>
            <input type="radio" name={`${formId}-${question.id}`} checked={drafts[question.id] === optionIndex}
              onChange={() => setDrafts(previous => ({ ...previous, [question.id]: optionIndex }))} />
            {option}
          </label>)}
        </div> : <textarea className="um-wb-studio-input" rows={4} maxLength={4000}
          aria-label={t('第 {0} 题作答', { 0: index + 1 })} placeholder={t('写下你的推理过程')}
          value={drafts[question.id] ?? ''} onChange={event => setDrafts(previous => ({ ...previous, [question.id]: event.target.value }))} />}
      </fieldset>;
    })}
    <div className="um-wb-studio-tools">
      {results ? <>
        <button type="button" className="um-agent-button" onClick={() => { setDrafts({}); setRetaking(true); }}>
          <ArrowClockwise size={15} />{t('重新作答')}
        </button>
        <span title={generateHint}><button type="button" className="um-agent-button" disabled={generating || !!generateHint}
          onClick={onGenerate}>{generating ? t('正在生成…') : t('生成新自测')}</button></span>
      </> : <>
        <button type="submit" className="um-agent-button um-agent-button-primary" disabled={submitting || !answers.length}>
          {submitting ? t('正在批改…') : t('提交批改')}
        </button>
        <span className="um-wb-muted">{t('已作答 {0} / {1}', { 0: answers.length, 1: questions.length })}</span>
      </>}
    </div>
  </form>;
}
