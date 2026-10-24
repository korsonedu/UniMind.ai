import { useCallback, useEffect, useRef, useState } from 'react';
import AgentChatLayout, { type AgentChatLayoutProps } from '@/components/AgentChatLayout';
import type { Bot } from '@/hooks/useAgentConversation';
import api from '@/lib/api';
import { notesApi, notebookPath, type Note, type Notebook, type NoteBinding } from '@/lib/notes';
import { useXiaoYuStore } from '@/store/useXiaoYuStore';
import { toast } from 'sonner';
import { ArrowClockwise, Link as LinkIcon, LinkBreak, Plus, X } from '@phosphor-icons/react';

interface ReferenceState { key: string; ready: boolean; ids: number[]; bot: number; conversationId: string }
interface Props {
  note: Note; notebooks: Notebook[]; notes: Note[]; beforeSend: () => Promise<void>;
  selection: string; clearSelection: () => void; openRequest: number;
}
export default function NotesAgentPanel(props: Props) {
  const [bots, setBots] = useState<Bot[]>([]);
  const [botId, setBotId] = useState<number | null>(null);
  const [botError, setBotError] = useState(false);
  const [sessionControls, setSessionControls] = useState<Parameters<NonNullable<AgentChatLayoutProps['onSessionsReady']>>[0] | null>(null);
  const reference = useRef<ReferenceState | null>(null);
  const noteIdRef = useRef(props.note.id);
  noteIdRef.current = props.note.id;
  const seed = useRef<number | null>(props.note.id);
  const seeded = useRef(new Set<string>());
  const lastRequest = useRef(props.openRequest);
  const initialConversationId = useRef(useXiaoYuStore.getState().conversationId);
  const [newSeed, setNewSeed] = useState(0);
  if (lastRequest.current !== props.openRequest) { lastRequest.current = props.openRequest; seed.current = reference.current && seeded.current.has(`${reference.current.key}:${props.note.id}`) ? null : props.note.id; }
  const loadBots = useCallback(() => {
    setBotError(false);
    void api.get<Bot[]>('/ai/bots/').then(({ data }) => { setBots(data); setBotId(data.find(bot => bot.name === '小宇')?.id ?? data[0]?.id ?? null); }).catch(() => setBotError(true));
  }, []);
  useEffect(loadBots, [loadBots]);
  const findBot = useCallback((available: Bot[]) => available.find(bot => bot.id === botId), [botId]);
  const sessionsReady = useCallback<NonNullable<AgentChatLayoutProps['onSessionsReady']>>(setSessionControls, []);
  const resetConversation = useCallback<NonNullable<AgentChatLayoutProps['onReset']>>(handler => {
    reference.current = null; seed.current = noteIdRef.current; setNewSeed(value => value + 1); handler();
  }, []);
  const loadConversation = useCallback<NonNullable<AgentChatLayoutProps['onLoadSession']>>((session, handler) => {
    reference.current = null; seed.current = null; handler(session);
  }, []);
  const saveBeforeSend = async () => {
    const state = reference.current;
    await props.beforeSend();
    if (!state?.ready || reference.current !== state) throw new Error('参考笔记尚未加载或保存，请重试后再提问。');
  };
  const currentBot = bots.find(bot => bot.id === botId);
  return <div className="notes-agent-panel">
    <div className="notes-agent-controls">
      <select aria-label="选择只读 Agent" value={botId ?? ''} onChange={e => { reference.current = null; seed.current = props.note.id; setSessionControls(null); setBotId(Number(e.target.value)); }}>
        {!bots.length && <option value="">{botError ? 'Agent 加载失败' : '加载 Agent…'}</option>}{bots.map(bot => <option key={bot.id} value={bot.id}>{bot.name}</option>)}
      </select>
      {botError && <button aria-label="重新加载 Agent" title="重试" onClick={loadBots}><ArrowClockwise size={17} /></button>}
      {sessionControls && <button aria-label="新会话" title="新会话" onClick={() => sessionControls.newConversation()}><Plus size={19} /></button>}
      {sessionControls && <select aria-label="切换讨论会话" value={sessionControls.activeSessionId ?? ''} onChange={e => {
        seed.current = null; reference.current = null;
        const session = sessionControls.sessions.find(s => s.id === Number(e.target.value));
        if (session) sessionControls.loadSession(session);
      }}><option value="" disabled>新会话</option>{[...sessionControls.sessions].reverse().map(session => <option key={session.id} value={session.id}>{session.title || session.label}</option>)}</select>}
    </div>
    {botId && currentBot ? <AgentChatLayout key={botId} appearance="native" layout="inline" findBot={findBot} skills={[]} typewriterWords={[]} chatPlaceholder="围绕笔记提问…" landingTitle="笔记讨论" landingDescription="" botDisplayName={currentBot.name}
      initialConversationId={currentBot.name === '小宇' ? initialConversationId.current : undefined}
      onSessionsReady={sessionsReady}
      onReset={resetConversation}
      onLoadSession={loadConversation}
      beforeSend={saveBeforeSend}
      getExtraPayload={() => ({ note_selection: props.selection.slice(0, 3000) })}
      onDone={refresh => { props.clearSelection(); refresh(); }}
      contextPanel={({ bot, conversationId }) => bot && <ReferenceContext key={`${bot.id}:${conversationId}`} bot={bot} conversationId={conversationId} {...props} reference={reference} seed={seed} seeded={seeded} seedTrigger={`${props.openRequest}:${newSeed}`} />}
    /> : !botError && !bots.length ? <p className="notes-empty">正在加载 Agent…</p> : <p className="notes-empty">暂无可用 Agent，仍可正常编辑笔记。</p>}
  </div>;
}

