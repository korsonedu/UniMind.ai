import { useEffect, useRef, useState } from 'react';
import { useAuthStore } from '@/store/useAuthStore';
import { DshToolCard, type DshCard } from '@/components/DshToolCard';

type Health = { sdk?: string; backend_configured: boolean; model_configured: boolean; mode: string; student?: { id: number; name: string } };
type Pending = { message: string; session_id?: string; request_id: string };
const urlSite = new URLSearchParams(window.location.search).get('source') === 'site';
const site = urlSite;
const defaultMessage = '查询我的学习统计，并根据我的讲解偏好解释结果。';
class RequestError extends Error {
  status: number;
  constructor(message: string, status: number) { super(message); this.status = status; }
}
type LocalSession = { id: string; notice: string; updated_at: string; messages: { role: string; content: string; mode?: string; cards?: DshCard[] }[] };
type SavedSession = { id: string; title: string; updated_at: string; message_count: number };
type Turn = { content: string; session: LocalSession; routing: Context['routing']; gateway: { model: string; requests: { status: string; tool_count: number; tool_schema_bytes: number; tool_results: number; usage: { input_tokens?: number; output_tokens?: number; cache_read_input_tokens?: number; cache_creation_input_tokens?: number } }[] } };
type Context = {
  student: { id: number; name: string };
  memory: { version: string; items: { id: number; key: string; value: string }[] };
  tools: { function: { name: string; description: string } }[];
  permitted_tool_count: number;
  routing: { catalog_count: number; candidate_count: number; pending_names: string[]; candidate_schema_bytes: number; executable_schema_bytes: number; available_schema_bytes: number; initial_group: string; max_visible_tools: number; selected_calls?: string[] };
};

async function request<T>(path: string, data?: Record<string, unknown>, signal?: AbortSignal): Promise<T> {
  const base = site ? `${(import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '')}/ai/dsh` : '/dsh-m0';
  const response = await fetch(`${base}${path}${site ? '/' : ''}`, {
    credentials: 'include', signal,
    ...(data === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    const fallback = response.status === 401 ? '请先登录站点，当前页面的学生数据已清除。'
      : response.status === 403 ? '当前账号没有此项学习权益。'
      : response.status === 404 ? '入口尚未启用，或会话不存在。'
      : response.status === 409 ? '当前账号仍有任务处理中，请稍后重试。' : '服务暂不可用，请稍后重试。';
    throw new RequestError(response.status === 401 ? fallback : result.error || result.detail || fallback, response.status);
  }
  return result;
}

type StreamEvent = { type: string; text?: string; step?: number; name?: string; status?: string | number; error?: string; result?: Turn };
async function streamTurn(body: Pending, signal: AbortSignal, emit: (event: StreamEvent) => void): Promise<Turn> {
  const base = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '');
  const response = await fetch(`${base}/ai/dsh/chat/stream/`, {
    method: 'POST', credentials: 'include', signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (!response.ok) {
    const result = await response.json().catch(() => ({}));
    throw new RequestError(result.error || result.detail || '站点流式入口暂不可用。', response.status);
  }
  if (!response.body || !response.headers.get('Content-Type')?.includes('text/event-stream')) throw new Error('未收到有效的实时响应。');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) throw new Error('连接已结束，回答尚未确认完成；请恢复同一请求。');
      buffer += decoder.decode(value, { stream: true });
      if (buffer.length > 3 * 1024 * 1024) throw new Error('实时响应超出显示范围。');
      let end;
      while ((end = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, end); buffer = buffer.slice(end + 2);
        if (!frame.startsWith('data: ')) continue;
        const event = JSON.parse(frame.slice(6)) as StreamEvent;
        if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
        if (event.type === 'done' && event.result) return event.result;
        if (event.type === 'error') throw new RequestError(event.error || '本轮未完成。', Number(event.status) || 503);
        emit(event);
      }
    }
  } finally { await reader.cancel().catch(() => undefined); }
}

