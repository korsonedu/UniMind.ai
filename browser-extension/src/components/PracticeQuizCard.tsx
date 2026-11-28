import { useEffect, useRef, useState } from 'react';
import { CaretLeft, CaretRight, CheckCircle, Spinner } from '@phosphor-icons/react';
import type { ApiClient } from '../lib/api';
import { MarkdownMessage } from './MarkdownMessage';

export interface PracticeQuestion {
  id: number;
  text: string;
  q_type: string;
  options: string[] | Record<string, string> | null;
  kp_name?: string;
}

export interface PracticePayload {
  practice_id: string;
  title: string;
  questions: PracticeQuestion[];
  learning_task_id?: string;
  assistance?: string;
  project_id?: number;
  conversation_id?: string;
  response_type?: 'objective' | 'explanation' | 'calculation' | 'reasoning' | 'case' | 'code';
  label_source?: string;
}

export interface PracticeResult {
  status: 'pending' | 'grading' | 'completed' | 'partial' | 'failed';
  total_score: number;
  max_score: number;
  graded_count: number;
  total_questions: number;
  correct_count?: number;
  label_source?: string;
  results: {
    position: number;
    status: string;
    score: number;
    max_score: number;
    is_correct: boolean;
    label_source?: string;
    correct_answer: string;
    feedback: string;
    analysis: string;
  }[];
}

interface SubmittedPractice {
  exam_id: number;
  assistance?: string | null;
  answers: { position: number; answer: string }[];
}

interface PracticeDraft {
  answers: Record<number, string>;
  notes: Record<number, string>;
  index: number;
  examId: number | null;
  submitted: boolean;
  assistance: string;
}

export interface PracticeQuizCardProps {
  payload: PracticePayload;
  api: ApiClient;
  storageScope?: string;
  onResult?: () => void;
}

function readDraft(key: string, payload: PracticePayload): PracticeDraft {
  const empty: PracticeDraft = {
    answers: {}, notes: {}, index: 0, examId: null, submitted: false,
    assistance: payload.learning_task_id && (!payload.assistance || payload.assistance === 'unknown')
      ? 'independent' : payload.assistance || 'unknown',
  };
  try {
    const saved = JSON.parse(localStorage.getItem(key) || 'null') as Partial<PracticeDraft> | null;
    if (!saved || typeof saved !== 'object') return empty;
    return {
      ...empty, ...saved,
      answers: saved.answers && typeof saved.answers === 'object' ? saved.answers : {},
      notes: saved.notes && typeof saved.notes === 'object' ? saved.notes : {},
      examId: Number.isInteger(saved.examId) && Number(saved.examId) > 0 ? Number(saved.examId) : null,
      index: Number.isInteger(saved.index) ? Number(saved.index) : 0,
    };
  } catch {
    return empty;
  }
}

function persistDraft(key: string, draft: PracticeDraft) {
  try { localStorage.setItem(key, JSON.stringify(draft)); } catch { /* 作答继续使用内存草稿。 */ }
}

