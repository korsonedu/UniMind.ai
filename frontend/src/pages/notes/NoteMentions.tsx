import { useEffect, useReducer, useRef, useState, type KeyboardEvent, type RefObject } from 'react';
import { Link } from 'react-router-dom';
import { FileText, X } from '@phosphor-icons/react';
import { notesApi, notebookPath, type Notebook, type NoteSummary } from '@/lib/notes';
import '@/styles/note-mentions.css';

interface SessionReferences {
  key: string; notes: NoteSummary[]; ready: boolean; error: string;
  pending?: Promise<void>;
}
interface Options {
  enabled: boolean; disabled: boolean; botId?: number; conversationId: string; input: string;
  setInput: (value: string) => void; textareaRef: RefObject<HTMLTextAreaElement | null>;
}
export function useNoteMentions({ enabled, disabled, botId, conversationId, input, setInput, textareaRef }: Options) {
  const [, redraw] = useReducer(value => value + 1, 0);
  const key = enabled && botId ? `${botId}:${conversationId}` : '';
  const sessionRef = useRef<SessionReferences>({ key, notes: [], ready: false, error: '' });
  if (sessionRef.current.key !== key) sessionRef.current = { key, notes: [], ready: false, error: '' };
  const session = sessionRef.current;
  const [books, setBooks] = useState<Notebook[]>([]);
  const [retry, setRetry] = useState(0);
  const [query, setQuery] = useState<{ from: number; to: number; text: string } | null>(null);
  const [matches, setMatches] = useState<NoteSummary[]>([]);
  const [searchState, setSearchState] = useState<'loading' | 'ready' | 'error'>('ready');
  const [active, setActive] = useState(0);
  const current = () => sessionRef.current === session;
  useEffect(() => {
    setQuery(null);
    if (!key || !botId) return;
    const controller = new AbortController();
    session.ready = false; session.error = '';
    session.pending = (async () => {
      try {
        const [ids, folders] = await Promise.all([notesApi.references(botId, conversationId, controller.signal), notesApi.notebooks()]);
        const notes = ids.length ? await notesApi.lookup({ ids: ids.join(',') }, controller.signal) : [];
        if (!controller.signal.aborted && current()) { session.notes = notes; session.ready = true; setBooks(folders); }
      } catch { if (!controller.signal.aborted && current()) session.error = '笔记引用加载失败'; }
      finally { if (!controller.signal.aborted && current()) { session.pending = undefined; redraw(); } }
    })();
    redraw();
    return () => controller.abort();
  }, [key, retry]);
  useEffect(() => { if (!input) setQuery(null); }, [input]);
  useEffect(() => {
    if (!query || !key) return;
    const controller = new AbortController();
    setMatches([]); setActive(0); setSearchState('loading');
    const timer = setTimeout(() => {
      void notesApi.lookup({ q: query.text }, controller.signal).then(notes => {
        if (!controller.signal.aborted) { setMatches(notes); setSearchState('ready'); }
      }).catch(() => { if (!controller.signal.aborted) setSearchState('error'); });
    }, 120);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [query?.text, key]);
  const updateQuery = (value: string, cursor: number) => {
    if (!enabled) return;
    const match = value.slice(0, cursor).match(/(?:^|\s)@([^\s@]*)$/u);
    setQuery(match ? { from: cursor - match[1].length - 1, to: cursor, text: match[1] } : null);
  };
  const persist = (notes: NoteSummary[]) => {
    if (disabled || !botId || !session.ready || session.pending) return;
    session.notes = notes; session.error = '';
    session.pending = notesApi.saveReferences(botId, conversationId, notes.map(note => note.id)).then(() => {
      if (current()) session.error = '';
    }).catch(() => { if (current()) session.error = '笔记引用保存失败'; }).finally(() => {
      if (current()) { session.pending = undefined; redraw(); }
    });
    redraw();
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
    await session.pending;
    if (!current() || !session.ready || session.error) throw new Error(session.error || '笔记引用正在加载，请稍后重试。');
    if (!session.notes.length) return;
    const latest = await notesApi.lookup({ ids: session.notes.map(note => note.id).join(',') });
    if (!current()) throw new Error('会话已切换，请重新发送。');
    if (latest.length !== session.notes.length) throw new Error('引用的笔记已不可用，请移除后重试。');
    session.notes = latest; redraw();
  };
  const panel = !key ? null : <div className="note-mentions">
    {!!session.notes.length && <div className="note-mention-chips">{session.notes.map(note => <span className="note-mention-chip" key={note.id}><FileText size={14} /><Link to={`/notes/${note.id}`} title={notebookPath(note.notebook, books)}>{note.title || '未命名笔记'}</Link><button type="button" aria-label={`移除引用 ${note.title}`} disabled={disabled || !!session.pending} onClick={() => persist(session.notes.filter(item => item.id !== note.id))}><X size={13} /></button></span>)}</div>}
    {session.error && <div className="note-mention-error" role="alert">{session.error}<button type="button" onClick={() => session.ready ? persist(session.notes) : setRetry(value => value + 1)}>重试</button></div>}
    {query && <div className="note-mention-menu" role="listbox" aria-label="选择笔记">{searchState !== 'ready' ? <div role="status">{searchState === 'loading' ? '搜索中…' : '搜索失败，请重新输入'}</div> : !matches.length ? <div role="status">没有匹配的笔记</div> : matches.map((note, index) => <button type="button" key={note.id} role="option" aria-selected={index === active} disabled={disabled || !session.ready || !!session.pending || session.notes.length >= 30 && !session.notes.some(item => item.id === note.id)} onMouseDown={event => event.preventDefault()} onClick={() => choose(note)} onMouseEnter={() => setActive(index)}><FileText size={18} /><span><strong>{note.title || '未命名笔记'}</strong><small>{notebookPath(note.notebook, books)}</small></span></button>)}</div>}
  </div>;
  return { panel, beforeSend, onKeyDown, updateQuery, payload: () => ({ note_ids: session.notes.map(note => note.id) }) };
}

export function NoteAttachments({ attachments }: { attachments: unknown }) {
  if (!Array.isArray(attachments)) return null;
  const notes = attachments.filter((item): item is { note_id: number; title: string; version: number } => !!item && Number.isInteger(item.note_id) && typeof item.title === 'string' && Number.isInteger(item.version));
  return !notes.length ? null : <div className="note-mention-chips note-message-attachments">{notes.map(note => <Link className="note-mention-chip" key={note.note_id} to={`/notes/${note.note_id}`} title={`发送时版本 v${note.version}`}><FileText size={14} />{note.title || '未命名笔记'}</Link>)}</div>;
}