export default function DshM0({ production = false }: { production?: boolean }) {
  const [health, setHealth] = useState<Health | null>(null);
  const [context, setContext] = useState<Context | null>(null);
  const [message, setMessage] = useState(() => production ? '' : defaultMessage);
  const [session, setSession] = useState<LocalSession | null>(null);
  const [savedSessions, setSavedSessions] = useState<SavedSession[]>([]);
  const [turn, setTurn] = useState<Turn | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(true);
  const [retry, setRetry] = useState<Pending | null>(null);
  const [liveText, setLiveText] = useState('');
  const [liveStep, setLiveStep] = useState(0);
  const [liveTool, setLiveTool] = useState('');
  const operation = useRef<AbortController | null>(null);
  const storageKey = useRef<string | null>(site ? null : 'unimind-dsh-m0-session');
  const storage = site ? sessionStorage : localStorage;

  const selectSession = (value: LocalSession | null) => {
    setSession(value);
    if (site && value) setSavedSessions(rows => [{ id: value.id,
      title: value.messages.find(message => message.role === 'user')?.content.slice(0, 60).trim() || '新会话',
      updated_at: value.updated_at, message_count: value.messages.length }, ...rows.filter(row => row.id !== value.id)]
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, 50));
    if (!storageKey.current) return;
    if (value) storage.setItem(storageKey.current, value.id);
    else storage.removeItem(storageKey.current);
  };
  const begin = () => {
    operation.current?.abort();
    const controller = new AbortController();
    operation.current = controller;
    setBusy(true); setError(''); setLiveText(''); setLiveStep(0); setLiveTool('');
    return controller.signal;
  };
  const clearIdentity = () => {
    operation.current?.abort();
    selectSession(null); storageKey.current = site ? null : 'unimind-dsh-m0-session';
    setHealth(null); setContext(null); setTurn(null); setSavedSessions([]); setRetry(null); setMessage(production ? '' : defaultMessage); setBusy(false); setLiveText(''); setLiveStep(0); setLiveTool('');
  };
  const report = (err: unknown, signal: AbortSignal) => {
    if (signal.aborted) return;
    if (site && err instanceof RequestError && [401, 403].includes(err.status)) clearIdentity();
    setError(err instanceof Error ? err.message : '调用失败');
  };

  const loadConnection = (signal: AbortSignal) =>
    request<Health>(site ? '/status' : '/health', undefined, signal).then(async status => {
      if (signal.aborted) return;
      if (site) {
        const key = `unimind-dsh-site-session:${status.student!.id}`;
        if (storageKey.current !== key) {
          if (storageKey.current) storage.removeItem(storageKey.current);
          setRetry(null); setMessage(production ? '' : defaultMessage);
        }
        storageKey.current = key;
      }
      setHealth(site ? { ...status, backend_configured: true } : status);
      if (site) {
        const saved = await request<{ student_id: number; sessions: SavedSession[] }>('/sessions', undefined, signal);
        if (signal.aborted) return;
        if (saved.student_id !== status.student?.id) { clearIdentity(); setError('账号已变化，请刷新连接。'); return; }
        setSavedSessions(saved.sessions);
      }
      const id = storageKey.current && storage.getItem(storageKey.current);
      if (id) {
        try {
          const restored = await request<LocalSession>('/session/read', { session_id: id }, signal);
          if (!signal.aborted) selectSession(restored);
        } catch (err) {
          if (signal.aborted) return;
          if (err instanceof RequestError && [404, 410].includes(err.status)) selectSession(null);
          report(err, signal);
        }
      }
    }).catch(err => report(err, signal))
      .finally(() => { if (!signal.aborted) setBusy(false); });
  const refresh = () => {
    const signal = begin();
    setHealth(null); setSession(null); setContext(null); setTurn(null); setSavedSessions([]);
    return loadConnection(signal);
  };
  useEffect(() => {
    const controller = new AbortController();
    operation.current = controller;
    void loadConnection(controller.signal);
    if (!site) return () => operation.current?.abort();
    const logout = () => { clearIdentity(); setError('登录状态已变化，请刷新连接后继续。'); };
    const focus = () => { void refresh(); };
    const storageChange = (event: StorageEvent) => { if (event.key === 'auth-storage' || event.key === null) logout(); };
    const unsubscribe = useAuthStore.subscribe((state, previous) => {
      if (previous.user && previous.user.id !== state.user?.id) logout();
    });
    window.addEventListener('auth:logout', logout);
    window.addEventListener('focus', focus);
    window.addEventListener('storage', storageChange);
    return () => {
      operation.current?.abort(); unsubscribe();
      window.removeEventListener('auth:logout', logout); window.removeEventListener('focus', focus); window.removeEventListener('storage', storageChange);
    };
  }, []);

  const run = async (chat: boolean) => {
    const signal = begin();
    if (chat) setTurn(null);
    try {
      const body: Pending = site && retry ? retry : { message, session_id: session?.id, request_id: crypto.randomUUID() };
      const latest = await request<Context>('/context', { message: body.message }, signal);
      if (signal.aborted) return;
      if (site && latest.student.id !== health?.student?.id) { clearIdentity(); setError('账号已变化，请刷新连接。'); return; }
      setContext(latest);
      if (chat) {
        if (site) setRetry(body);
        const result = site ? await streamTurn(body, signal, event => {
          if (signal.aborted) return;
          if (event.type === 'step') { setLiveStep(event.step || 0); setLiveText(''); }
          if (event.type === 'text_delta') setLiveText(text => (text + (event.text || '')).slice(0, 65536));
          if (event.type === 'tool_status') setLiveTool(`${event.name} · ${event.status === 'running' ? '查询中' : '已返回'}`);
        }) : await request<Turn>('/chat', body, signal);
        if (site) {
          const current = await request<Health>('/status', undefined, signal);
          if (signal.aborted) return;
          if (current.student?.id !== latest.student.id) { clearIdentity(); setError('账号已变化，请刷新连接。'); return; }
        }
        if (signal.aborted) return;
        selectSession(result.session); setTurn(result); setContext({ ...latest, routing: result.routing }); setRetry(null);
      }
    } catch (err) {
      if (!signal.aborted && err instanceof RequestError && [400, 401, 403, 404, 410].includes(err.status)) setRetry(null);
      report(err, signal);
    } finally { if (!signal.aborted) { setBusy(false); setLiveText(''); setLiveStep(0); setLiveTool(''); } }
  };

  const loadSession = async (id: string) => {
    if (!id) return;
    const signal = begin();
    setSession(null); setContext(null); setTurn(null);
    try {
      const restored = await request<LocalSession>('/session/read', { session_id: id }, signal);
      const current = await request<Health>('/status', undefined, signal);
      if (signal.aborted) return;
      if (current.student?.id !== health?.student?.id) { clearIdentity(); setError('账号已变化，请刷新连接。'); return; }
      selectSession(restored);
    } catch (err) {
      if (!signal.aborted && err instanceof RequestError && [404, 410].includes(err.status)) {
        setSavedSessions(rows => rows.filter(row => row.id !== id));
      }
      report(err, signal);
    } finally { if (!signal.aborted) setBusy(false); }
  };

  const manageSession = async (action: 'new' | 'delete') => {
    if (action === 'delete' && !window.confirm('删除验证聊天及模型上下文？长期记忆和已发生的用量记录分别保留。')) return;
    const signal = begin();
    try {
      const result = await request<LocalSession>(`/session/${action}`, { session_id: session?.id }, signal);
      if (!signal.aborted) {
        if (action === 'delete') setSavedSessions(rows => rows.filter(row => row.id !== session?.id));
        selectSession(action === 'new' ? result : null); setTurn(null); setRetry(null);
      }
    } catch (err) { report(err, signal); }
    finally { if (!signal.aborted) setBusy(false); }
  };

  const exportSession = () => {
    if (!session) return;
    const messages = session.messages.map(({ role, content, mode }) => ({ role, content, mode }));
    const url = URL.createObjectURL(new Blob([JSON.stringify({ id: session.id, updated_at: session.updated_at, messages }, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = `unimind-m0-${session.id}.json`; link.click(); URL.revokeObjectURL(url);
  };

  return <main className="min-h-screen bg-background px-6 py-10 text-[#202020]">
    <div className="mx-auto max-w-5xl space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-border pb-6">
        <div><p className="mb-2 text-xs tracking-widest text-muted-foreground">{production ? 'UNIMIND' : 'UNIMIND / M0'}</p>
          <h1 className="text-3xl font-semibold">{production ? '小宇' : '学习界面与 AI 运行时分开验证'}</h1>
          {!production && <>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">{site ? '站点接入验证，使用当前登录身份；' : '本地开发入口。使用隔离的验证账号和合成数据；'}{health?.mode === 'deepseek-official' ? '模型使用 DeepSeek 官方 API，经本地任务网关限量调用。' : health?.mode === 'local-protocol-smoke' ? '模型端为本地协议模拟。' : health?.mode === 'unavailable' ? '模型尚未配置可用的授权来源。' : '模型来源尚未连接。'}当前验证不代表正式教学效果或生产发布。</p>
            <p className="mt-2 max-w-2xl text-xs leading-6 text-muted-foreground">产品基线：DSH 作为服务端 harness；网页和 UniMind 桌面客户端共用 AI 服务。{site ? '本页经站点身份进入隔离 DSH 进程。' : '本页连接本机开发服务。'}当前仅开放已验证的只读工具。</p>
          </>}
        </div>
        <a className="text-sm underline underline-offset-4" href="/courses">进入普通课程界面 →</a>
      </header>

      {!production && <section className="grid gap-4 sm:grid-cols-3" aria-label="连接状态">
        {[
          ['独立 React 界面', '已运行'],
          [site ? '站点入口' : '本地 Host', health ? (site ? '当前账号已连接' : `SDK ${health.sdk}`) : '未连接'],
          ['模型来源', health?.backend_configured && health.model_configured ? (health.mode === 'deepseek-official' ? 'DeepSeek 官方 · 任务网关' : '本地协议模拟 · 任务网关') : '尚未完整配置'],
        ].map(([label, value]) => <div key={label} className="border border-border bg-card p-5">
          <p className="text-xs text-muted-foreground">{label}</p><p className="mt-3 font-medium">{value}</p>
        </div>)}
      </section>}

      <div className={production ? 'grid gap-6' : 'grid gap-6 md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]'}>
        <section className="space-y-4 border border-border bg-card p-6">
          {!production && <h2 className="font-semibold">小宇只读链路</h2>}
          {production && <div className="flex flex-wrap items-center gap-3 text-sm">
            <select aria-label="历史会话" className="min-w-48 border border-border/70 bg-card p-2"
              value={session?.id || ''} disabled={busy || !!retry || !health?.backend_configured || !savedSessions.length}
              onChange={event => void loadSession(event.target.value)}>
              <option value="">{savedSessions.length ? '历史会话' : '暂无历史会话'}</option>
              {savedSessions.map(row => <option key={row.id} value={row.id}>{row.title} · {row.message_count} 条</option>)}
            </select>
            <button disabled={busy || !!retry || !health?.backend_configured} onClick={() => void manageSession('new')} className="border border-border px-3 py-2 disabled:opacity-40">新会话</button>
          </div>}
          <label className="block text-sm text-foreground/60" htmlFor="dsh-message">本轮问题</label>
          <textarea id="dsh-message" value={message} disabled={busy || !!retry} onChange={event => setMessage(event.target.value)} maxLength={4000}
            placeholder={production ? '问小宇任何备考问题…' : undefined}
            className="min-h-32 w-full resize-y border border-border/70 bg-muted/30 p-3 text-sm leading-6" />
          <div className="flex flex-wrap gap-3 text-sm">
            {!production && <button disabled={busy || !!retry || !health?.backend_configured} onClick={() => void run(false)} className="border border-border px-4 py-2 disabled:opacity-40">读取本人记忆与工具</button>}
            <button disabled={busy || !health?.backend_configured || !health?.model_configured} onClick={() => void run(true)} className="bg-foreground px-4 py-2 text-background disabled:opacity-40">{busy ? (production ? '正在回答…' : '正在验证…') : retry ? '恢复这次提问（同一请求）' : production ? '发送' : health?.mode === 'deepseek-official' ? '调用官方模型' : site ? '通过站点运行 DSH' : '运行 DSH 协议链路'}</button>
            {!production && <button disabled={busy} onClick={() => void refresh()} className="px-2 py-2 text-muted-foreground underline disabled:opacity-40">刷新连接与会话</button>}
          </div>
          {site && busy && <button className="text-xs underline text-muted-foreground" onClick={() => {
            operation.current?.abort(); setBusy(false); setLiveText(''); setLiveStep(0); setLiveTool('');
            setError('已停止接收。服务端任务可能仍在处理，恢复会使用同一请求。');
          }}>停止接收</button>}
          {site && busy && liveStep > 0 && <section aria-label="实时回答" aria-live="polite" className="border-l-2 border-border pl-4 text-sm leading-7">
            <p className="text-xs text-muted-foreground">小宇正在生成 · 第 {liveStep} 步{liveTool ? ` · ${liveTool}` : ''}</p>
            <p className="whitespace-pre-wrap">{liveText || '正在查询和组织回答…'}</p>
            <p className="text-xs text-muted-foreground/80">完成后保存完整回答；当前片段尚未确认。</p>
          </section>}
          {retry && !busy && <p className="text-xs leading-6 text-muted-foreground">这次提问尚未确认返回。恢复会使用相同请求 ID；页面取消或刷新不会撤销服务端任务。此页不会自动重试。</p>}
          {error && <p role="alert" className="border-l-2 border-amber-600 bg-amber-50 p-3 text-sm leading-6">{error}</p>}
          <div className="flex flex-wrap gap-4 border-t border-border pt-3 text-xs text-muted-foreground">
            <button disabled={busy || !!retry || !health?.backend_configured} onClick={() => void manageSession('new')}>新会话</button>
            <button disabled={busy || !session} onClick={exportSession}>导出对话文字</button>
            <button disabled={busy || !!retry || !session} onClick={() => void manageSession('delete')}>{site ? '删除站点会话' : '删除本地会话'}</button>
          </div>
          {!production && session && <p className="break-all font-mono text-[10px] text-muted-foreground/80">会话 {session.id} · {session.messages.length} 条消息</p>}
          {session?.notice && <p className="bg-amber-50 p-3 text-xs leading-6">{session.notice}</p>}
          <section aria-label="聊天记录" className="space-y-5">{session?.messages.map((item, index) => <div key={index} className="border-t border-border pt-4">
            <p className="mb-2 text-xs text-muted-foreground/80">{item.role === 'user' ? '我' : production ? '小宇' : `小宇 · ${item.mode === 'deepseek-official' ? '官方模型' : '本地协议模拟'}`}</p>
            <p className="whitespace-pre-wrap text-sm leading-7">{item.content}</p>
            {!!item.cards?.length && <div className="mt-4 space-y-4">
              <p className="text-xs text-muted-foreground/80">业务工具返回的结果快照；最新状态请打开详情。</p>
              {item.cards.map((card, cardIndex) => <DshToolCard key={`${card.tool}-${cardIndex}`} card={card} />)}
            </div>}
          </div>)}</section>
          {!production && turn && <p className="border-t border-border pt-3 text-xs leading-6 text-muted-foreground" aria-label="网关用量">
            {turn.gateway.model} · {turn.gateway.requests.length} 次请求 · {turn.gateway.requests.reduce((sum, r) => sum + r.tool_results, 0)} 个工具结果<br />
            各请求工具数 / Schema：{turn.gateway.requests.map((r, i) => `#${i + 1} ${r.tool_count} 项 / ${r.tool_schema_bytes} bytes`).join(' → ')}<br />
            工具调用轨迹：{turn.routing.selected_calls?.join(' → ') || '无工具调用'}<br />
            总输入 {turn.gateway.requests.reduce((sum, r) => sum + (r.usage.input_tokens || 0) + (r.usage.cache_read_input_tokens || 0) + (r.usage.cache_creation_input_tokens || 0), 0)} / 输出 {turn.gateway.requests.reduce((sum, r) => sum + (r.usage.output_tokens || 0), 0)} tokens。<br />
            输入明细：未缓存 {turn.gateway.requests.reduce((sum, r) => sum + (r.usage.input_tokens || 0), 0)} / 缓存读取 {turn.gateway.requests.reduce((sum, r) => sum + (r.usage.cache_read_input_tokens || 0), 0)} / 缓存创建 {turn.gateway.requests.reduce((sum, r) => sum + (r.usage.cache_creation_input_tokens || 0), 0)}。<br />最多 4 次请求，每次输出 1024 tokens。{site ? '完整成功的回答使用既有周问答额度。' : '未接正式扣费。'}
          </p>}
        </section>

        {!production && <aside className="space-y-6 border border-border bg-card p-6">
          <section><h2 className="font-semibold">当前验证身份</h2>
            <p className="mt-3 text-sm text-muted-foreground">{context ? `${context.student.name} · #${context.student.id}` : health?.student ? `${health.student.name} · #${health.student.id}` : site ? '请先登录站点' : '读取后显示；凭据由 Host 持有'}</p>
          </section>
          {site && <section>
            <label htmlFor="dsh-saved-session" className="font-semibold">服务端会话</label>
            <select id="dsh-saved-session" className="mt-3 w-full border border-border/70 bg-card p-2 text-sm"
              value={session?.id || ''} disabled={busy || !!retry || !health?.backend_configured || !savedSessions.length}
              onChange={event => void loadSession(event.target.value)}>
              <option value="">选择已有会话（最近 50 项）</option>
              {savedSessions.map(row => <option key={row.id} value={row.id}>{row.title} · {row.message_count} 条</option>)}
            </select>
            <p className="mt-2 text-xs leading-6 text-muted-foreground">{savedSessions.length ? '同一账号可从服务器恢复；读取不会调用模型或扣问答次数。' : '当前账号暂无可发现的服务端会话。'}</p>
          </section>}
          <section><h2 className="font-semibold">学生长期记忆</h2>
            {context?.memory.items.length ? context.memory.items.map(item => <p key={item.id} className="mt-3 text-sm leading-6"><span className="text-muted-foreground">{item.key}：</span>{item.value}</p>) : <p className="mt-3 text-sm text-muted-foreground">{context ? '当前没有有效的长期记忆' : '尚未读取记忆'}</p>}
            {context && <p className="mt-3 break-all font-mono text-[10px] text-foreground/35">版本 {context.memory.version}</p>}
          </section>
          <section><h2 className="font-semibold">本轮初始工具</h2>
            <p className="mt-2 text-xs leading-6 text-muted-foreground">{context?.routing ? `已鉴权目录 ${context.routing.catalog_count} 个，旧共享候选 ${context.routing.candidate_count} 个；初始提供 ${context.tools.length} 个工具（含发现），本人可用 ${context.permitted_tool_count} 个只读业务工具。` : '按权限与问题选择'}</p>
            <ul className="mt-3 space-y-2">{context?.tools.map(tool => <li key={tool.function.name} className="break-all border-t border-border/60 pt-2 font-mono text-xs">{tool.function.name}</li>)}</ul>
            {context?.routing && <p className="mt-3 text-xs leading-6 text-muted-foreground">初始组：{context.routing.initial_group || '按需发现'}。每次最多 {context.routing.max_visible_tools} 个工具，发现后切换分组。<br />初始 Schema {context.routing.executable_schema_bytes} bytes；完整业务许可 Schema {context.routing.available_schema_bytes} bytes。真实模型选择质量尚待验证。</p>}
            {!!context?.routing?.pending_names.length && <details className="mt-3 text-xs leading-6 text-muted-foreground"><summary>旧候选中 {context.routing.pending_names.length} 项尚未开放</summary><p className="mt-2 break-all font-mono">{context.routing.pending_names.join('、')}</p></details>}
          </section>
        </aside>}
      </div>
    </div>
  </main>;
}
