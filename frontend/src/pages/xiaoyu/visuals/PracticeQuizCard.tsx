import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import api from '@/lib/api';
import { formatApiErrorToast } from '@/lib/apiError';
import { normalizeOptions, processMathContent } from '@/lib/utils';
import { queryKeys } from '@/lib/queryKeys';
import { MarkdownContent } from '@/components/MarkdownContent';
import { useAuthStore } from '@/store/useAuthStore';
import { useExamActivityStore, isActiveExamStatus, type ExamActivityStatus } from '@/store/useExamActivityStore';
import { useLearningSession } from '@/hooks/useLearningSession';
import '@/styles/inline-practice.css';

interface PracticeQuestion {
  id: number;
  text: string;
  q_type: string;
  options: string[];
  kp_name?: string;
}

interface PracticePayload {
  practice_id: string;
  title: string;
  questions: PracticeQuestion[];
}

interface Draft {
  answers: Record<number, string>;
  notes: Record<number, string>;
  index: number;
  examId: number | null;
  submitted: boolean;
}

interface PracticeResult {
  status: ExamActivityStatus;
  total_score: number;
  max_score: number;
  graded_count: number;
  total_questions: number;
  results: { position: number; status: string; score: number; max_score: number;
    is_correct: boolean; correct_answer: string; feedback: string; analysis: string }[];
}

