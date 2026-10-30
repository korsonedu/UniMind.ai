import { useEffect, useRef, useState } from 'react';
import { isAxiosError } from 'axios';
import { CheckCircle, ClipboardText, Clock, ArrowRight, ArrowClockwise, Spinner } from '@phosphor-icons/react';
import { Link } from 'react-router-dom';
import api from '@/lib/api';
import { formatApiErrorToast } from '@/lib/apiError';
import { useAuthStore } from '@/store/useAuthStore';
import '@/styles/dsh-actions.css';

type Question = { id: number; question_text: string; options: string[] | Record<string, string> };
export type ActionPayload = {
  kind: 'diagnostic' | 'faq'; request_id: string; token: string; expires_at: number;
  content?: string; questions?: Question[];
};
type Result = {
  kind: string; ticket_id?: number; total_score?: number; total_questions?: number;
  results?: { question_text: string; is_correct: boolean; correct_answer: string }[];
};

export function DshActionCard({ payload }: { payload: ActionPayload }) {
  const userId = useAuthStore(state => state.user?.id);
  return userId ? <ActionForm key={`${userId}:${payload.request_id}`} payload={payload} /> : null;
}

function ActionForm({ payload }: { payload: ActionPayload }) {
  const userId = useAuthStore(state => state.user?.id);
  const [result, setResult] = useState<Result | null>(null);
  const [checking, setChecking] = useState(true);
  const [statusKnown, setStatusKnown] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [content, setContent] = useState(payload.content || '');
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [now, setNow] = useState(Date.now);
  const inFlight = useRef(false);
  const seconds = Math.max(0, Math.ceil((payload.expires_at * 1000 - now) / 1000));
  const expired = seconds === 0;
  const diagnostic = payload.kind === 'diagnostic';
  const answeredCount = (payload.questions || []).filter(question => answers[question.id]).length;

  useEffect(() => {
    let active = true;
    api.get<Result>(`/ai/dsh/actions/${payload.request_id}/`)
      .then(({ data }) => { if (active) { setResult(data); setStatusKnown(true); } })
      .catch(err => {
        if (!active) return;
        if (isAxiosError(err) && err.response?.status === 404) setStatusKnown(true);
        else setError(formatApiErrorToast(err, '暂时无法读取提交状态，请刷新状态后继续。'));
      })
      .finally(() => { if (active) setChecking(false); });
    return () => { active = false; };
  }, [payload.request_id]);

  useEffect(() => {
    if (result?.kind === 'diagnostic' && useAuthStore.getState().user?.id === userId) {
      useAuthStore.getState().updateUser({ has_completed_initial_assessment: true });
    }
  }, [result, userId]);

  useEffect(() => {
    if (result || expired) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [result, expired]);

  const recover = async () => {
    if (checking || inFlight.current) return;
    setChecking(true); setStatusKnown(false); setError('');
    try { setResult((await api.get<Result>(`/ai/dsh/actions/${payload.request_id}/`)).data); setStatusKnown(true); }
    catch (err) {
      if (isAxiosError(err) && err.response?.status === 404) { setResult(null); setStatusKnown(true); }
      else setError(formatApiErrorToast(err, '暂时无法读取提交状态，请稍后重试。'));
    }
    finally { setChecking(false); }
  };
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (inFlight.current || checking || !statusKnown || result || Date.now() >= payload.expires_at * 1000) return;
    inFlight.current = true; setBusy(true); setError('');
    try {
      const body = { token: payload.token, confirmed: true, ...(diagnostic
        ? { answers: (payload.questions || []).map(question => ({ question: { id: question.id }, answer: answers[question.id] || '' })) }
        : { content }) };
      setResult((await api.post<Result>('/ai/dsh/actions/confirm/', body)).data);
    } catch (err) { setStatusKnown(false); setError(formatApiErrorToast(err, '提交未确认，请刷新状态查看原结果。')); }
    finally { inFlight.current = false; setBusy(false); }
  };

  return <section className="um-dsh-action" aria-label={diagnostic ? '诊断作答' : '人工答疑草稿'} aria-busy={checking || busy}>
    <header className="um-dsh-action-header">
      {result ? <CheckCircle size={20} className="um-dsh-action-success" /> : <ClipboardText size={20} />}
      <div><h3>{diagnostic ? '首次学习诊断' : '人工答疑草稿'}</h3>
        <p>{result ? diagnostic ? '已完成诊断' : '已发布到课程答疑' : checking ? '正在核对提交状态…' : !statusKnown ? '提交状态待确认' : expired ? '已过期' : diagnostic ? '自行作答，确认后提交' : '核对内容后发布'}</p></div>
      {diagnostic && !result && !checking && <span className="um-dsh-action-time"><Clock size={14} />{Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')}</span>}
    </header>
    {checking && <p className="um-dsh-action-status" role="status"><Spinner size={16} className="animate-spin" />正在读取提交状态…</p>}
    {error && <div className="um-dsh-action-error"><p role="alert">{error}</p>
      <button type="button" disabled={checking || busy} onClick={() => void recover()} className="um-dsh-action-retry"><ArrowClockwise size={14} />刷新提交状态</button></div>}
    {result ? diagnostic ? <div className="um-dsh-action-result">
      <p className="um-dsh-action-score"><strong>{result.total_score}<span> / {result.total_questions}</span></strong>题答对</p>
      {result.results?.map((row, index) => <div key={index} className="um-dsh-action-result-row">
        <p>{index + 1}．{row.question_text}</p><p className={row.is_correct ? 'um-dsh-action-success' : 'um-dsh-action-muted'}>{row.is_correct ? '回答正确' : '回答未命中参考答案'} · 参考答案：{row.correct_answer}</p>
      </div>)}
      <Link to="/report-card" className="um-dsh-action-link">查看学习报告<ArrowRight size={14} /></Link>
    </div> : <div className="um-dsh-action-result"><p>答疑问题 #{result.ticket_id} 已发布。</p><Link to="/qa" className="um-dsh-action-link">查看课程答疑<ArrowRight size={14} /></Link></div>
      : checking ? null : <form onSubmit={event => void submit(event)}>
        {diagnostic ? <>
          <div className="um-dsh-action-meta"><span>已作答 {answeredCount} / {payload.questions?.length || 0} 题</span><span>未作答题按错误计分</span></div>
          {payload.questions?.map((question, index) => <fieldset key={question.id} disabled={busy || checking || expired} className="um-dsh-action-question">
            <legend>{index + 1}．{question.question_text}</legend>
            {Object.entries(question.options).map(([key, value]) => {
              const option = Array.isArray(question.options) ? String.fromCharCode(65 + Number(key)) : key;
              return <label key={key} className="um-dsh-action-option" data-selected={answers[question.id] === option || undefined}><input type="radio" name={`${payload.request_id}-${question.id}`} value={option}
                checked={answers[question.id] === option} onChange={() => setAnswers(previous => ({ ...previous, [question.id]: option }))} />
                <span className="um-dsh-action-letter">{option}</span><span>{String(value).replace(/^[A-Z][.．、:：)）]\s*/i, '')}</span></label>;
            })}
          </fieldset>)}
        </> : <div className="um-dsh-action-editor">
          <p className="um-dsh-action-muted">确认发布后，课程答疑中的同学和老师可见。</p>
          <label><span>答疑正文</span><textarea value={content} maxLength={7500} required disabled={busy || checking || expired}
            onChange={event => setContent(event.target.value)} rows={6} /></label>
          <p className="um-dsh-action-count">{content.length.toLocaleString()} / 7,500</p>
        </div>}
        <footer className="um-dsh-action-footer">
          <p>{expired ? `本次${diagnostic ? '诊断' : '草稿'}已过期，请让小宇重新准备。` : !statusKnown ? '请先刷新状态，确认是否已提交。' : diagnostic ? '超时不会自动提交' : '发布前仍可编辑正文'}</p>
          <button type="submit" disabled={busy || checking || !statusKnown || expired || (!diagnostic && !content.trim())} className="um-dsh-action-submit">
            {busy && <Spinner size={16} className="animate-spin" />}{busy ? '提交中…' : diagnostic ? '确认提交诊断答案' : '确认发布到课程答疑'}
          </button>
        </footer>
      </form>}
  </section>;
}
