import api from './api';

export interface Notebook { id: number; name: string; parent: number | null; position: number }
export interface Note {
  id: number; title: string; content: string; notebook: number | null; tags: string[];
  is_favorite: boolean; version: number; deleted_at: string | null; updated_at: string;
  backlinks: { id: number; title: string }[];
}
export interface NoteBinding { id: number; bot: number; note: number | null; notebook: number | null }
export type NoteDraft = Pick<Note, 'title' | 'content' | 'notebook' | 'tags' | 'is_favorite'>;
// A write with an unknown outcome must be reviewed, not automatically repeated.
const writeConfig = { __retryCount: 2, timeout: 30000 };
export const noteDraft = (note: Note): NoteDraft => ({ title: note.title, content: note.content, notebook: note.notebook, tags: note.tags, is_favorite: note.is_favorite });
export const notesApi = {
  list: (params: Record<string, string> = {}, signal?: AbortSignal) => api.get<Note[]>('/notes/items/', { params, signal }).then(r => r.data),
  get: (id: number, signal?: AbortSignal) => api.get<Note>(`/notes/items/${id}/`, { signal }).then(r => r.data),
  create: (notebook: number | null) => api.post<Note>('/notes/items/', { title: '未命名笔记', notebook }, writeConfig).then(r => r.data),
  save: (note: Note) => api.patch<Note>(`/notes/items/${note.id}/`, { ...noteDraft(note), version: note.version }, writeConfig).then(r => r.data),
  remove: (id: number, permanent = false) => api.delete(`/notes/items/${id}/`, { ...writeConfig, params: permanent ? { permanent: '1' } : {} }),
  restore: (id: number) => api.post<Note>(`/notes/items/${id}/restore/`, {}, writeConfig).then(r => r.data),
  notebooks: () => api.get<Notebook[]>('/notes/notebooks/').then(r => r.data),
  createNotebook: (name: string, parent: number | null) => api.post<Notebook>('/notes/notebooks/', { name, parent }, writeConfig).then(r => r.data),
  updateNotebook: (id: number, data: Partial<Notebook>) => api.patch(`/notes/notebooks/${id}/`, data, writeConfig),
  removeNotebook: (id: number) => api.delete(`/notes/notebooks/${id}/`, writeConfig),
  tags: () => api.get<{ id: number; name: string }[]>('/notes/tags/').then(r => r.data),
  bindings: (bot: number) => api.get<NoteBinding[]>('/notes/bindings/', { params: { bot } }).then(r => r.data),
  bind: (bot: number, source: { note: number } | { notebook: number }) => api.post<NoteBinding>('/notes/bindings/', { bot, ...source }, writeConfig).then(r => r.data),
  unbind: (id: number) => api.delete(`/notes/bindings/${id}/`, writeConfig),
  references: (bot: number, conversation_id: string, signal?: AbortSignal) => api.get<{ note_ids: number[] }>('/notes/references/', { params: { bot, conversation_id }, signal }).then(r => r.data.note_ids),
  saveReferences: (bot: number, conversation_id: string, note_ids: number[]) => api.put('/notes/references/', { note_ids }, { ...writeConfig, params: { bot, conversation_id } }),
  export: async (kind: 'items' | 'notebooks', id: number) => {
    const { data } = await api.get<Blob>(`/notes/${kind}/${id}/export/`, { responseType: 'blob' });
    const url = URL.createObjectURL(data);
    const anchor = document.createElement('a');
    anchor.href = url; anchor.download = `${kind === 'items' ? 'note' : 'notebook'}-${id}.${kind === 'items' ? 'md' : 'zip'}`;
    anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};
export function notebookPath(id: number | null, notebooks: Notebook[]): string {
  const parts: string[] = [];
  const seen = new Set<number>();
  while (id !== null && !seen.has(id)) {
    seen.add(id);
    const item = notebooks.find(n => n.id === id);
    if (!item) break;
    parts.unshift(item.name); id = item.parent;
  }
  return parts.join(' / ') || '未分类';
}
