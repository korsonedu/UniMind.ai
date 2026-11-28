import { t, useLocale } from '@/i18n';
import { useEffect, useRef, useState } from 'react';
import { isAxiosError } from 'axios';
import { CheckCircle, ClipboardText, Clock, ArrowClockwise, Spinner } from '@phosphor-icons/react';
import api from '@/lib/api';
import { formatApiErrorToast } from '@/lib/apiError';
import { useAuthStore } from '@/store/useAuthStore';
import '@/styles/dsh-actions.css';

type Question = { id: number; question_text: string; options: string[] | Record<string, string> };
export type ActionPayload = {
  kind: 'diagnostic'; request_id: string; token: string; expires_at: number;
  questions?: Question[];
};
type Result = {
  kind: string; total_score?: number; total_questions?: number;
  results?: { question_text: string; is_correct: boolean; correct_answer: string }[];
};

const LEARNING_ACTIONS = '/ai/learning-actions';

export function DshActionCard({ payload }: { payload: ActionPayload }) {
  const userId = useAuthStore(state => state.user?.id);
  return userId ? <ActionForm key={`${userId}:${payload.request_id}`} payload={payload} /> : null;
}

function ActionForm({ payload }: { payload: ActionPayload }) {
  useLocale();
  const userId = useAuthStore(state => state.user?.id);
  const [result, setResult] = useState<Result | null>(null);
  const [checking, setChecking] = useState(true);
  const [statusKnown, setStatusKnown] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [now, setNow] = useState(Date.now);
  const inFlight = useRef(false);
  const seconds = Math.max(0, Math.ceil((payload.expires_at * 1000 - now) / 1000));
  const expired = seconds === 0;
  const answeredCount = (payload.questions || []).filter(question => answers[question.id]).length;

  useEffect(() => {
    let active = true;
    api.get<Result>(`${LEARNING_ACTIONS}/${payload.request_id}/`)
      .then(({ data }) => { if (active) { setResult(data); setStatusKnown(true); } })
      .catch(err => {
        if (!active) return;
        if (isAxiosError(err) && err.response?.status === 404) setStatusKnown(true);
        else setError(formatApiErrorToast(err, t('暂时无法读取提交状态，请刷新状态后继续。')));
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
    try { setResult((await api.get<Result>(`${LEARNING_ACTIONS}/${payload.request_id}/`)).data); setStatusKnown(true); }
    catch (err) {
      if (isAxiosError(err) && err.response?.status === 404) { setResult(null); setStatusKnown(true); }
      else setError(formatApiErrorToast(err, t('暂时无法读取提交状态，请稍后重试。')));
    }
    finally { setChecking(false); }
  };
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (inFlight.current || checking || !statusKnown || result || Date.now() >= payload.expires_at * 1000) return;
    inFlight.current = true; setBusy(true); setError('');
    try {
      const body = { token: payload.token, confirmed: true,
        answers: (payload.questions || []).map(question => ({ question: { id: question.id }, answer: answers[question.id] || '' })) };
      setResult((await api.post<Result>(`${LEARNING_ACTIONS}/confirm/`, body)).data);
    } catch (err) { setStatusKnown(false); setError(formatApiErrorToast(err, t('提交未确认，请刷新状态查看原结果。'))); }
    finally { inFlight.current = false; setBusy(false); }
  };

  return <section className="um-dsh-action" aria-label={t('诊断作答')} aria-busy={checking || busy}>
    <header className="um-dsh-action-header">
      {result ? <CheckCircle size={20} className="um-dsh-action-success" /> : <ClipboardText size={20} />}
      <div><h3>{t('首次学习诊断')}</h3>
        <p>{result ? t('已完成诊断') : checking ? t('正在核对提交状态…') : !statusKnown ? t('提交状态待确认') : expired ? t('已过期') : t('自行作答，确认后提交')}</p></div>
      {!result && !checking && <span className="um-dsh-action-time"><Clock size={14} />{Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')}</span>}
    </header>
    {checking && <p className="um-dsh-action-status" role="status"><Spinner size={16} className="animate-spin" />{t('正在读取提交状态…')}</p>}
    {error && <div className="um-dsh-action-error"><p role="alert">{t(error)}</p>
      <button type="button" disabled={checking || busy} onClick={() => void recover()} className="um-dsh-action-retry"><ArrowClockwise size={14} />{t('刷新提交状态')}</button></div>}
    {result ? <div className="um-dsh-action-result">
      <p className="um-dsh-action-score"><strong>{result.total_score}<span> / {result.total_questions}</span></strong>{t('题答对')}</p>
      {result.results?.map((row, index) => <div key={index} className="um-dsh-action-result-row">
        <p>{index + 1}．{row.question_text}</p><p className={row.is_correct ? 'um-dsh-action-success' : 'um-dsh-action-muted'}>{row.is_correct ? t('回答正确') : t('回答未命中参考答案')} {t('· 参考答案：')}{row.correct_answer}</p>
      </div>)}
    </div>
      : checking ? null : <form onSubmit={event => void submit(event)}>
          <div className="um-dsh-action-meta"><span>{t('已作答 {0} / {1} 题', { 0: answeredCount, 1: payload.questions?.length || 0 })}</span><span>{t('未作答题按错误计分')}</span></div>
          {payload.questions?.map((question, index) => <fieldset key={question.id} disabled={busy || checking || expired} className="um-dsh-action-question">
            <legend>{index + 1}．{question.question_text}</legend>
            {Object.entries(question.options).map(([key, value]) => {
              const option = Array.isArray(question.options) ? String.fromCharCode(65 + Number(key)) : key;
              return <label key={key} className="um-dsh-action-option" data-selected={answers[question.id] === option || undefined}><input type="radio" name={`${payload.request_id}-${question.id}`} value={option}
                checked={answers[question.id] === option} onChange={() => setAnswers(previous => ({ ...previous, [question.id]: option }))} />
                <span className="um-dsh-action-letter">{option}</span><span>{String(value).replace(/^[A-Z][.．、:：)）]\s*/i, '')}</span></label>;
            })}
          </fieldset>)}
        <footer className="um-dsh-action-footer">
          <p>{expired ? t('本次诊断已过期，请让小宇重新准备。') : !statusKnown ? t('请先刷新状态，确认是否已提交。') : t('超时不会自动提交')}</p>
          <button type="submit" disabled={busy || checking || !statusKnown || expired} className="um-dsh-action-submit">
            {busy && <Spinner size={16} className="animate-spin" />}{busy ? t('提交中…') : t('确认提交诊断答案')}
          </button>
        </footer>
      </form>}
  </section>;
}
