import { useCallback, useEffect, useRef, useState } from 'react';
import { useBlocker, useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { FilePlus, FolderPlus, Notebook as NotebookIcon, ChatCircleText, MagnifyingGlass, ArrowClockwise, ArrowCounterClockwise, ClockCounterClockwise, DownloadSimple, Export, Folders, FunnelX, NotePencil, PencilSimple, Stack, Star, Trash, X } from '@phosphor-icons/react';
import api from '@/lib/api';
import type { Bot } from '@/hooks/useAgentConversation';
import { notesApi, notebookPath, type Note, type Notebook } from '@/lib/notes';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import NoteEditor from './NoteEditor';
import NotesAgentPanel from './NotesAgentPanel';
import NoteDialog, { type NoteDialogOptions } from './NoteDialog';
import { useNoteSave } from './useNoteSave';
import '@/styles/notes.css';

export default function NotesPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [dialog, setDialog] = useState<NoteDialogOptions | null>(null);
  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  const [items, setItems] = useState<Note[]>([]);
  const [allNotes, setAllNotes] = useState<Note[]>([]);
  const [tags, setTags] = useState<{ id: number; name: string }[]>([]);
  const [bots, setBots] = useState<Bot[]>([]);
  const [query, setQuery] = useState('');
  const [folder, setFolder] = useState('');
  const [tag, setTag] = useState('');
  const [bot, setBot] = useState('');
  const [view, setView] = useState<'all' | 'favorite' | 'recent' | 'trash'>('all');
  const [mobileView, setMobileView] = useState<'directory' | 'editor' | 'discussion'>('directory');
  const [discussion, setDiscussion] = useState(false);
  const [discussionMounted, setDiscussionMounted] = useState(false);
  const [openRequest, setOpenRequest] = useState(0);
  const [selection, setSelection] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(false);
  const [listLoading, setListLoading] = useState(false);
  const [pageError, setPageError] = useState('');
  const [listError, setListError] = useState('');
  const [busy, setBusy] = useState(false);
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());
  const mounted = useRef(true);
  const hasAI = useInstitutionStore(state => state.hasFeature('ai.assistant'));
  const onSaved = useCallback((saved: Note) => {
    setAllNotes(previous => previous.map(item => item.id === saved.id ? saved : item));
    setItems(previous => previous.map(item => item.id === saved.id ? saved : item));
    setTags(previous => [...previous, ...saved.tags.filter(name => !previous.some(tag => tag.name === name)).map((name, index) => ({ id: -Date.now() - index, name }))]);
  }, []);
  const { note, documentKey, dirty, status, error, load, change, flush } = useNoteSave(onSaved);
  const blocker = useBlocker(dirty || busy);
  const blocking = useRef(false);
  useEffect(() => {
    if (busy || blocker.state !== 'blocked' || blocking.current) return;
    blocking.current = true;
    void flush().then(() => blocker.proceed()).catch(() => blocker.reset()).finally(() => { blocking.current = false; });
  }, [blocker, busy, flush]);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const reload = useCallback(() => setRefresh(value => value + 1), []);
  useEffect(() => {
    let active = true;
    void Promise.all([notesApi.notebooks(), notesApi.list(), notesApi.tags()]).then(([books, notes, labels]) => {
      if (active) { setNotebooks(books); setAllNotes(notes); setTags(labels); }
    }).catch(() => { if (active) setListError('笔记目录加载失败，请刷新重试。'); });
    return () => { active = false; };
  }, [refresh]);
  useEffect(() => {
    if (hasAI) void api.get<Bot[]>('/ai/bots/').then(r => setBots(r.data)).catch(() => {});
  }, [hasAI]);
  useEffect(() => {
    const controller = new AbortController();
    setListLoading(true); setListError('');
    const timer = setTimeout(() => {
      const params: Record<string, string> = {};
      if (query) params.q = query;
      if (folder) params.notebook = folder;
      if (tag) params.tag = tag;
      if (bot) params.bot = bot;
      if (view === 'favorite') params.favorite = '1';
      if (view === 'trash') params.trash = '1';
      void notesApi.list(params, controller.signal).then(result => { if (!controller.signal.aborted) setItems(result); }).catch(() => { if (!controller.signal.aborted) setListError('搜索失败，请重试。'); }).finally(() => { if (!controller.signal.aborted) setListLoading(false); });
    }, query ? 220 : 0);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query, folder, tag, bot, view, refresh]);
  useEffect(() => {
    setDialog(null);
    if (!id) { load(null); setLoading(false); setPageError(''); return; }
    const controller = new AbortController();
    setLoading(true); setPageError(''); setSelection('');
    void notesApi.get(Number(id), controller.signal).then(result => {
      if (!controller.signal.aborted) { load(result); setMobileView('editor'); }
    }).catch(() => { if (!controller.signal.aborted) { load(null); setPageError('笔记不存在、不可访问或加载失败。'); } }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [id, load]);
  const run = async (work: () => Promise<void>) => {
    if (busy || blocker.state !== 'unblocked') return;
    setBusy(true);
    try { await flush(); await work(); } catch (cause) { toast.error(cause instanceof Error ? cause.message : '操作失败，请重试。'); } finally { if (mounted.current) setBusy(false); }
  };
  const open = (target: number) => { navigate(`/notes/${target}`); setMobileView('editor'); };
  const createNote = () => void run(async () => {
    const created = await notesApi.create(folder && folder !== 'unfiled' ? Number(folder) : null);
    setView('all'); reload(); navigate(`/notes/${created.id}`); setMobileView('editor');
  });
  const createNotebook = () => setDialog({ title: '新建笔记本', initialValue: '', confirmText: '创建', onConfirm: name => void run(async () => {
    const book = await notesApi.createNotebook(name, folder && folder !== 'unfiled' ? Number(folder) : null);
    setFolder(String(book.id)); setView('all'); reload();
  }) });
  const selectedNotebook = notebooks.find(book => String(book.id) === folder);
  const changeNotebook = async (patch: Partial<Notebook>) => {
    if (selectedNotebook) await notesApi.updateNotebook(selectedNotebook.id, patch);
    reload();
  };
  const removeNote = () => {
    if (!note) return;
    const permanent = !!note.deleted_at;
    setDialog({ title: permanent ? '永久删除笔记？' : '移入回收站？', description: permanent ? '删除后无法恢复。' : undefined, confirmText: permanent ? '永久删除' : '移入回收站', destructive: true, onConfirm: () => void run(async () => { await notesApi.remove(note.id, permanent); load(null); reload(); navigate('/notes'); setMobileView('directory'); }) });
  };
  const downloadLocal = () => {
    if (!note) return;
    const url = URL.createObjectURL(new Blob([`# ${note.title}\n\n${note.content}`], { type: 'text/markdown;charset=utf-8' }));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = `note-${note.id}-local.md`; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const showDiscussion = () => { setDiscussionMounted(true); setDiscussion(true); setMobileView('discussion'); setOpenRequest(value => value + 1); };
  const descendants = (target: number, candidate: Notebook): boolean => {
    let parent: Notebook | undefined = candidate;
    while (parent) { if (parent.id === target) return true; parent = notebooks.find(book => book.id === parent?.parent); }
    return false;
  };
  const tree = (parent: number | null, depth = 0): React.ReactNode => notebooks.filter(book => book.parent === parent).map(book => <div key={book.id}>
    <div className={`notes-tree-row ${folder === String(book.id) ? 'is-active' : ''}`} style={{ paddingLeft: `${depth * 14}px` }}>
      <button aria-label={`${collapsed.has(book.id) ? '展开' : '折叠'} ${book.name}`} className="notes-tree-toggle" onClick={() => setCollapsed(old => { const next = new Set(old); if (next.has(book.id)) next.delete(book.id); else next.add(book.id); return next; })}>{notebooks.some(child => child.parent === book.id) ? collapsed.has(book.id) ? '›' : '⌄' : '·'}</button>
      <button onClick={() => { setFolder(String(book.id)); if (view === 'trash') setView('all'); }}><NotebookIcon size={15} /><span>{book.name}</span></button>
    </div>{!collapsed.has(book.id) && tree(book.id, depth + 1)}
  </div>);
  const orderedItems = [...items].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  return <div className={`notes-workspace notes-mobile-${mobileView} ${discussion && note && !note.deleted_at ? 'notes-has-discussion' : ''}`}>
    <nav className="notes-mobile-tabs" aria-label="笔记视图"><button aria-label="目录" title="目录" aria-pressed={mobileView === 'directory'} onClick={() => setMobileView('directory')}><Folders size={20} /></button><button aria-label="笔记" title="笔记" aria-pressed={mobileView === 'editor'} disabled={!note} onClick={() => setMobileView('editor')}><NotePencil size={20} /></button>{hasAI && <button aria-label="讨论" title="讨论" aria-pressed={mobileView === 'discussion'} disabled={!note || !!note.deleted_at} onClick={showDiscussion}><ChatCircleText size={20} /></button>}</nav>
    <aside className="notes-directory" aria-label="笔记目录">
      <header className="notes-directory-header"><h1>我的笔记</h1><div><button aria-label="新建笔记本" title="新建笔记本" disabled={busy} onClick={createNotebook}><FolderPlus size={20} /></button><button aria-label="新建笔记" title="新建笔记" disabled={busy} onClick={createNote}><FilePlus size={20} /></button></div></header>
      <label className="notes-search"><MagnifyingGlass size={17} /><input aria-label="搜索全部笔记标题和正文" placeholder="搜索标题、正文" value={query} onChange={e => setQuery(e.target.value)} /></label>
      <div className="notes-quickviews">{(['all', 'recent', 'favorite', 'trash'] as const).map(value => <button key={value} aria-label={({ all: '全部', recent: '最近', favorite: '收藏', trash: '回收站' })[value]} title={({ all: '全部', recent: '最近', favorite: '收藏', trash: '回收站' })[value]} aria-pressed={view === value} onClick={() => setView(value)}>{({ all: <Stack size={19} />, recent: <ClockCounterClockwise size={19} />, favorite: <Star size={19} />, trash: <Trash size={19} /> })[value]}</button>)}</div>
      <div className="notes-tree"><button className={`notes-tree-root ${folder === '' ? 'is-active' : ''}`} onClick={() => setFolder('')}>所有笔记本</button><button className={`notes-tree-root ${folder === 'unfiled' ? 'is-active' : ''}`} onClick={() => setFolder('unfiled')}>未分类</button>{tree(null)}</div>
      {selectedNotebook && <details className="notes-book-actions"><summary>{selectedNotebook.name}</summary><div className="notes-book-toolbar">
        <button aria-label="重命名笔记本" title="重命名" disabled={busy} onClick={() => setDialog({ title: '笔记本名称', initialValue: selectedNotebook.name, onConfirm: name => void run(() => changeNotebook({ name })) })}><PencilSimple size={18} /></button>
        <select aria-label="移动笔记本到" value={selectedNotebook.parent ?? ''} disabled={busy} onChange={e => void run(() => changeNotebook({ parent: e.target.value ? Number(e.target.value) : null }))}><option value="">根目录</option>{notebooks.filter(book => !descendants(selectedNotebook.id, book)).map(book => <option key={book.id} value={book.id}>{notebookPath(book.id, notebooks)}</option>)}</select>
        <button aria-label="导出笔记本" title="导出 ZIP" disabled={busy} onClick={() => void run(() => notesApi.export('notebooks', selectedNotebook.id))}><Export size={18} /></button>
        <button aria-label="删除笔记本" title="删除笔记本" className="notes-danger" disabled={busy} onClick={() => setDialog({ title: '删除笔记本？', description: '笔记和子目录移到上一级，此笔记本的 Agent 关联解除。', confirmText: '删除', destructive: true, onConfirm: () => void run(async () => { await notesApi.removeNotebook(selectedNotebook.id); setFolder(selectedNotebook.parent ? String(selectedNotebook.parent) : ''); if (note?.notebook === selectedNotebook.id) load(await notesApi.get(note.id)); reload(); }) })}><Trash size={18} /></button>
      </div></details>}
      <div className="notes-filters"><select aria-label="按标签筛选" value={tag} onChange={e => setTag(e.target.value)}><option value="">所有标签</option>{tags.map(label => <option key={label.id} value={label.name}>{label.name}</option>)}</select>{bots.length > 0 && <select aria-label="按关联 Agent 筛选" value={bot} onChange={e => setBot(e.target.value)}><option value="">所有关联 Agent</option>{bots.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select>}</div>
      {(query || folder || tag || bot || view !== 'all') && <button aria-label="清除筛选" title="清除筛选" className="notes-clear-filters" onClick={() => { setQuery(''); setFolder(''); setTag(''); setBot(''); setView('all'); }}><FunnelX size={16} /></button>}
      <div className="notes-list-heading"><span>{view === 'trash' ? '回收站' : selectedNotebook?.name || '笔记'}</span><small>{listLoading ? '加载中…' : `${items.length} 篇`}</small></div>
      {listError && <p className="notes-error" role="alert">{listError}<button onClick={reload}>重试</button></p>}
      <div className="notes-list" aria-busy={listLoading}>{orderedItems.map(item => <button className={item.id === note?.id ? 'is-active' : ''} key={item.id} onClick={() => open(item.id)}><strong>{item.is_favorite && '☆ '}{item.title || '未命名笔记'}</strong><span>{item.content.replace(/[#*`>\[\]]/g, '').slice(0, 60) || '还没有正文'}</span><small>{new Date(item.updated_at).toLocaleDateString()} · {notebookPath(item.notebook, notebooks)}</small></button>)}{!listLoading && !items.length && !listError && <p className="notes-empty">{view === 'trash' ? '回收站是空的。' : '没有匹配的笔记。'}{view !== 'trash' && <button onClick={createNote}>写一篇新笔记</button>}</p>}</div>
    </aside>
    <main className="notes-main" aria-busy={loading}>
      {loading && <div className="notes-loading">正在打开笔记…</div>}
      {pageError && <div className="notes-empty" role="alert">{pageError}<button onClick={() => navigate('/notes')}>返回目录</button></div>}
      {note && !pageError ? <>
        <header className="notes-note-header"><span aria-live="polite">{status}{dirty && status === '已保存' ? ' · 未保存' : ''}</span><div>{hasAI && !note.deleted_at && <button aria-label="讨论" title="讨论" onClick={showDiscussion}><ChatCircleText size={19} /></button>}<button aria-label="导出笔记" title="导出笔记" disabled={busy} onClick={() => void run(() => notesApi.export('items', note.id))}><Export size={19} /></button>{note.deleted_at && <button aria-label="恢复笔记" title="恢复笔记" disabled={busy} onClick={() => void run(async () => { load(await notesApi.restore(note.id)); setView('all'); reload(); })}><ArrowCounterClockwise size={19} /></button>}<button aria-label={note.deleted_at ? '永久删除' : '移入回收站'} title={note.deleted_at ? '永久删除' : '移入回收站'} disabled={busy} className="notes-danger" onClick={removeNote}><Trash size={19} /></button></div></header>
        {error && <div className="notes-save-error" role="alert"><p>{error}</p><button aria-label="重试保存" title="重试保存" onClick={() => void flush().catch(() => {})}><ArrowClockwise size={18} /></button><button aria-label="下载本地内容" title="下载本地内容" onClick={downloadLocal}><DownloadSimple size={18} /></button><button aria-label="重新加载远端" title="重新加载远端" onClick={() => setDialog({ title: '重新加载笔记？', description: '本地尚未保存的修改将被丢弃。', destructive: true, confirmText: '重新加载', onConfirm: () => { void notesApi.get(note.id).then(load).catch(() => toast.error('加载失败，本地内容已保留。')); } })}><ArrowCounterClockwise size={18} /></button></div>}
        {note.deleted_at && <p className="notes-trash-banner">已移入回收站</p>}
        <div className="notes-writing-surface" inert={loading || busy || undefined}><NoteEditor key={`${note.id}:${documentKey}`} note={note} notebooks={notebooks} onChange={change} onOpen={open} onSelection={setSelection} /></div>
      </> : !loading && !pageError && <div className="notes-welcome"><NotebookIcon size={34} weight="thin" /><button onClick={createNote}>写一篇笔记</button></div>}
    </main>
    {discussionMounted && note && !note.deleted_at && hasAI && <aside className={`notes-discussion ${discussion ? '' : 'is-hidden'}`}  aria-label="笔记讨论"><header className="notes-discussion-title"><span>围绕笔记讨论</span><button aria-label="收起讨论" title="收起" onClick={() => { setDiscussion(false); setMobileView('editor'); }}><X size={18} /></button></header><NotesAgentPanel note={note} notes={allNotes} notebooks={notebooks} beforeSend={flush} selection={selection} clearSelection={() => setSelection('')} openRequest={openRequest} /></aside>}
    {dialog && <NoteDialog {...dialog} onClose={() => setDialog(null)} />}
  </div>;
}
