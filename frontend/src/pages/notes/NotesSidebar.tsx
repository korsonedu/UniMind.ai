import { useCallback, useEffect, useEffectEvent, useRef, useState } from 'react';
import { ArrowLeft, ArrowSquareOut, CaretDown, Check, FileText, MagnifyingGlass, Plus, Star, X } from '@phosphor-icons/react';
import { useBlocker, useNavigate } from 'react-router-dom';
import { noteDraft, notesApi, type Note, type NoteDraft } from '@/lib/notes';
import { cacheNote, cacheNotes, loadOfflineCache } from '@/lib/offlineData';
import { useAuthStore } from '@/store/useAuthStore';
import NoteEditor from './NoteEditor';
import { useNoteSave } from './useNoteSave';
import '@/styles/notes.css';

const blankNote = (): Note => ({ id: 0, title: '', content: '', notebook: null, tags: [], is_favorite: false, version: 1, deleted_at: null, updated_at: '', backlinks: [] });

export default function NotesSidebar({ userId, initialNoteId, openRequest, visible, onSelect, onClose }: {
  userId: number; initialNoteId: number | null; openRequest?: { id: number; sequence: number } | null; visible: boolean; onSelect: (id: number | null, title?: string) => void; onClose: () => void;
}) {
  const navigate = useNavigate();
  const [items, setItems] = useState<Note[]>([]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [favorites, setFavorites] = useState(false);
  const [loading, setLoading] = useState(true);
  const [switching, setSwitching] = useState(false);
  const [creating, setCreating] = useState(false);
  const [message, setMessage] = useState('');
  const [listError, setListError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [draft, setDraft] = useState(blankNote);
  const [editorKey, setEditorKey] = useState(0);
  const draftRef = useRef(draft);
  const creation = useRef<Promise<void> | null>(null);
  const operation = useRef(false);
  const initialized = useRef(false);
  const firstNoteId = useRef(initialNoteId);
  const active = useRef(true);
  const content = useRef<HTMLDivElement>(null);
  const onSaved = useCallback((value: Note) => {
    setMessage('');
    setItems(current => [value, ...current.filter(item => item.id !== value.id)]);
    void cacheNote(userId, value);
    onSelect(value.id, value.title);
  }, [userId, onSelect]);
  const { note, dirty, status, error, load, change, flush } = useNoteSave(onSaved);
  const currentId = useRef<number | null>(null);
  const ownsSession = () => active.current && useAuthStore.getState().user?.id === userId;
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  useEffect(() => {
    if (visible && !pickerOpen) content.current?.querySelector<HTMLElement>('[contenteditable=true]')?.focus({ preventScroll: true });
  }, [visible, pickerOpen]);
  useEffect(() => {
    const protect = (event: BeforeUnloadEvent) => {
      if (creation.current || (!currentId.current && (draftRef.current.content.trim() || draftRef.current.title.trim()))) { event.preventDefault(); event.returnValue = ''; }
    };
    const sync = () => { void flush().catch(() => {}); };
    window.addEventListener('beforeunload', protect);
    window.addEventListener('online', sync);
    return () => { window.removeEventListener('beforeunload', protect); window.removeEventListener('online', sync); };
  }, [flush]);

  const readNote = useCallback(async (id: number) => {
    const cached = await loadOfflineCache(userId);
    const local = cached?.notes.find(item => item.id === id);
    const pending = cached?.outbox.find(entry => entry.noteId === id);
    if (pending && local) return { ...local, ...pending.draft, version: pending.baseVersion };
    try {
      const result = await notesApi.get(id);
      return local && local.version > result.version ? local : result;
    } catch (cause) {
      if (local && !local.deleted_at) return local;
      throw cause;
    }
  }, [userId]);

  useEffect(() => {
    let cancelled = false;
    const refreshNotes = async () => {
      setListError('');
      try {
        let result: Note[];
        try { result = await notesApi.list(); void cacheNotes(userId, result); }
        catch {
          const cached = await loadOfflineCache(userId);
          if (!cached) throw new Error('no-cache');
          result = cached.notes.filter(item => !item.deleted_at);
          if (!cancelled) setListError('当前显示本地笔记，联网后可刷新。');
        }
        if (cancelled) return;
        setItems(result);
        if (!initialized.current) {
          const id = result.find(item => item.id === firstNoteId.current)?.id ?? result[0]?.id;
          const next = id ? await readNote(id) : null;
          if (cancelled) return;
          load(next); currentId.current = next?.id ?? null; onSelect(next?.id ?? null, next?.title);
          initialized.current = true;
        }
      } catch { if (!cancelled) setListError('笔记加载失败，请重试。你仍可以先写下内容。'); }
      finally { if (!cancelled) setLoading(false); }
    };
    void refreshNotes();
    return () => { cancelled = true; };
  }, [load, onSelect, readNote, refresh, userId]);

  const createDraft = () => {
    if (creation.current) return creation.current;
    setCreating(true); setMessage('');
    creation.current = (async () => {
      try {
        const result = await notesApi.create(null, noteDraft(draftRef.current));
        if (!ownsSession()) return;
        load(result); currentId.current = result.id; onSelect(result.id, result.title);
        change(noteDraft(draftRef.current));
        onSaved(result);
      } catch (cause) {
        if (ownsSession()) setMessage('新笔记未能保存，文字仍在这里。请重试保存。');
        throw cause;
      } finally {
        creation.current = null;
        if (ownsSession()) setCreating(false);
      }
    })();
    return creation.current;
  };
  const edit = (patch: Partial<NoteDraft>) => {
    initialized.current = true;
    if (currentId.current) { change(patch); return; }
    const next = { ...draftRef.current, ...patch };
    draftRef.current = next; setDraft(next);
    if (!message && (next.content.trim() || next.title.trim())) void createDraft().catch(() => {});
  };
  const save = async () => {
    if (creation.current) await creation.current;
    if (!currentId.current && (draftRef.current.content.trim() || draftRef.current.title.trim())) await createDraft();
    await flush();
  };
  const run = async (work: () => Promise<void> | void) => {
    if (operation.current || loading || blocker.state !== 'unblocked') return;
    operation.current = true; setSwitching(true); setMessage('');
    try { await save(); if (ownsSession()) await work(); }
    catch { if (ownsSession()) setMessage('操作未完成，当前内容已保留。请检查网络或保存状态后重试。'); }
    finally { operation.current = false; if (ownsSession()) setSwitching(false); }
  };
  const open = (id: number) => run(async () => {
    if (id !== currentId.current) {
      const next = await readNote(id);
      if (!ownsSession()) return;
      load(next); currentId.current = next.id; onSelect(next.id, next.title); setEditorKey(value => value + 1);
      if (content.current) content.current.scrollTop = 0;
    }
    setPickerOpen(false);
  });
  const newNote = () => run(() => {
    load(null); currentId.current = null; onSelect(null);
    const next = blankNote(); draftRef.current = next; setDraft(next);
    setEditorKey(value => value + 1); setPickerOpen(false);
    if (content.current) content.current.scrollTop = 0;
  });
  // Only the full note workspace replaces this editing session. Other pages keep it mounted.
  const blocker = useBlocker(({ nextLocation }) => nextLocation.pathname.startsWith('/notes') && (dirty || creating || switching || (!note && (!!draft.content.trim() || !!draft.title.trim()))));
  const handledOpenRequest = useRef<number | null>(null);
  const openRequestedNote = useEffectEvent((id: number) => { void open(id); });
  useEffect(() => {
    if (!visible || loading || switching || creating || blocker.state !== 'unblocked' || !openRequest || handledOpenRequest.current === openRequest.sequence) return;
    handledOpenRequest.current = openRequest.sequence;
    openRequestedNote(openRequest.id);
  }, [openRequest, visible, loading, switching, creating, blocker.state]);
  const leaving = useRef(false);
  const saveForNavigation = useEffectEvent(save);
  useEffect(() => {
    if (blocker.state !== 'blocked' || switching || leaving.current) return;
    leaving.current = true;
    void saveForNavigation().then(() => blocker.proceed()).catch(() => {
      setMessage('保存未完成，请重试后再打开完整笔记。'); blocker.reset();
    }).finally(() => { leaving.current = false; });
  }, [blocker, switching]);
  const disabled = loading || switching || creating || blocker.state !== 'unblocked';
  const displayed = note ?? draft;
  const matches = [ ...(note ? [note] : []), ...items.filter(item => item.id !== note?.id) ]
    .filter(item => (!favorites || item.is_favorite) && `${item.title}\n${item.content}`.toLowerCase().includes(query.trim().toLowerCase()));

  return <aside className="um-notes-sidebar notes-workspace" aria-label="笔记侧栏" onKeyDown={event => { if (event.key === 'Escape' && pickerOpen && !event.defaultPrevented) { event.preventDefault(); event.stopPropagation(); setPickerOpen(false); } }}>
    <header className="um-notes-sidebar-header">
      <strong>笔记</strong>
      <button type="button" aria-label="新建笔记" title="新建笔记" disabled={disabled} onClick={() => void newNote()}><Plus size={18} /></button>
      <button type="button" aria-label="打开完整笔记" title="在完整页面中整理" disabled={disabled} onClick={() => void run(() => navigate(currentId.current ? `/notes/${currentId.current}` : '/notes'))}><ArrowSquareOut size={17} /></button>
      <button type="button" onClick={onClose} aria-label="收起笔记" title="收起笔记，保留当前内容"><X size={18} /></button>
    </header>
    <div className="um-notes-document-bar">
      <button type="button" className="um-notes-switch" aria-label={pickerOpen ? '返回当前笔记' : '切换笔记'} aria-expanded={pickerOpen} aria-controls="um-notes-picker" disabled={disabled} onClick={() => { setPickerOpen(value => !value); if (!pickerOpen) setRefresh(value => value + 1); }}>
        <span>{pickerOpen ? '返回当前笔记' : displayed.title || '随手记'}</span>{pickerOpen ? <ArrowLeft size={14} /> : <CaretDown size={14} />}
      </button>
      <span>{pickerOpen ? '切换笔记' : note ? '继续记录' : '输入后自动保存'}</span>
    </div>
    {(message || error) && <div role="alert" className="notes-save-error">{error || message}<button type="button" disabled={disabled} onClick={() => void run(() => {})}>重试保存</button></div>}
    <div ref={content} className="um-notes-sidebar-content" hidden={pickerOpen} inert={switching || loading || blocker.state !== 'unblocked'} aria-busy={switching || loading}>
      {loading ? <div className="um-notes-skeleton" role="status" aria-label="正在加载笔记"><i /><i /><i /></div> : <NoteEditor compact autoFocus={visible} key={editorKey} note={displayed} notebooks={[]} onChange={edit} onOpen={id => void open(id)} />}
    </div>
    {pickerOpen && <section id="um-notes-picker" className="um-notes-picker" aria-label="选择笔记">
      <label className="um-notes-search"><MagnifyingGlass size={16} /><input autoFocus aria-label="搜索笔记" placeholder="搜索标题或正文" value={query} onChange={event => setQuery(event.target.value)} />{query && <button type="button" aria-label="清空搜索" onClick={() => setQuery('')}><X size={14} /></button>}</label>
      <div className="um-notes-picker-heading"><span>{query.trim() ? `${matches.length} 篇匹配` : favorites ? '收藏的笔记' : '最近编辑'}</span><button type="button" aria-pressed={favorites} onClick={() => setFavorites(value => !value)}><Star size={14} weight={favorites ? 'fill' : 'regular'} />收藏</button></div>
      {listError && <p className="um-notes-list-error" role="status">{listError}<button type="button" onClick={() => setRefresh(value => value + 1)}>刷新</button></p>}
      <div className="um-notes-results">{matches.map(item => <button type="button" className="um-notes-result" key={item.id} aria-current={note?.id === item.id ? 'true' : undefined} disabled={disabled} onClick={() => void open(item.id)}>
        <div><strong>{item.title || '未命名笔记'}</strong>{note?.id === item.id ? <Check size={15} /> : item.is_favorite && <Star size={13} />}</div>
        <span>{item.content.replace(/[#*`>]/g, '').slice(0, 100) || '还没有正文'}</span><small>{new Date(item.updated_at).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })}</small>
      </button>)}{!matches.length && <div className="um-notes-picker-empty"><FileText size={28} /><p>{query.trim() ? '没有找到相关笔记' : favorites ? '还没有收藏的笔记' : '还没有笔记'}</p><span>{query.trim() ? '换个关键词，或新建一篇记录。' : '点击右上角的 +，开始记录。'}</span></div>}</div>
    </section>}
    {!pickerOpen && listError && <p className="um-notes-list-error">{listError}<button type="button" onClick={() => setRefresh(value => value + 1)}>刷新</button></p>}
    <footer className="um-notes-sidebar-footer"><span role="status" data-error={!!(message || error)}><i />{loading ? '正在加载…' : creating ? '正在创建…' : message || error ? '内容已保留，尚未保存' : note ? status : '尚未创建笔记'}</span><span>关闭侧栏可继续学习</span></footer>
  </aside>;
}
