import { t } from '@/i18n';
import { loadOfflineCache, updateLocalDemo } from './offlineData';
import { DEMO_USER_ID, OFFLINE_MESSAGE } from './offlineSession';
import type { Note } from './notes';

export async function demoRequest(method: string, path: string, payload: unknown = {}, params: Record<string, unknown> = {}): Promise<unknown> {
  const verb = method.toLowerCase();
  const parsed = typeof payload === 'string' ? JSON.parse(payload) : payload;
  const data = parsed && typeof parsed === 'object' ? parsed as Record<string, unknown> : {};
  const url = new URL(path, 'https://offline.local');
  path = url.pathname.replace(/^\/api/, '');
  const cache = await loadOfflineCache(DEMO_USER_ID);
  if (!cache) throw new Error(t('离线存储不可用。'));
  if (verb === 'get') {
    if (path === '/users/workspace/') return { available: false, demo: true, role: null, workspace: null, courses: [], members: [], invites: [], usage: [] };
    if (path === '/courses/') return { items: [], total: 0, page: 1, total_pages: 1 };
    if (path === '/ai/bots/') return [{ id: 1, name: '小宇', bot_type: 'planner', avatar: null, institution: null, is_active: true }];
    if (['/ai/projects/', '/ai/history/', '/ai/sessions/', '/courses/modules/', '/courses/watch-history/'].includes(path)) return [];
  }
  if (path === '/notes/ai-settings/' && verb === 'get') return { enabled: false, acknowledged: true };
  if (path === '/notes/references/' && verb === 'get') return { note_ids: [] };
  if (path === '/notes/bindings/' && verb === 'get') return [];
  if (path === '/notes/tags/' && verb === 'get') return cache.tags;
  if (path === '/notes/lookup/' && verb === 'get') return cache.notes.filter(n => !n.deleted_at);
  if (path === '/notes/items/' && verb === 'get') {
    const p = { ...Object.fromEntries(url.searchParams), ...params };
    return cache.notes.filter(n => (p.trash ? !!n.deleted_at : !n.deleted_at) && (!p.favorite || n.is_favorite) && (!p.notebook || String(n.notebook) === String(p.notebook)) && (!p.q || `${n.title}\n${n.content}`.includes(String(p.q))) && (!p.tag || n.tags.includes(String(p.tag))));
  }
  if (path === '/notes/notebooks/' && verb === 'get') return cache.notebooks;
  if (path === '/notes/items/' && verb === 'post') {
    const note: Note = { title: t('未命名笔记'), content: '', notebook: null, tags: [], is_favorite: false, ...data, id: Date.now(), version: 1, deleted_at: null, backlinks: [], updated_at: new Date().toISOString() } as Note;
    await updateLocalDemo(value => { value.notes.unshift(note); }); return note;
  }
  const noteMatch = path.match(/^\/notes\/items\/(\d+)\/(restore\/)?$/);
  if (noteMatch) {
    const note = cache.notes.find(n => n.id === Number(noteMatch[1]));
    if (!note) throw new Error(t('笔记不存在'));
    if (verb === 'get') return note;
    if (!['patch', 'delete'].includes(verb) && !(verb === 'post' && noteMatch[2])) throw new Error(t(OFFLINE_MESSAGE));
    if (verb === 'delete' && (params.permanent === '1' || url.searchParams.get('permanent') === '1')) {
      await updateLocalDemo(value => { value.notes = value.notes.filter(item => item.id !== note.id); }); return {};
    }
    const next = { ...note, ...data, id: note.id, version: note.version + 1, updated_at: new Date().toISOString() };
    if (verb === 'delete') next.deleted_at = new Date().toISOString();
    if (noteMatch[2]) next.deleted_at = null;
    await updateLocalDemo(value => { value.notes = value.notes.map(n => n.id === note.id ? next : n); }); return next;
  }
  if (path === '/notes/notebooks/' && verb === 'post') {
    const book = { id: Date.now(), name: String(data.name), parent: (data.parent as number) || null, position: cache.notebooks.length };
    await updateLocalDemo(value => { value.notebooks.push(book); }); return book;
  }
  const bookMatch = path.match(/^\/notes\/notebooks\/(\d+)\/$/);
  if (bookMatch && ['patch', 'delete'].includes(verb)) {
    const id = Number(bookMatch[1]);
    await updateLocalDemo(value => {
      value.notebooks = verb === 'delete' ? value.notebooks.filter(n => n.id !== id) : value.notebooks.map(n => n.id === id ? { ...n, ...data, id } : n);
      if (verb === 'delete') {
        value.notes = value.notes.map(note => note.notebook === id ? { ...note, notebook: null } : note);
        value.notebooks = value.notebooks.map(book => book.parent === id ? { ...book, parent: null } : book);
      }
    }); return {};
  }
  throw new Error(t(OFFLINE_MESSAGE));
}
export { demoRequest as offlineDemoRequest };
