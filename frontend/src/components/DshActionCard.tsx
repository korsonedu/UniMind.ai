import { useEffect, useRef, useState } from 'react';
import { isAxiosError } from 'axios';
import { Link } from 'react-router-dom';
import api from '@/lib/api';
import { formatApiErrorToast } from '@/lib/apiError';
import { useAuthStore } from '@/store/useAuthStore';

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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [content, setContent] = useState(payload.content || '');
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [now, setNow] = useState(Date.now());
  const inFlight = useRef(false);
  const seconds = Math.max(0, Math.ceil((payload.expires_at * 1000 - now) / 1000));
  const expired = seconds === 0;
  const diagnostic = payload.kind === 'diagnostic';

  useEffect(() => {
    let active = true;
    api.get<Result>(`/ai/dsh/actions/${payload.request_id}/`)
      .then(({ data }) => { if (active) setResult(data); })
      .catch(err => { if (active && (!isAxiosError(err) || err.response?.status !== 404)) setError(formatApiErrorToast(err, '暂时无法读取提交结果')); })
      .finally(() => { if (active) setChecking(false); });
    return () => { active = false; };
  }, [payload.request_id]);

  useEffect(() => {
    if (result) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [result]);

  const recover = async () => {
    setChecking(true); setError('');
    try { setResult((await api.get<Result>(`/ai/dsh/actions/${payload.request_id}/`)).data); }
    catch (err) { setError(formatApiErrorToast(err, '尚未找到已提交结果，可核对后重试。')); }
    finally { setChecking(false); }
  };
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (inFlight.current || checking || result || expired) return;
    inFlight.current = true; setBusy(true); setError('');
    try {
      const body = { token: payload.token, confirmed: true, ...(diagnostic
        ? { answers: (payload.questions || []).map(question => ({ question: { id: question.id }, answer: answers[question.id] || '' })) }
        : { content }) };
      const saved = (await api.post<Result>('/ai/dsh/actions/confirm/', body)).data;
      setResult(saved);
      if (saved.kind === 'diagnostic' && useAuthStore.getState().user?.id === userId) {
        useAuthStore.getState().updateUser({ has_completed_initial_assessment: true });
      }
    } catch (err) { setError(formatApiErrorToast(err, '提交未确认，请查询原结果或重试。')); }
    finally { inFlight.current = false; setBusy(false); }
  };

  return <section className="space-y-4 rounded-xl border border-border/50 bg-card p-4" aria-label={diagnostic ? '诊断作答' : '人工答疑草稿'}>
    <h3 className="text-sm font-semibold">{diagnostic ? '首次学习诊断' : '人工答疑草稿'}</h3>
    {checking && <p className="text-xs text-muted-foreground" role="status">正在读取提交状态…</p>}
    {error && <div className="space-y-2"><p className="text-sm text-destructive" role="alert">{error}</p>
      <button type="button" disabled={checking || busy} onClick={() => void recover()} className="text-xs underline">查询已提交结果</button></div>}
    {result ? diagnostic ? <div className="space-y-3">
      <p className="text-sm">诊断完成，答对 {result.total_score}/{result.total_questions} 题。</p>
      {result.results?.map((row, index) => <div key={index} className="border-t border-border/50 pt-3 text-sm">
        <p>{row.question_text}</p><p className="mt-1 text-muted-foreground">{row.is_correct ? '回答正确' : '回答未命中参考答案'} · 参考答案：{row.correct_answer}</p>
      </div>)}
      <Link to="/report-card" className="text-xs underline">查看学习报告 →</Link>
    </div> : <p className="text-sm">答疑问题 #{result.ticket_id} 已发布。<Link to="/qa" className="ml-2 underline">查看课程答疑 →</Link></p>
      : checking ? null : <form onSubmit={event => void submit(event)} className="space-y-4">
        {diagnostic ? <>
          <p className="text-xs text-muted-foreground">剩余 {Math.floor(seconds / 60)} 分 {seconds % 60} 秒。请自行作答，未作答题按错误计分；超时不会自动提交。</p>
          {payload.questions?.map((question, index) => <fieldset key={question.id} disabled={busy || checking || expired} className="space-y-2 border-t border-border/50 pt-3">
            <legend className="text-sm">{index + 1}．{question.question_text}</legend>
            {Object.entries(question.options).map(([key, value]) => {
              const option = Array.isArray(question.options) ? String.fromCharCode(65 + Number(key)) : key;
              return <label key={key} className="flex items-start gap-2 text-sm"><input type="radio" name={`${payload.request_id}-${question.id}`} value={option}
                checked={answers[question.id] === option} onChange={() => setAnswers(previous => ({ ...previous, [question.id]: option }))} />
                <span>{option}．{String(value).replace(/^[A-Z][.．、:：)）]\s*/i, '')}</span></label>;
            })}
          </fieldset>)}
        </> : <>
          <p className="text-xs leading-5 text-muted-foreground">尚未发布。请核对正文；确认发布后，课程答疑中的同学和老师可见。</p>
          <label className="block space-y-2 text-sm"><span>答疑正文</span><textarea value={content} maxLength={7500} required disabled={busy || checking || expired}
            onChange={event => setContent(event.target.value)} rows={6} className="w-full rounded-lg border border-input bg-background p-3" /></label>
        </>}
        {expired && <p className="text-xs text-destructive">本次{diagnostic ? '诊断' : '草稿'}已过期，请让小宇重新准备。</p>}
        <button type="submit" disabled={busy || checking || expired || (!diagnostic && !content.trim())}
          className="rounded-full bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-40">
          {busy ? '提交中…' : diagnostic ? '确认提交诊断答案' : '确认发布到课程答疑'}
        </button>
      </form>}
  </section>;
}
