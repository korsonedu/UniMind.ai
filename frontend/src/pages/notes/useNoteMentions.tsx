import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore, type KeyboardEvent, type RefObject } from 'react';
import { Link } from 'react-router-dom';
import { FileText, X } from '@phosphor-icons/react';
import { notesApi, notebookPath, type Notebook, type NoteSummary } from '@/lib/notes';
import '@/styles/note-mentions.css';

interface SessionReferences {
  key: string; notes: NoteSummary[]; ready: boolean; error: string;
  pending?: Promise<void>;
}
function createReferenceSession(key: string) {
  let snapshot: SessionReferences = { key, notes: [], ready: false, error: '' };
  const listeners = new Set<() => void>();
  return {
    getSnapshot: () => snapshot,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    update: (patch: Partial<SessionReferences>) => {
      snapshot = { ...snapshot, ...patch };
      listeners.forEach(listener => listener());
    },
  };
}
interface Options {
  enabled: boolean; disabled: boolean; botId?: number; conversationId: string; input: string;
  setInput: (value: string) => void; textareaRef: RefObject<HTMLTextAreaElement | null>;
}
export function useNoteMentions({ enabled, disabled, botId, conversationId, input, setInput, textareaRef }: Options) {
  const key = enabled && botId ? `${botId}:${conversationId}` : '';
  const store = useMemo(() => createReferenceSession(key), [key]);
  const session = useSyncExternalStore(store.subscribe, store.getSnapshot);
  const sessionRef = useRef(store);
  useLayoutEffect(() => { sessionRef.current = store; }, [store]);
  const [books, setBooks] = useState<Notebook[]>([]);
  const [retry, setRetry] = useState(0);
  const [query, setQuery] = useState<{ from: number; to: number; text: string } | null>(null);
  const [querySource, setQuerySource] = useState({ key, input });
  if (querySource.key !== key || querySource.input !== input) {
    setQuerySource({ key, input });
    if (querySource.key !== key || !input) setQuery(null);
  }
  const [matches, setMatches] = useState<NoteSummary[]>([]);
  const [searchState, setSearchState] = useState<'loading' | 'ready' | 'error'>('ready');
  const [active, setActive] = useState(0);
  const current = useCallback(() => sessionRef.current === store, [store]);
  useEffect(() => {
    if (!key || !botId) return;
    const controller = new AbortController();
    store.update({ ready: false, error: '' });
    const pending = (async () => {
      try {
        const [ids, folders] = await Promise.all([notesApi.references(botId, conversationId, controller.signal), notesApi.notebooks()]);
        const notes = ids.length ? await notesApi.lookup({ ids: ids.join(',') }, controller.signal) : [];
        if (!controller.signal.aborted && current()) { store.update({ notes, ready: true }); setBooks(folders); }
      } catch { if (!controller.signal.aborted && current()) store.update({ error: '笔记引用加载失败' }); }
      finally { if (!controller.signal.aborted && current()) { store.update({ pending: undefined }); } }
    })();
    store.update({ pending });
    return () => controller.abort();
  }, [key, retry, botId, conversationId, current, store]);
  const queryText = query?.text;
  const searchKey = `${key}:${queryText ?? ''}`;
  const [previousSearchKey, setPreviousSearchKey] = useState(searchKey);
  if (previousSearchKey !== searchKey) {
    setPreviousSearchKey(searchKey); setMatches([]); setActive(0); setSearchState('loading');
  }
  useEffect(() => {
    if (queryText === undefined || !key) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      void notesApi.lookup({ q: queryText }, controller.signal).then(notes => {
        if (!controller.signal.aborted) { setMatches(notes); setSearchState('ready'); }
      }).catch(() => { if (!controller.signal.aborted) setSearchState('error'); });
    }, 120);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [queryText, key]);
  const updateQuery = (value: string, cursor: number) => {
    if (!enabled) return;
    const match = value.slice(0, cursor).match(/(?:^|\s)@([^\s@]*)$/u);
    setQuery(match ? { from: cursor - match[1].length - 1, to: cursor, text: match[1] } : null);
  };
  const persist = (notes: NoteSummary[]) => {
    const session = store.getSnapshot();
    if (disabled || !botId || !session.ready || session.pending) return;
    store.update({ notes, error: '' });
    const pending = notesApi.saveReferences(botId, conversationId, notes.map(note => note.id)).then(() => {
      if (current()) store.update({ error: '' });
    }).catch(() => { if (current()) store.update({ error: '笔记引用保存失败' }); }).finally(() => {
      if (current()) { store.update({ pending: undefined }); }
    });
    store.update({ pending });
  };
  const choose = (note: NoteSummary) => {
    if (disabled || !query || !session.ready || session.pending || session.notes.length >= 30 && !session.notes.some(item => item.id === note.id)) return;
    const cursor = query.from;
    setInput(input.slice(0, query.from) + input.slice(query.to));
    setQuery(null);
    if (!session.notes.some(item => item.id === note.id)) persist([...session.notes, note]);
    requestAnimationFrame(() => { textareaRef.current?.focus(); textareaRef.current?.setSelectionRange(cursor, cursor); });
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>, composing: boolean) => {
    if (!query || composing || event.nativeEvent.isComposing) return false;
    if (event.key === 'Escape') { event.preventDefault(); setQuery(null); return true; }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault(); setActive(value => matches.length ? (value + (event.key === 'ArrowDown' ? 1 : -1) + matches.length) % matches.length : 0); return true;
    }
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); if (matches[active]) choose(matches[active]); return true; }
    return false;
  };
  const beforeSend = async () => {
    if (!key) return;
    await store.getSnapshot().pending;
    const session = store.getSnapshot();
    if (!current() || !session.ready || session.error) throw new Error(session.error || '笔记引用正在加载，请稍后重试。');
    if (!session.notes.length) return;
    const latest = await notesApi.lookup({ ids: session.notes.map(note => note.id).join(',') });
    if (!current()) throw new Error('会话已切换，请重新发送。');
    if (latest.length !== session.notes.length) throw new Error('引用的笔记已不可用，请移除后重试。');
    store.update({ notes: latest });
  };
  const panel = !key ? null : <div className="note-mentions">
    {!!session.notes.length && <div className="note-mention-chips">{session.notes.map(note => <span className="note-mention-chip" key={note.id}><FileText size={14} /><Link to={`/notes/${note.id}`} title={notebookPath(note.notebook, books)}>{note.title || '未命名笔记'}</Link><button type="button" aria-label={`移除引用 ${note.title}`} disabled={disabled || !!session.pending} onClick={() => persist(session.notes.filter(item => item.id !== note.id))}><X size={13} /></button></span>)}</div>}
    {session.error && <div className="note-mention-error" role="alert">{session.error}<button type="button" onClick={() => session.ready ? persist(session.notes) : setRetry(value => value + 1)}>重试</button></div>}
    {query && <div className="note-mention-menu" role="listbox" aria-label="选择笔记">{searchState !== 'ready' ? <div role="status">{searchState === 'loading' ? '搜索中…' : '搜索失败，请重新输入'}</div> : !matches.length ? <div role="status">没有匹配的笔记</div> : matches.map((note, index) => <button type="button" key={note.id} role="option" aria-selected={index === active} disabled={disabled || !session.ready || !!session.pending || session.notes.length >= 30 && !session.notes.some(item => item.id === note.id)} onMouseDown={event => event.preventDefault()} onClick={() => choose(note)} onMouseEnter={() => setActive(index)}><FileText size={18} /><span><strong>{note.title || '未命名笔记'}</strong><small>{notebookPath(note.notebook, books)}</small></span></button>)}</div>}
  </div>;
  return { panel, beforeSend, onKeyDown, updateQuery, payload: () => ({ note_ids: store.getSnapshot().notes.map(note => note.id) }) };
}
