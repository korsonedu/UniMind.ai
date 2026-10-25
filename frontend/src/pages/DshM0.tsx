import { useEffect, useState } from 'react';

type Health = { sdk: string; backend_configured: boolean; model_configured: boolean };
type Context = {
  student: { id: number; name: string };
  memory: { version: string; items: { id: number; key: string; value: string }[] };
  tools: { function: { name: string; description: string } }[];
  permitted_tool_count: number;
};

async function request<T>(path: string, message?: string): Promise<T> {
  const response = await fetch(`/dsh-m0${path}`, message === undefined ? undefined : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '本地服务暂不可用');
  return data;
}

export default function DshM0() {
  const [health, setHealth] = useState<Health | null>(null);
  const [context, setContext] = useState<Context | null>(null);
  const [message, setMessage] = useState('查询我的学习统计，并根据我的讲解偏好解释结果。');
  const [answer, setAnswer] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    setError('');
    try { setHealth(await request<Health>('/health')); }
    catch { setHealth(null); setError('Host 尚未启动。课程和普通业务界面仍可独立使用。'); }
  };
  useEffect(() => { void refresh(); }, []);

  const run = async (chat: boolean) => {
    setBusy(true); setError('');
    if (chat) setAnswer('');
    try {
      const latest = await request<Context>('/context', message);
      setContext(latest);
      if (chat) setAnswer((await request<{ content: string }>('/chat', message)).content);
    } catch (err) { setError(err instanceof Error ? err.message : '调用失败'); }
    finally { setBusy(false); }
  };

  return <main className="min-h-screen bg-[#f7f7f5] px-6 py-10 text-[#202020]">
    <div className="mx-auto max-w-5xl space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-black/10 pb-6">
        <div><p className="mb-2 text-xs tracking-widest text-black/45">UNIMIND / M0</p>
          <h1 className="text-3xl font-semibold">学习界面与 AI 运行时分开验证</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-black/55">本地开发入口。使用隔离的验证账号和合成数据；模型端为协议夹具，不代表真实模型教学效果或生产发布。</p>
        </div>
        <a className="text-sm underline underline-offset-4" href="/courses">进入普通课程界面 →</a>
      </header>

      <section className="grid gap-4 sm:grid-cols-3" aria-label="连接状态">
        {[
          ['独立 React 界面', '已运行'],
          ['本地 Host', health ? `SDK ${health.sdk}` : '未连接'],
          ['业务与协议端点', health?.backend_configured && health.model_configured ? '已配置，等待验证' : '尚未完整配置'],
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
            <button disabled={busy || !health?.backend_configured || !health?.model_configured} onClick={() => void run(true)} className="bg-black px-4 py-2 text-white disabled:opacity-40">{busy ? '正在验证…' : '运行 DSH 协议链路'}</button>
            <button onClick={() => void refresh()} className="px-2 py-2 text-black/55 underline">刷新连接</button>
          </div>
          {error && <p role="alert" className="border-l-2 border-amber-600 bg-amber-50 p-3 text-sm leading-6">{error}</p>}
          {answer && <div aria-label="小宇结果" className="whitespace-pre-wrap border-t border-black/10 pt-5 text-sm leading-7">{answer}</div>}
        </section>

        <aside className="space-y-6 border border-black/10 bg-white p-6">
          <section><h2 className="font-semibold">当前验证身份</h2>
            <p className="mt-3 text-sm text-black/55">{context ? `${context.student.name} · #${context.student.id}` : '读取后显示；凭据由 Host 持有'}</p>
          </section>
          <section><h2 className="font-semibold">学生长期记忆</h2>
            {context?.memory.items.length ? context.memory.items.map(item => <p key={item.id} className="mt-3 text-sm leading-6"><span className="text-black/45">{item.key}：</span>{item.value}</p>) : <p className="mt-3 text-sm text-black/45">尚未读取记忆</p>}
            {context && <p className="mt-3 break-all font-mono text-[10px] text-black/35">版本 {context.memory.version}</p>}
          </section>
          <section><h2 className="font-semibold">本轮候选工具</h2>
            <p className="mt-2 text-xs text-black/45">{context ? `${context.tools.length} 个候选 / ${context.permitted_tool_count} 个允许的只读工具` : '按权限与问题选择'}</p>
            <ul className="mt-3 space-y-2">{context?.tools.map(tool => <li key={tool.function.name} className="break-all border-t border-black/5 pt-2 font-mono text-xs">{tool.function.name}</li>)}</ul>
          </section>
        </aside>
      </div>
    </div>
  </main>;
}