function failureText(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

function responseStatus(error: unknown): number | undefined {
  return error && typeof error === 'object' && 'status' in error ? Number(error.status) : undefined;
}

export function PracticeQuizCard(props: PracticeQuizCardProps) {
  const storageKey = `unimind:extension:practice:${props.storageScope || 'default'}:${props.payload.practice_id}`;
  return <PracticeQuiz key={storageKey} {...props} storageKey={storageKey} />;
}

function PracticeQuiz({ payload, api, storageKey, onResult }: PracticeQuizCardProps & { storageKey: string }) {
  const [draft, setDraft] = useState(() => readDraft(storageKey, payload));
  const [recovering, setRecovering] = useState(!draft.examId);
  const [recoveryError, setRecoveryError] = useState('');
  const [recoveryAttempt, setRecoveryAttempt] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [result, setResult] = useState<PracticeResult | null>(null);
  const [resultError, setResultError] = useState('');
  const [pollAttempt, setPollAttempt] = useState(0);
  const inFlight = useRef(false);
  const mounted = useRef(true);
  const submitController = useRef<AbortController | null>(null);
  const resultCallback = useRef(onResult);
  resultCallback.current = onResult;
  const questions = payload.questions || [];
  const index = Math.max(0, Math.min(draft.index, questions.length - 1));
  const question = questions[index];
  const answeredCount = questions.filter(item => draft.answers[item.id]?.trim()).length;
  const locked = submitting || recovering || !!recoveryError || !!draft.examId || draft.submitted;

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; submitController.current?.abort(); };
  }, []);

  useEffect(() => { persistDraft(storageKey, draft); }, [storageKey, draft]);

  const recoverSubmission = async (signal: AbortSignal): Promise<boolean> => {
    try {
      const saved = await api.request<SubmittedPractice>(`/api/quizzes/submissions/${encodeURIComponent(payload.practice_id)}/`, { signal });
      if (!Number.isInteger(saved.exam_id) || saved.exam_id <= 0) throw new Error('未收到有效的练习结果编号，请重试读取。');
      if (signal.aborted) return false;
      setDraft(previous => ({
        ...previous, submitted: true, examId: saved.exam_id,
        assistance: saved.assistance || previous.assistance,
        answers: Object.fromEntries(questions.map((item, position) => [item.id,
          saved.answers.find(answer => answer.position === position + 1)?.answer || '',
        ])),
      }));
      return true;
    } catch (error) {
      if (signal.aborted) return false;
      if (responseStatus(error) === 404) return false;
      throw error;
    }
  };

  useEffect(() => {
    if (draft.examId) return;
    const controller = new AbortController();
    setRecovering(true);
    setRecoveryError('');
    void recoverSubmission(controller.signal).catch(error => {
      if (!controller.signal.aborted) setRecoveryError(failureText(error, '暂时无法读取提交状态。'));
    }).finally(() => { if (!controller.signal.aborted) setRecovering(false); });
    return () => controller.abort();
  }, [api, payload.practice_id, draft.examId, recoveryAttempt]);

  useEffect(() => {
    if (!draft.examId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let lastVersion = '';
    const poll = async () => {
      try {
        const next = await api.request<PracticeResult>(`/api/quizzes/exams/${draft.examId}/`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setResult(next);
        setResultError('');
        const version = `${next.status}:${next.graded_count}:${next.total_score}`;
        if (lastVersion !== version) resultCallback.current?.();
        lastVersion = version;
        if (next.status === 'pending' || next.status === 'grading') timer = setTimeout(() => void poll(), 2500);
      } catch (error) {
        if (controller.signal.aborted) return;
        setResultError(failureText(error, '暂时无法读取批改结果。'));
        timer = setTimeout(() => void poll(), 5000);
      }
    };
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [api, draft.examId, pollAttempt]);

  const submit = async () => {
    if (inFlight.current || recovering || recoveryError || draft.examId || answeredCount !== questions.length) return;
    inFlight.current = true;
    setSubmitting(true);
    setSubmitError('');
    const controller = new AbortController();
    submitController.current = controller;
    const submitted = { ...draft, submitted: true };
    persistDraft(storageKey, submitted);
    setDraft(submitted);
    try {
      // Reuse the original practice ID and frozen answers if a response was lost.
      const saved = await api.request<{ exam_id: number }>('/api/quizzes/submit-exam/', {
        method: 'POST', signal: controller.signal,
        body: {
          submission_id: payload.practice_id,
          ...(payload.learning_task_id ? { learning_task_id: payload.learning_task_id, assistance: draft.assistance } : {}),
          answers: questions.map(item => ({ question_id: item.id, answer: draft.answers[item.id] })),
        },
      });
      if (!Number.isInteger(saved.exam_id) || saved.exam_id <= 0) throw new Error('未收到练习结果编号，请重试提交。');
      if (!controller.signal.aborted) setDraft(previous => ({ ...previous, examId: saved.exam_id }));
    } catch (error) {
      if (controller.signal.aborted) return;
      setSubmitError(failureText(error, '提交失败，请重试。'));
      try {
        const found = await recoverSubmission(controller.signal);
        const status = responseStatus(error);
        if (!found && status && status >= 400 && status < 500 && status !== 409 && status !== 408 && status !== 429) {
          setDraft(previous => ({ ...previous, submitted: false }));
        }
      } catch (recoveryFailure) {
        if (!controller.signal.aborted) setRecoveryError(failureText(recoveryFailure, '暂时无法查回提交状态。'));
      }
    } finally {
      inFlight.current = false;
      if (mounted.current) setSubmitting(false);
    }
  };

  if (!question) return null;
  const options = Array.isArray(question.options) ? question.options
    : Object.keys(question.options || {}).sort().map(key => (question.options as Record<string, string>)[key] || '');
  const itemResult = result?.results.find(item => item.position === index + 1);
  const grading = result?.status === 'pending' || result?.status === 'grading';
  const modelEvaluation = (itemResult?.label_source || result?.label_source || payload.label_source) === 'model_rubric_grade';

  return <section className="um-inline-practice" aria-label={payload.title || '随堂练习'}>
    <header className="um-inline-practice-header">
      <div><span className="um-inline-practice-caption">{payload.response_type && payload.response_type !== 'objective' ? '开放成果' : '随堂练习'} · {questions.length} 题</span>
      <h3>{payload.title || '随堂练习'}</h3></div>
    </header>
    <div>
      <div className="um-inline-practice-progress"><span>答题进度</span><span role="status">{answeredCount}/{questions.length}</span></div>
      <div className="um-inline-practice-segments" aria-hidden="true">{questions.map((item, position) => <span key={`${item.id}:${position}`} data-complete={!!draft.answers[item.id]?.trim()} />)}</div>
      <nav className="um-inline-practice-nav" aria-label="切换练习题目">{questions.map((item, position) =>
        <button type="button" key={`${item.id}:${position}`} aria-label={`第 ${position + 1} 题${draft.answers[item.id]?.trim() ? '，已答' : '，未答'}`}
          aria-current={position === index ? 'step' : undefined}
          data-answered={!!draft.answers[item.id]?.trim()}
          onClick={() => setDraft(previous => ({ ...previous, index: position }))}>{position + 1}</button>,
      )}</nav>
      <article className="um-inline-practice-question">
        <p className="um-inline-practice-caption">第 {index + 1} 题{question.kp_name && ` · ${question.kp_name}`}</p>
        <MarkdownMessage content={question.text} />
        {question.q_type === 'objective' ? <div className="um-inline-practice-options" role="group" aria-label="选择答案">
          {options.map((option, optionIndex) => <button type="button" key={optionIndex} disabled={locked}
            aria-pressed={draft.answers[question.id] === option}
            onClick={() => setDraft(previous => ({ ...previous, answers: { ...previous.answers, [question.id]: option } }))}>
            <span>{String.fromCharCode(65 + optionIndex)}</span>
            <div className="min-w-0"><MarkdownMessage content={option} /></div>
          </button>)}
        </div> : <textarea className="um-inline-practice-input"
          aria-label="本题答案" placeholder={payload.response_type === 'code' ? '粘贴代码，并说明思路、预期行为与已知结果…' : '写下你的解释、分析或计算过程…'}
          maxLength={payload.learning_task_id ? 20000 : undefined} spellCheck={payload.response_type !== 'code'} disabled={locked}
          value={draft.answers[question.id] || ''}
          onChange={event => setDraft(previous => ({ ...previous, answers: { ...previous.answers, [question.id]: event.target.value } }))} />}
      </article>
      <details key={question.id} className="um-inline-practice-notes">
        <summary>本题草稿{draft.notes[question.id] ? ' · 已记录' : ''}</summary>
        <textarea aria-label="本题草稿" placeholder="仅保存在此浏览器，不参与评分。" className="um-inline-practice-input"
          value={draft.notes[question.id] || ''} onChange={event => setDraft(previous => ({ ...previous, notes: { ...previous.notes, [question.id]: event.target.value } }))} />
      </details>
      {payload.learning_task_id && <label className="um-inline-practice-assistance">作答方式
        <select aria-label="本次作答帮助程度" disabled={locked} value={draft.assistance}
          onChange={event => setDraft(previous => ({ ...previous, assistance: event.target.value }))}>
          {draft.assistance === 'unknown' && <option value="unknown">尚未说明</option>}
          <option value="independent">独立作答</option><option value="hint">获得提示</option><option value="guided">逐步引导完成</option>
        </select>
      </label>}
      {recovering && <p className="um-inline-practice-caption">正在读取提交状态…</p>}
      {recoveryError && !draft.examId && <p className="um-inline-practice-error" role="alert">{recoveryError} <button type="button" className="um-inline-practice-text-button" onClick={() => setRecoveryAttempt(value => value + 1)}>重试读取</button></p>}
      {submitError && !draft.examId && <p className="um-inline-practice-error" role="alert">{submitError}</p>}
      {draft.submitted && !draft.examId && !submitting && !recovering && <p className="um-inline-practice-caption">答案已保留，可使用相同答案重试提交。</p>}
      {draft.examId && <section className="um-inline-practice-result" aria-label="练习批改结果" aria-live="polite">
        {resultError && <p className="um-inline-practice-error" role="alert">{resultError} <button type="button" className="um-inline-practice-text-button" onClick={() => setPollAttempt(value => value + 1)}>重试</button></p>}
        {!result ? <p className="result-status"><Spinner size={14} className="spin" />正在读取批改结果…</p> : <>
          <p className="um-inline-practice-score result-status">{grading ? <Spinner size={15} className="spin" /> : <CheckCircle size={15} />}
            {grading ? `批改中 · ${result.graded_count}/${result.total_questions} 题`
              : `${result.status === 'partial' || result.status === 'failed' ? '批改未全部完成 · ' : result.label_source === 'model_rubric_grade' || result.label_source === 'mixed' ? 'AI 评分参考 · ' : '本次得分 · '}${result.total_score}/${result.max_score}`}</p>
          {itemResult?.status === 'graded' ? <>
            <p className="text-xs">本题 {itemResult.score}/{itemResult.max_score} 分{itemResult.is_correct ? ' · 回答正确' : ''}</p>
            {payload.learning_task_id && <p className="um-inline-practice-caption">{modelEvaluation ? 'AI 评分参考' : '按标准答案评分'}{payload.response_type === 'code' && ' · 代码按文本评分'}</p>}
            {itemResult.correct_answer && <div><p className="um-inline-practice-caption">参考答案</p><MarkdownMessage content={itemResult.correct_answer} /></div>}
            {itemResult.feedback && <MarkdownMessage content={itemResult.feedback} />}
            {itemResult.analysis && <div><p className="um-inline-practice-caption">解析</p><MarkdownMessage content={itemResult.analysis} /></div>}
          </> : <p className="text-xs">{itemResult?.status === 'failed' ? '本题批改未完成。' : '本题正在批改，请稍候。'}</p>}
        </>}
      </section>}
      <footer className="um-inline-practice-footer">
        <div>
          <button type="button" disabled={index === 0} onClick={() => setDraft(previous => ({ ...previous, index: index - 1 }))}><CaretLeft size={13} />上一题</button>
          <button type="button" disabled={index === questions.length - 1} onClick={() => setDraft(previous => ({ ...previous, index: index + 1 }))}>下一题<CaretRight size={13} /></button>
        </div>
        {!draft.examId && <button type="button" className="um-inline-practice-submit"
          disabled={submitting || recovering || !!recoveryError || answeredCount !== questions.length} onClick={() => void submit()}>{submitting ? '提交中…' : draft.submitted ? '重试提交' : '提交批改'}</button>}
      </footer>
    </div>
  </section>;
}
