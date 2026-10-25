import { useEffect, useRef, useState } from 'react';
import { DshToolCard, type DshCard } from '@/components/DshToolCard';

type Health = { sdk: string; backend_configured: boolean; model_configured: boolean; mode: string };
type LocalSession = { id: string; notice: string; updated_at: string; messages: { role: string; content: string; mode?: string; cards?: DshCard[] }[] };
type Turn = { content: string; session: LocalSession; routing: Context['routing']; gateway: { model: string; requests: { status: string; tool_results: number; usage: { input_tokens?: number; output_tokens?: number; cache_read_input_tokens?: number; cache_creation_input_tokens?: number } }[] } };
type Context = {
  student: { id: number; name: string };
  memory: { version: string; items: { id: number; key: string; value: string }[] };
  tools: { function: { name: string; description: string } }[];
  permitted_tool_count: number;
  routing: { catalog_count: number; candidate_count: number; pending_names: string[]; candidate_schema_bytes: number; executable_schema_bytes: number };
};

async function request<T>(path: string, data?: Record<string, unknown>): Promise<T> {
  const response = await fetch(`/dsh-m0${path}`, data === undefined ? undefined : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || '本地服务暂不可用');
  return result;
}

export default function DshM0() {
  const [health, setHealth] = useState<Health | null>(null);
  const [context, setContext] = useState<Context | null>(null);
  const [message, setMessage] = useState('查询我的学习统计，并根据我的讲解偏好解释结果。');
  const [session, setSession] = useState<LocalSession | null>(null);
  const [turn, setTurn] = useState<Turn | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const refreshing = useRef(false);

  const selectSession = (value: LocalSession | null) => {
    setSession(value);
    if (value) localStorage.setItem('unimind-dsh-m0-session', value.id);
    else localStorage.removeItem('unimind-dsh-m0-session');
  };

  const refresh = async () => {
    if (refreshing.current) return;
    refreshing.current = true;
    setBusy(true); setError(''); setSession(null); setContext(null); setTurn(null);
    try {
      setHealth(await request<Health>('/health'));
      const id = localStorage.getItem('unimind-dsh-m0-session');
      if (id) {
        try { selectSession(await request<LocalSession>('/session/read', { session_id: id })); }
        catch (err) { selectSession(null); setError(err instanceof Error ? err.message : '本机会话不可用'); }
      }
    }
    catch { setHealth(null); setError('Host 尚未启动。课程和普通业务界面仍可独立使用。'); }
    finally { refreshing.current = false; setBusy(false); }
  };
  useEffect(() => { void refresh(); }, []);

  const run = async (chat: boolean) => {
    setBusy(true); setError('');
    if (chat) setTurn(null);
    try {
      const latest = await request<Context>('/context', { message });
      setContext(latest);
      if (chat) {
        const result = await request<Turn>('/chat', { message, session_id: session?.id });
        selectSession(result.session); setTurn(result); setContext({ ...latest, routing: result.routing });
      }
    } catch (err) { setError(err instanceof Error ? err.message : '调用失败'); }
    finally { setBusy(false); }
  };

  const manageSession = async (action: 'new' | 'delete') => {
    if (action === 'delete' && !window.confirm('删除本地验证聊天及模型上下文？长期记忆和已发生的用量记录分别保留。')) return;
    setBusy(true); setError('');
    try {
      const result = await request<LocalSession>(`/session/${action}`, { session_id: session?.id });
      selectSession(action === 'new' ? result : null); setTurn(null);
    } catch (err) { setError(err instanceof Error ? err.message : '会话操作失败'); }
    finally { setBusy(false); }
  };

  const exportSession = () => {
    if (!session) return;
    const messages = session.messages.map(({ role, content, mode }) => ({ role, content, mode }));
    const url = URL.createObjectURL(new Blob([JSON.stringify({ id: session.id, updated_at: session.updated_at, messages }, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = `unimind-m0-${session.id}.json`; link.click(); URL.revokeObjectURL(url);
  };

  return <main className="min-h-screen bg-[#f7f7f5] px-6 py-10 text-[#202020]">
    <div className="mx-auto max-w-5xl space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-black/10 pb-6">
        <div><p className="mb-2 text-xs tracking-widest text-black/45">UNIMIND / M0</p>
          <h1 className="text-3xl font-semibold">学习界面与 AI 运行时分开验证</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-black/55">本地开发入口。使用隔离的验证账号和合成数据；{health?.mode === 'deepseek-official' ? '模型使用 DeepSeek 官方 API，经本地任务网关限量调用。' : '模型端为本地协议模拟。'}当前验证不代表正式教学效果或生产发布。</p>
          <p className="mt-2 max-w-2xl text-xs leading-6 text-black/45">产品基线：DSH 作为服务端 harness；网页和 UniMind 桌面客户端共用 AI 服务。本页连接本机开发服务，当前仅开放已验证的只读工具。</p>
        </div>
        <a className="text-sm underline underline-offset-4" href="/courses">进入普通课程界面 →</a>
      </header>

      <section className="grid gap-4 sm:grid-cols-3" aria-label="连接状态">
        {[
          ['独立 React 界面', '已运行'],
          ['本地 Host', health ? `SDK ${health.sdk}` : '未连接'],
          ['模型来源', health?.backend_configured && health.model_configured ? (health.mode === 'deepseek-official' ? 'DeepSeek 官方 · 任务网关' : '本地协议模拟 · 任务网关') : '尚未完整配置'],
        ].map(([label, value]) => <div key={label} className="border border-black/10 bg-white p-5">
          <p className="text-xs text-black/45">{label}</p><p className="mt-3 font-medium">{value}</p>
        </div>)}
      </section>

      <div className="grid gap-6 md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <section className="space-y-4 border border-black/10 bg-white p-6">
          <h2 className="font-semibold">小宇只读链路</h2>
          <label className="block text-sm text-black/60" htmlFor="dsh-message">本轮问题</label>
          <textarea id="dsh-message" value={message} onChange={event => setMessage(event.target.value)} maxLength={4000}
            className="min-h-32 w-full resize-y border border-black/15 bg-[#fafaf9] p-3 text-sm leading-6" />
          <div className="flex flex-wrap gap-3 text-sm">
            <button disabled={busy || !health?.backend_configured} onClick={() => void run(false)} className="border border-black/20 px-4 py-2 disabled:opacity-40">读取本人记忆与工具</button>
            <button disabled={busy || !health?.backend_configured || !health?.model_configured} onClick={() => void run(true)} className="bg-black px-4 py-2 text-white disabled:opacity-40">{busy ? '正在验证…' : health?.mode === 'deepseek-official' ? '调用官方模型' : '运行 DSH 协议链路'}</button>
            <button disabled={busy} onClick={() => void refresh()} className="px-2 py-2 text-black/55 underline disabled:opacity-40">刷新连接与会话</button>
          </div>
          {error && <p role="alert" className="border-l-2 border-amber-600 bg-amber-50 p-3 text-sm leading-6">{error}</p>}
          <div className="flex flex-wrap gap-4 border-t border-black/10 pt-3 text-xs text-black/55">
            <button disabled={busy || !health?.backend_configured} onClick={() => void manageSession('new')}>新会话</button>
            <button disabled={busy || !session} onClick={exportSession}>导出对话文字</button>
            <button disabled={busy || !session} onClick={() => void manageSession('delete')}>删除本地会话</button>
          </div>
          {session && <p className="break-all font-mono text-[10px] text-black/40">会话 {session.id} · {session.messages.length} 条消息</p>}
          {session?.notice && <p className="bg-amber-50 p-3 text-xs leading-6">{session.notice}</p>}
          <section aria-label="聊天记录" className="space-y-5">{session?.messages.map((item, index) => <div key={index} className="border-t border-black/10 pt-4">
            <p className="mb-2 text-xs text-black/40">{item.role === 'user' ? '我' : `小宇 · ${item.mode === 'deepseek-official' ? '官方模型' : '本地协议模拟'}`}</p>
            <p className="whitespace-pre-wrap text-sm leading-7">{item.content}</p>
            {!!item.cards?.length && <div className="mt-4 space-y-4">
              <p className="text-xs text-black/40">业务工具返回的结果快照；最新状态请打开详情。</p>
              {item.cards.map((card, cardIndex) => <DshToolCard key={`${card.tool}-${cardIndex}`} card={card} />)}
            </div>}
          </div>)}</section>
          {turn && <p className="border-t border-black/10 pt-3 text-xs leading-6 text-black/50" aria-label="网关用量">
            {turn.gateway.model} · {turn.gateway.requests.length} 次请求 · {turn.gateway.requests.reduce((sum, r) => sum + r.tool_results, 0)} 个工具结果<br />
            总输入 {turn.gateway.requests.reduce((sum, r) => sum + (r.usage.input_tokens || 0) + (r.usage.cache_read_input_tokens || 0) + (r.usage.cache_creation_input_tokens || 0), 0)} / 输出 {turn.gateway.requests.reduce((sum, r) => sum + (r.usage.output_tokens || 0), 0)} tokens。<br />
            输入明细：未缓存 {turn.gateway.requests.reduce((sum, r) => sum + (r.usage.input_tokens || 0), 0)} / 缓存读取 {turn.gateway.requests.reduce((sum, r) => sum + (r.usage.cache_read_input_tokens || 0), 0)} / 缓存创建 {turn.gateway.requests.reduce((sum, r) => sum + (r.usage.cache_creation_input_tokens || 0), 0)}。<br />最多 4 次请求，每次输出 1024 tokens。未接正式扣费。
          </p>}
        </section>

        <aside className="space-y-6 border border-black/10 bg-white p-6">
          <section><h2 className="font-semibold">当前验证身份</h2>
            <p className="mt-3 text-sm text-black/55">{context ? `${context.student.name} · #${context.student.id}` : '读取后显示；凭据由 Host 持有'}</p>
          </section>
          <section><h2 className="font-semibold">学生长期记忆</h2>
            {context?.memory.items.length ? context.memory.items.map(item => <p key={item.id} className="mt-3 text-sm leading-6"><span className="text-black/45">{item.key}：</span>{item.value}</p>) : <p className="mt-3 text-sm text-black/45">{context ? '当前没有有效的长期记忆' : '尚未读取记忆'}</p>}
            {context && <p className="mt-3 break-all font-mono text-[10px] text-black/35">版本 {context.memory.version}</p>}
          </section>
          <section><h2 className="font-semibold">本轮候选工具</h2>
            <p className="mt-2 text-xs leading-6 text-black/45">{context?.routing ? `已鉴权目录 ${context.routing.catalog_count} 个，本轮候选 ${context.routing.candidate_count} 个；当前可执行 ${context.tools.length} / ${context.permitted_tool_count} 个只读工具。` : '按权限与问题选择'}</p>
            <ul className="mt-3 space-y-2">{context?.tools.map(tool => <li key={tool.function.name} className="break-all border-t border-black/5 pt-2 font-mono text-xs">{tool.function.name}</li>)}</ul>
            {context?.routing && <p className="mt-3 text-xs leading-6 text-black/45">候选 Schema {context.routing.candidate_schema_bytes} bytes；本轮实际开放 Schema {context.routing.executable_schema_bytes} bytes。模型意图分类尚待接入 DSH。</p>}
            {!!context?.routing?.pending_names.length && <details className="mt-3 text-xs leading-6 text-black/50"><summary>候选中 {context.routing.pending_names.length} 项尚未迁移执行</summary><p className="mt-2 break-all font-mono">{context.routing.pending_names.join('、')}</p></details>}
          </section>
        </aside>
      </div>
    </div>
  </main>;
}