function ReferenceContext({ bot, conversationId, note, notes, notebooks, selection, clearSelection, reference, seed, seeded, seedTrigger }: Props & {
  bot: Bot; conversationId: string; reference: React.RefObject<ReferenceState | null>;
  seed: React.RefObject<number | null>; seeded: React.RefObject<Set<string>>; seedTrigger: string;
}) {
  const key = `${bot.id}:${conversationId}`;
  const [ids, setIds] = useState<number[]>([]);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [bindings, setBindings] = useState<NoteBinding[]>([]);
  const [bindingError, setBindingError] = useState(false);
  const [bindingBusy, setBindingBusy] = useState(false);
  const [source, setSource] = useState('');
  const [query, setQuery] = useState('');
  const ownState = useRef<ReferenceState>({ key, ready: false, ids: [], bot: bot.id, conversationId });
  const mounted = useRef(true);
  // Mark the new session unavailable before any event can send with the old references.
  reference.current = ownState.current;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    const controller = new AbortController();
    ownState.current.ready = false; setReady(false); setError('');
    void notesApi.references(bot.id, conversationId, controller.signal).then(async loaded => {
      if (controller.signal.aborted) return;
      let next = loaded;
      if (seed.current !== null && !seeded.current.has(`${key}:${seed.current}`)) {
        const requested = seed.current;
        next = [...new Set([...loaded, requested])];
        await notesApi.saveReferences(bot.id, conversationId, next);
        if (controller.signal.aborted) return;
        seeded.current.add(`${key}:${requested}`);
        if (seed.current === requested) seed.current = null;
      }
      if (controller.signal.aborted) return;
      ownState.current.ids = next; ownState.current.ready = true; setIds(next); setReady(true);
    }).catch(() => { if (!controller.signal.aborted) setError('参考加载失败，已暂停发问。请重试，原参考不会被覆盖。'); });
    return () => { controller.abort(); ownState.current.ready = false; };
  }, [bot.id, conversationId, retry, seedTrigger, seed]);
  const loadBindings = useCallback(() => {
    setBindingError(false);
    void notesApi.bindings(bot.id).then(result => { if (mounted.current) setBindings(result); }).catch(() => { if (mounted.current) setBindingError(true); });
  }, [bot.id]);
  useEffect(loadBindings, [loadBindings]);
  const replace = async (next: number[]) => {
    ownState.current.ready = false; setReady(false); setError('');
    try {
      await notesApi.saveReferences(bot.id, conversationId, next);
      if (!mounted.current) return;
      ownState.current.ids = next; ownState.current.ready = true; setIds(next); setReady(true);
    } catch { if (mounted.current) setError('参考保存失败，已暂停发问。请重试加载确认当前参考。'); }
  };
  const changeBinding = async (action: () => Promise<unknown>) => {
    setBindingBusy(true);
    try { await action(); loadBindings(); setSource(''); } catch { toast.error('长期关联更新失败，请重试。'); } finally { setBindingBusy(false); }
  };
  return <div className="notes-reference-context">
    <div className="notes-row"><strong>本次会话参考</strong><span>{ready ? `${ids.length} 篇` : '暂停发问'}</span></div>
    {error ? <p role="alert" className="notes-error">{error} <button aria-label="重试加载参考" title="重试" onClick={() => setRetry(value => value + 1)}><ArrowClockwise size={16} /></button></p> : !ready && <p>正在同步参考…</p>}
    <div className="notes-reference-chips">{ids.map(id => <span key={id}>{notes.find(item => item.id === id)?.title || (id === note.id ? note.title : `笔记 ${id}`)}<button aria-label={`移除参考笔记 ${id}`} disabled={!ready} onClick={() => void replace(ids.filter(value => value !== id))}><X size={14} /></button></span>)}</div>
    <details><summary>添加参考笔记</summary><input aria-label="搜索参考笔记" placeholder="搜索笔记" value={query} onChange={e => setQuery(e.target.value)} /><select aria-label="添加会话参考" value="" disabled={!ready} onChange={e => { if (e.target.value) void replace([...ids, Number(e.target.value)]); }}><option value="">选择笔记…</option>{notes.filter(item => !ids.includes(item.id) && `${item.title} ${item.content}`.toLowerCase().includes(query.toLowerCase())).map(item => <option key={item.id} value={item.id}>{item.title || '未命名笔记'} · {notebookPath(item.notebook, notebooks)}</option>)}</select></details>
    {selection && <div className="notes-selected-text"><span>本次提问重点（{selection.length}/3000）</span><button aria-label="清除选中片段" title="清除" onClick={clearSelection}><X size={16} /></button><blockquote>{selection}</blockquote></div>}
    <details><summary>长期关联 · {bindings.length} 项</summary>
      {bindingError && <p className="notes-error">关联加载失败。<button aria-label="重新加载关联" title="重试" onClick={loadBindings}><ArrowClockwise size={16} /></button></p>}
      {bindings.map(binding => <div className="notes-row" key={binding.id}><span>{binding.note ? `笔记：${notes.find(item => item.id === binding.note)?.title || binding.note}` : `笔记本：${notebookPath(binding.notebook, notebooks)}（含子目录）`}</span><button aria-label="解除关联" title="解除关联" disabled={bindingBusy} onClick={() => void changeBinding(() => notesApi.unbind(binding.id))}><LinkBreak size={17} /></button></div>)}
      <select aria-label="选择长期关联来源" value={source} onChange={e => setSource(e.target.value)}><option value="">选择笔记或笔记本…</option><optgroup label="笔记">{notes.map(item => <option key={item.id} value={`note:${item.id}`}>{item.title || '未命名笔记'}</option>)}</optgroup><optgroup label="笔记本（含子目录）">{notebooks.map(book => <option key={book.id} value={`notebook:${book.id}`}>{notebookPath(book.id, notebooks)}</option>)}</optgroup></select>
      <button aria-label={`关联到 ${bot.name}`} title={`关联到 ${bot.name}`} disabled={!source || bindingBusy || bindingError} onClick={() => { const [kind, id] = source.split(':'); void changeBinding(() => notesApi.bind(bot.id, kind === 'note' ? { note: Number(id) } : { notebook: Number(id) })); }}><LinkIcon size={18} /></button>
    </details>
  </div>;
}