export function PracticeQuizCard({ payload }: { payload: PracticePayload }) {
  const userId = useAuthStore(state => state.user?.id);
  const storageKey = `unimind:inline-practice:${userId}:${payload.practice_id}`;
  const [draft, setDraft] = useState<Draft>(() => {
    const empty: Draft = { answers: {}, notes: {}, index: 0, examId: null, submitted: false };
    try { return { ...empty, ...JSON.parse(localStorage.getItem(storageKey) || 'null') }; }
    catch { return empty; }
  });
  const [active, setActive] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const inFlight = useRef(false);
  const questions = payload.questions;
  const index = Math.max(0, Math.min(draft.index, questions.length - 1));
  const question = questions[index];
  const answeredCount = questions.filter(item => draft.answers[item.id]?.trim()).length;
  const locked = draft.submitted || !!draft.examId;

  useLearningSession({ enabled: active && !locked && questions.length > 0,
    kind: 'practice', questionIds: questions.map(item => item.id) });

  useEffect(() => {
    try { localStorage.setItem(storageKey, JSON.stringify(draft)); }
    catch { /* 禁用本地存储不阻止作答。 */ }
  }, [storageKey, draft]);

  useEffect(() => {
    const onActive = (event: Event) => setActive((event as CustomEvent<string>).detail === storageKey);
    window.addEventListener('unimind:practice-active', onActive);
    return () => window.removeEventListener('unimind:practice-active', onActive);
  }, [storageKey]);

  const detail = useQuery<PracticeResult>({
    queryKey: queryKeys.exams.detail(draft.examId || 0),
    queryFn: async () => (await api.get(`/quizzes/exams/${draft.examId}/`)).data,
    enabled: !!draft.examId,
    staleTime: 0,
    retry: 1,
    refetchInterval: query => query.state.data && isActiveExamStatus(query.state.data.status) ? 2500 : false,
  });
  const result = detail.data;
  const itemResult = result?.results.find(item => item.position === index + 1);
  const graded = itemResult?.status === 'graded';

  const activate = () => {
    if (!locked) window.dispatchEvent(new CustomEvent('unimind:practice-active', { detail: storageKey }));
  };
  const submit = async () => {
    if (inFlight.current || draft.examId || answeredCount !== questions.length) return;
    inFlight.current = true;
    setSubmitting(true);
    setActive(false);
    setError('');
    const submitted = { ...draft, submitted: true };
    setDraft(submitted);
    try {
      // 在请求前保留提交状态，刷新或网络重试继续使用同一编号和答案。
      try { localStorage.setItem(storageKey, JSON.stringify(submitted)); } catch { /* 继续提交。 */ }
      const { data } = await api.post('/quizzes/submit-exam/', {
        submission_id: payload.practice_id,
        answers: questions.map(item => ({ question_id: item.id, answer: draft.answers[item.id] })),
      });
      const examId = Number(data.exam_id);
      if (!Number.isInteger(examId) || examId <= 0) throw new Error('未收到练习结果编号，请重试提交。');
      setDraft(previous => ({ ...previous, examId }));
      useExamActivityStore.getState().start({ examId, total: questions.length });
    } catch (failure) {
      setError(formatApiErrorToast(failure, '提交失败，请重试。'));
    } finally { inFlight.current = false; setSubmitting(false); }
  };

  if (!question) return null;

  return <section className="um-inline-practice" aria-label={payload.title || '随堂练习'}
    onFocusCapture={event => {
      if (!(event.target as HTMLElement).closest('[data-practice-toggle]')) activate();
    }} onBlurCapture={event => {
      if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setActive(false);
    }}>
    <header className="um-inline-practice-header">
      <div><span className="um-inline-practice-caption">随堂练习 · {questions.length} 题</span><h3>{payload.title || '随堂练习'}</h3></div>
      {!locked && <button type="button" data-practice-toggle className="um-inline-practice-text-button" onClick={() => {
        if (active) setActive(false); else activate();
      }}>{active ? '暂停练习' : '开始／继续'}</button>}
    </header>
    <div className="um-inline-practice-progress"><span>答题进度</span><span role="status">{answeredCount}/{questions.length}</span></div>
    <div className="um-inline-practice-segments" aria-hidden="true">{questions.map(item => <span key={item.id} data-complete={!!draft.answers[item.id]?.trim()} />)}</div>
    <nav className="um-inline-practice-nav" aria-label="切换练习题目">{questions.map((item, position) => <button type="button" key={item.id}
      aria-label={`第 ${position + 1} 题${draft.answers[item.id]?.trim() ? '，已答' : '，未答'}`}
      aria-current={position === index ? 'step' : undefined} data-answered={!!draft.answers[item.id]?.trim()}
      onClick={() => setDraft(previous => ({ ...previous, index: position }))}>{position + 1}</button>)}</nav>
    <article className="um-inline-practice-question">
      <p className="um-inline-practice-caption">第 {index + 1} 题{question.kp_name && ` · ${question.kp_name}`}</p>
      <MarkdownContent content={processMathContent(question.text)} />
      {question.q_type === 'objective' ? <div className="um-inline-practice-options" role="group" aria-label="选择答案">
        {normalizeOptions(question.options).map((option: string, optionIndex: number) => <button type="button" key={optionIndex}
          disabled={locked} aria-pressed={draft.answers[question.id] === option}
          onClick={() => setDraft(previous => ({ ...previous, answers: { ...previous.answers, [question.id]: option } }))}>
          <span>{String.fromCharCode(65 + optionIndex)}</span><MarkdownContent content={processMathContent(option)} />
        </button>)}
      </div> : <textarea className="um-inline-practice-input" aria-label="本题答案" placeholder="写下你的分析或计算过程…" disabled={locked}
        value={draft.answers[question.id] || ''} onChange={event => setDraft(previous => ({ ...previous,
          answers: { ...previous.answers, [question.id]: event.target.value } }))} />}
    </article>
    <details className="um-inline-practice-notes" key={question.id}>
      <summary>本题草稿{draft.notes[question.id] ? ' · 已记录' : ''}</summary>
      <textarea className="um-inline-practice-input" aria-label="本题草稿" placeholder="仅保存在此浏览器，不参与评分。"
        value={draft.notes[question.id] || ''} onChange={event => setDraft(previous => ({ ...previous,
          notes: { ...previous.notes, [question.id]: event.target.value } }))} />
    </details>
    {draft.examId && <section className="um-inline-practice-result" aria-label="练习批改结果" aria-live="polite">
      {!result ? <p>{detail.isError ? '暂时无法读取结果。' : '正在读取批改结果…'}{detail.isError && <button type="button" onClick={() => void detail.refetch()}>重试</button>}</p>
        : <>
          <p className="um-inline-practice-score">{isActiveExamStatus(result.status) ? `批改中 · ${result.graded_count}/${result.total_questions} 题`
            : `${result.status === 'partial' || result.status === 'failed' ? '批改未全部完成 · ' : '本次得分 · '}${result.total_score}/${result.max_score}`}</p>
          {graded ? <>
            <p>本题 {itemResult.score}/{itemResult.max_score} 分</p>
            {itemResult.correct_answer && <div><span className="um-inline-practice-caption">参考答案</span><MarkdownContent content={processMathContent(itemResult.correct_answer)} /></div>}
            {itemResult.feedback && <MarkdownContent content={processMathContent(itemResult.feedback)} />}
            {itemResult.analysis && <div><span className="um-inline-practice-caption">解析</span><MarkdownContent content={processMathContent(itemResult.analysis)} /></div>}
          </> : <p>{itemResult?.status === 'failed' ? '本题批改未完成，可在逐题复盘中重试。' : '本题正在批改，请稍候。'}</p>}
          <Link className="um-inline-practice-text-button" to={`/tests/results/${draft.examId}`}>打开逐题复盘</Link>
        </>}
    </section>}
    {error && <p className="um-inline-practice-error" role="alert">{error}</p>}
    <footer className="um-inline-practice-footer">
      <div><button type="button" disabled={index === 0} onClick={() => setDraft(previous => ({ ...previous, index: index - 1 }))}>上一题</button>
        <button type="button" disabled={index === questions.length - 1} onClick={() => setDraft(previous => ({ ...previous, index: index + 1 }))}>下一题</button></div>
      {!draft.examId && <button type="button" className="um-inline-practice-submit" disabled={submitting || answeredCount !== questions.length}
        onClick={() => void submit()}>{submitting ? '提交中…' : draft.submitted ? '重试提交' : '提交批改'}</button>}
    </footer>
  </section>;
}
